"""
智能点餐助手主程序 FastAPI 接口

分层：
- 顾客端：/chat /delivery /menu/list /cart* /order*
- 餐厅端（admin）：/admin/orders /admin/menu/{id} /admin/order/{id}/status
- 健康检查：/health /session/{id}
"""

import logging
import re
import uuid
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from service.diancan_service import service
from tools import amap_tool, config, db_tool, image_tool

logger = logging.getLogger(__name__)

# 地址完整性判断：只要写到「具体地点」即可，不强制门牌号
# 例如「重庆市大渡口人民医院」「龙湖时代天街」都算合格
_ADDRESS_HINT_RE = re.compile(
    r'(省|市|区|县|镇|乡|村|路|街|道|巷|弄|胡同|大道|小区|花园|广场|大厦|公寓'
    r'|中心|公园|医院|学校|大学|学院|车站|机场|地铁|酒店|宾馆|超市|商场|市场'
    r'|馆|院|校|园|城|号|栋|幢|单元|室|楼)'
)

app = FastAPI(
    title='智能点餐助手 API',
    version='1.0.0',
    description='智能点餐后端：对话推荐、配送查询、购物车、下单、餐厅管理',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=False,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.mount('/images', StaticFiles(directory=str(config.PROJECT_ROOT / 'ui' / 'public' / 'images'), check_dir=False), name='images')

_visitor: ContextVar[Optional[str]] = ContextVar('visitor', default=None)


@app.middleware('http')
async def visitor_session(request: Request, call_next):
    if not request.url.path.startswith(('/cart', '/order')):
        return await call_next(request)
    visitor = request.cookies.get('dining_visitor', '')
    fresh = not re.fullmatch(r'[a-f0-9]{32}', visitor)
    if fresh:
        visitor = uuid.uuid4().hex
    token = _visitor.set(visitor)
    try:
        response = await call_next(request)
        if fresh:
            response.set_cookie('dining_visitor', visitor, max_age=2592000, httponly=True, samesite='lax')
        return response
    finally:
        _visitor.reset(token)


# ================================================================ 请求模型

class DishImageRequest(BaseModel):
    dish_name: str = Field(..., min_length=1, max_length=50)
    category: str = Field('', max_length=50)
    description: str = Field('', max_length=300)
    main_ingredients: str = Field('', max_length=200)
    cooking_method: str = Field('', max_length=80)
    is_vegetarian: bool = False


@app.post('/admin/menu/image-jobs', summary='创建菜品 AI 配图任务')
def create_dish_image(body: DishImageRequest):
    if not body.dish_name.strip():
        raise HTTPException(status_code=400, detail='请先填写菜品名称')
    try:
        return image_tool.create_job(body.model_dump())
    except image_tool.ImageGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get('/admin/menu/image-jobs/{job_id}', summary='查询菜品图片生成状态')
def dish_image_status(job_id: str):
    try:
        return image_tool.get_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

class ChatRequest(BaseModel):
    query: str = Field(..., description='用户说的话')
    session_id: Optional[str] = None


class DeliveryRequest(BaseModel):
    address: str
    travel_mode: Optional[int] = None


class CartAddRequest(BaseModel):
    user_id: Optional[int] = Field(None, description='不传则用 guest')
    dish_id: int
    quantity: int = Field(1, ge=1)


class CartRemoveRequest(BaseModel):
    user_id: Optional[int] = None
    dish_id: int


class CartClearRequest(BaseModel):
    user_id: Optional[int] = None


class CartSetRequest(BaseModel):
    user_id: Optional[int] = None
    dish_id: int
    quantity: int = Field(..., description='目标数量，<=0 表示移除该菜品')


class OrderLineRequest(BaseModel):
    dish_id: int = Field(..., ge=1, strict=True)
    quantity: int = Field(..., ge=1, le=999, strict=True)


class OrderCreateRequest(BaseModel):
    user_id: Optional[int] = None
    contact_name: str
    contact_phone: str
    delivery_address: Optional[str] = None
    delivery_mode: int = Field(2, ge=1, le=2, description='1-到店自取，2-外卖配送')
    table_no: Optional[str] = Field(None, description='堂食桌号，可空')
    items: Optional[List[OrderLineRequest]] = Field(
        None, description='不传则直接下单购物车全部内容')
    delivery_distance: Optional[float] = None
    member_id: Optional[int] = Field(None, description='会员ID，会员下单时传入')
    coupon_id: Optional[int] = Field(None, description='使用的优惠券ID，需配合 member_id')


class OrderStatusUpdateRequest(BaseModel):
    status: int = Field(..., ge=0, le=4)


class OrderPayRequest(BaseModel):
    payment_method: int = Field(..., description='支付方式：1-微信，2-支付宝，3-会员余额')


class MemberCreateRequest(BaseModel):
    phone: str = Field(..., description='11 位手机号')
    name: Optional[str] = None


class RechargeRequest(BaseModel):
    amount: float = Field(..., gt=0, description='充值金额')


class CouponIssueRequest(BaseModel):
    title: str
    amount: float = Field(..., gt=0, description='抵扣金额')
    min_spend: float = Field(0, ge=0, description='使用门槛')
    expire_days: int = Field(30, ge=0, description='有效天数，0 表示长期有效')


class TableOpenRequest(BaseModel):
    table_no: str


class TableChangeRequest(BaseModel):
    from_table_no: str
    to_table_no: str


class TableCloseRequest(BaseModel):
    table_no: str
    settle: bool = Field(True, description='是否同时把该桌订单结账为已完成')


class InventoryUpdateRequest(BaseModel):
    add: Optional[float] = Field(None, description='增量补货数量')
    stock: Optional[float] = Field(None, description='直接设定库存')
    threshold: Optional[float] = Field(None, description='补货预警阈值')


# ================================================================ 顾客端

@app.get('/', summary='服务简介')
def root() -> Dict[str, Any]:
    return {
        'service': '智能点餐助手 API',
        'model': config.LLM_MODEL,
        'shop': config.MERCHANT_NAME,
        'endpoints': [
            'POST /chat', 'POST /delivery', 'GET /menu/list',
            'GET /cart', 'POST /cart/add', 'POST /cart/set', 'POST /cart/remove', 'POST /cart/clear',
            'POST /order', 'GET /order/list', 'GET /order/{id}', 'POST /order/{id}/pay',
            'GET /admin/orders', 'POST /admin/order/{id}/status',
            'GET /admin/reports/summary',
            'GET /admin/kitchen', 'GET /admin/tables',
            'POST /admin/table/open', 'POST /admin/table/change',
            'POST /admin/table/merge', 'POST /admin/table/close',
            'PATCH /admin/menu/{id}',
            'GET /health', 'DELETE /session/{session_id}',
        ],
    }


@app.post('/chat')
def chat(request: ChatRequest) -> Dict[str, Any]:
    if not (request.query or '').strip():
        raise HTTPException(status_code=400, detail='query 不能为空')
    try:
        return service.smart_chat(request.query, request.session_id)
    except Exception as exc:
        logger.exception('对话处理失败')
        raise HTTPException(status_code=500, detail=f'对话处理失败：{exc}') from exc


@app.get('/shop', summary='门店与支付渠道资料')
def shop_info() -> Dict[str, Any]:
    return {
        'name': config.MERCHANT_NAME,
        'address': config.MERCHANT_ADDRESS,
        'phone': config.MERCHANT_PHONE,
        'business_hours': config.MERCHANT_BUSINESS_HOURS,
        'delivery_radius_km': config.DELIVERY_RADIUS / 1000,
        'online_payment_available': False,
        'payment_notice': '微信/支付宝尚未接入，订单提交后保留为待支付，请联系门店确认收款方式。',
    }


@app.post('/delivery')
def delivery(request: DeliveryRequest) -> Dict[str, Any]:
    if not (request.address or '').strip():
        raise HTTPException(status_code=400, detail='address 不能为空')
    try:
        return service.delivery_check(request.address, request.travel_mode)
    except Exception as exc:
        logger.exception('配送查询失败')
        raise HTTPException(status_code=500, detail=f'配送查询失败：{exc}') from exc


@app.get('/menu/list')
def menu_list() -> Dict[str, Any]:
    try:
        return service.get_menu()
    except Exception as exc:
        logger.exception('菜品列表查询失败')
        raise HTTPException(status_code=500, detail=f'菜品列表查询失败：{exc}') from exc


# ---------------------------------------------------------------- 购物车

def _resolve_user_id(user_id: Optional[int]) -> int:
    """浏览器匿名会话隔离，不能通过传入其他 user_id 访问别人的购物车。"""
    visitor = _visitor.get()
    if not visitor:
        raise HTTPException(status_code=401, detail='请重新打开点餐页面建立访客会话')
    uid = db_tool.get_or_create_user(f'guest_{visitor}')
    if user_id is not None and int(user_id) != uid:
        raise HTTPException(status_code=403, detail='不能访问其他访客的数据')
    return uid


@app.get('/cart')
def cart_view(user_id: Optional[int] = None) -> Dict[str, Any]:
    uid = _resolve_user_id(user_id)
    try:
        return db_tool.cart_total(uid)
    except Exception as exc:
        logger.exception('查询购物车失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/cart/add')
def cart_add(req: CartAddRequest) -> Dict[str, Any]:
    uid = _resolve_user_id(req.user_id)
    try:
        return db_tool.add_to_cart(uid, req.dish_id, req.quantity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('加入购物车失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/cart/set')
def cart_set(req: CartSetRequest) -> Dict[str, Any]:
    uid = _resolve_user_id(req.user_id)
    try:
        return db_tool.set_cart_quantity(uid, req.dish_id, req.quantity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('设置购物车数量失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/cart/remove')
def cart_remove(req: CartRemoveRequest) -> Dict[str, Any]:
    uid = _resolve_user_id(req.user_id)
    try:
        ok = db_tool.remove_from_cart(uid, req.dish_id)
        return {'success': ok, 'dish_id': req.dish_id}
    except Exception as exc:
        logger.exception('移除购物车失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/cart/clear')
def cart_clear(req: CartClearRequest) -> Dict[str, Any]:
    uid = _resolve_user_id(req.user_id)
    try:
        n = db_tool.clear_cart(uid)
        return {'cleared': n, 'user_id': uid}
    except Exception as exc:
        logger.exception('清空购物车失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------- 订单

def _address_looks_complete(address: str) -> bool:
    """粗略判断地址是否写到「具体地点」——不强制门牌号。

    「重庆市大渡口人民医院」「龙湖时代天街」这类都算合格；
    真正认不出来的地址由高德的 low_confidence 兜底。
    """
    s = (address or '').strip()
    return len(s) >= 5 and bool(_ADDRESS_HINT_RE.search(s))


@app.post('/order')
def order_create(req: OrderCreateRequest) -> Dict[str, Any]:
    """下单。

    delivery_mode=1（自取）不校验配送范围，地址可为空；
    delivery_mode=2（外卖配送）必须填完整地址，且必须落在配送范围内。
    """
    uid = _resolve_user_id(req.user_id)
    mode = 1 if int(req.delivery_mode) == 1 else 2
    address = (req.delivery_address or '').strip()
    distance = req.delivery_distance

    if not (req.contact_name or '').strip():
        raise HTTPException(status_code=400, detail='请填写联系人姓名')
    if not (req.contact_phone or '').strip():
        raise HTTPException(status_code=400, detail='请填写手机号')
    if not re.fullmatch(r'1[3-9]\d{9}', req.contact_phone.strip()):
        raise HTTPException(status_code=400, detail='请输入有效的 11 位手机号')

    if mode == 2:
        if not address:
            raise HTTPException(status_code=400, detail='外卖配送需要填写收货地址')
        if not _address_looks_complete(address):
            raise HTTPException(
                status_code=400,
                detail='配送地址请写详细一些，具体到某条路、小区、医院、学校等即可，如「重庆市大渡口人民医院」',
            )
        # 校验是否在配送范围内（配送半径见 config.DELIVERY_RADIUS）
        try:
            chk = amap_tool.check_delivery_range(address, config.DEFAULT_PATH_MODE)
        except Exception:
            logger.exception('配送范围校验异常')
            raise HTTPException(status_code=503, detail='配送服务暂不可用，请稍后重试或选择到店自取')
        if not chk or not chk.get('success'):
            raise HTTPException(status_code=503, detail='暂时无法核验配送地址，请重试或选择到店自取')
        if chk is not None:
            if chk.get('low_confidence'):
                raise HTTPException(
                    status_code=400,
                    detail=chk.get('message') or '没能识别这个地址，请补充更具体的地点，如「重庆市大渡口人民医院」',
                )
            if chk.get('success'):
                if not chk.get('in_range'):
                    raise HTTPException(
                        status_code=400,
                        detail=chk.get('message') or '该地址超出配送范围',
                    )
                distance = chk.get('distance')
    else:
        address = ''

    try:
        return db_tool.create_order(
            uid, req.contact_name, req.contact_phone, address or None,
            items=[item.model_dump() for item in req.items] if req.items is not None else None,
            delivery_distance=distance, delivery_mode=mode,
            table_no=(req.table_no or '').strip() or None,
            member_id=req.member_id, coupon_id=req.coupon_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('下单失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get('/order/list')
def order_list(user_id: Optional[int] = None,
               limit: int = Query(10, ge=1, le=50)) -> Dict[str, Any]:
    uid = _resolve_user_id(user_id)
    try:
        orders = db_tool.get_orders(uid, limit=limit)
        return {'orders': orders, 'total': len(orders), 'user_id': uid}
    except Exception as exc:
        logger.exception('查询订单失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get('/order/{order_id}')
def order_detail(order_id: int, user_id: Optional[int] = None) -> Dict[str, Any]:
    uid = _resolve_user_id(user_id)
    try:
        orders = db_tool.get_orders(uid, limit=100)
        order = next((o for o in orders if o['order_id'] == order_id), None)
        if not order:
            raise HTTPException(status_code=404, detail='订单不存在')
        return order
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception('查询订单详情失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/order/{order_id}/pay', summary='订单支付')
def order_pay(order_id: int, body: OrderPayRequest) -> Dict[str, Any]:
    """支付接口预留；渠道和会员身份验证接入前不记录在线支付成功。"""
    try:
        uid = _resolve_user_id(None)
        with db_tool.db_cursor() as cursor:
            cursor.execute('SELECT id FROM orders WHERE id = %s AND user_id = %s', (order_id, uid))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail='订单不存在')
        raise HTTPException(status_code=503, detail='支付渠道和会员身份验证尚未接入，当前不能在线支付；请联系门店')
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('订单支付失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ================================================================ 餐厅端（admin）

@app.get('/admin/orders', summary='餐厅端：所有订单')
def admin_orders(status: Optional[int] = None,
                 limit: int = Query(50, ge=1, le=200)) -> Dict[str, Any]:
    try:
        # 跨用户拿订单——用 db_cursor 直接查
        from tools.db_tool import (db_cursor, _to_float, ORDER_STATUS_TEXT,
                                   DELIVERY_MODE_TEXT, PAYMENT_METHOD_TEXT, PAYMENT_STATUS_TEXT)
        with db_cursor() as cursor:
            sql = (
                'SELECT id, order_no, contact_name, contact_phone, '
                'delivery_address, delivery_mode, table_no, total_amount, discount_amount, '
                'total_quantity, status, payment_method, payment_status, paid_at, '
                'delivery_distance, created_at FROM orders'
            )
            params: List[Any] = []
            if status is not None:
                sql += ' WHERE status = %s'
                params.append(status)
            sql += ' ORDER BY created_at DESC LIMIT %s'
            params.append(limit)
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        orders = []
        for row in rows:
            mode = int(row['delivery_mode'] or 2)
            pay_method = row['payment_method']
            pay_method = int(pay_method) if pay_method is not None else None
            pay_status = int(row['payment_status'] or 0)
            orders.append({
                'order_id': row['id'],
                'order_no': row['order_no'],
                'contact_name': row['contact_name'],
                'contact_phone': row['contact_phone'],
                'delivery_address': row['delivery_address'],
                'delivery_mode': mode,
                'delivery_mode_text': DELIVERY_MODE_TEXT.get(mode, '外卖配送'),
                'table_no': row['table_no'],
                'total_amount': _to_float(row['total_amount']),
                'discount_amount': _to_float(row['discount_amount']),
                'payable_amount': round(_to_float(row['total_amount']) - _to_float(row['discount_amount']), 2),
                'formatted_total': f'¥{_to_float(row["total_amount"]) - _to_float(row["discount_amount"]):.2f}',
                'total_quantity': int(row['total_quantity']),
                'status': int(row['status']),
                'status_text': ORDER_STATUS_TEXT.get(int(row['status']), '未知'),
                'payment_method': pay_method,
                'payment_method_text': PAYMENT_METHOD_TEXT.get(pay_method, '') if pay_method else '',
                'payment_status': pay_status,
                'payment_status_text': PAYMENT_STATUS_TEXT.get(pay_status, '未支付'),
                'paid_at': str(row['paid_at']) if row['paid_at'] else None,
                'delivery_distance': _to_float(row['delivery_distance']) if row['delivery_distance'] is not None else None,
                'created_at': str(row['created_at']),
            })

        # 附上菜品明细与所属档口，供餐厅端展示真实分单结果
        items_map = db_tool.get_order_items_map([o['order_id'] for o in orders])
        for order in orders:
            items = items_map.get(order['order_id'], [])
            order['items'] = items
            stations: List[str] = []
            for it in items:
                if it['station'] not in stations:
                    stations.append(it['station'])
            order['stations'] = stations

        return {'orders': orders, 'total': len(orders)}
    except Exception as exc:
        logger.exception('查询全部订单失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/admin/order/{order_id}/status', summary='餐厅端：更新订单状态')
def admin_order_status(order_id: int, body: OrderStatusUpdateRequest) -> Dict[str, Any]:
    try:
        return db_tool.update_order_status(order_id, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception('更新订单状态失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get('/admin/reports/summary', summary='餐厅端：经营数据看板')
def admin_report_summary() -> Dict[str, Any]:
    """今日营业额、订单量、客单价、热销菜 TOP5、分类占比。"""
    try:
        return db_tool.report_summary()
    except Exception as exc:
        logger.exception('经营报表查询失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get('/admin/kitchen', summary='后厨大屏：按档口分单')
def admin_kitchen() -> Dict[str, Any]:
    """把待处理订单（待接单/已接单）按档口分组，供后厨大屏轮询。"""
    try:
        return db_tool.get_kitchen_orders()
    except Exception as exc:
        logger.exception('后厨分单查询失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get('/admin/tables', summary='餐厅端：桌台状态')
def admin_tables() -> Dict[str, Any]:
    try:
        tables = db_tool.list_tables()
        return {
            'tables': tables,
            'total': len(tables),
            'free': len([t for t in tables if t['status'] == 0]),
        }
    except Exception as exc:
        logger.exception('查询桌台失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/admin/table/open', summary='餐厅端：开台')
def admin_table_open(body: TableOpenRequest) -> Dict[str, Any]:
    try:
        return db_tool.open_table(body.table_no)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('开台失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/admin/table/change', summary='餐厅端：换台')
def admin_table_change(body: TableChangeRequest) -> Dict[str, Any]:
    try:
        return db_tool.change_table(body.from_table_no, body.to_table_no)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('换台失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/admin/table/merge', summary='餐厅端：并台')
def admin_table_merge(body: TableChangeRequest) -> Dict[str, Any]:
    try:
        return db_tool.merge_table(body.from_table_no, body.to_table_no)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('并台失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/admin/table/close', summary='餐厅端：结账清台')
def admin_table_close(body: TableCloseRequest) -> Dict[str, Any]:
    try:
        return db_tool.close_table(body.table_no, settle=body.settle)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('结账清台失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get('/admin/inventory', summary='餐厅端：库存与补货提醒')
def admin_inventory() -> Dict[str, Any]:
    try:
        return db_tool.list_inventory()
    except Exception as exc:
        logger.exception('库存查询失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.patch('/admin/inventory/{ingredient_id}', summary='餐厅端：原料补货/调价')
def admin_inventory_update(ingredient_id: int,
                           body: InventoryUpdateRequest) -> Dict[str, Any]:
    try:
        return db_tool.update_ingredient(
            ingredient_id, add=body.add, stock=body.stock, threshold=body.threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('库存更新失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ================================================================ 会员（顾客端）

@app.get('/member/lookup', summary='顾客端：按手机号识别会员')
def member_lookup(phone: str = Query(..., description='11 位手机号')) -> Dict[str, Any]:
    try:
        member = db_tool.get_member_by_phone(phone)
        return {'member': member}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('会员查询失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/member/register', summary='顾客端：注册会员')
def member_register(req: MemberCreateRequest) -> Dict[str, Any]:
    try:
        return {'member': db_tool.create_member(req.phone, req.name)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('会员注册失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ================================================================ 会员（餐厅端）

@app.get('/admin/members', summary='餐厅端：会员列表/搜索')
def admin_members(keyword: Optional[str] = None) -> Dict[str, Any]:
    try:
        return db_tool.list_members(keyword)
    except Exception as exc:
        logger.exception('会员列表查询失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/admin/members', summary='餐厅端：新增会员')
def admin_member_create(req: MemberCreateRequest) -> Dict[str, Any]:
    try:
        return db_tool.create_member(req.phone, req.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('新增会员失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get('/admin/members/{member_id}', summary='餐厅端：会员详情与优惠券')
def admin_member_detail(member_id: int) -> Dict[str, Any]:
    try:
        return db_tool.get_member_detail(member_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('会员详情查询失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/admin/members/{member_id}/recharge', summary='餐厅端：会员充值')
def admin_member_recharge(member_id: int, body: RechargeRequest) -> Dict[str, Any]:
    try:
        return db_tool.recharge_member(member_id, body.amount)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('会员充值失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/admin/members/{member_id}/coupons', summary='餐厅端：发放优惠券')
def admin_member_coupon(member_id: int, body: CouponIssueRequest) -> Dict[str, Any]:
    try:
        return db_tool.issue_coupon(
            member_id, body.title, body.amount, body.min_spend, body.expire_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('发券失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/admin/menu', summary='餐厅端：新增菜品')
def admin_menu_create(body: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return db_tool.create_menu_item(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('新增菜品失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.patch('/admin/menu/{dish_id}', summary='餐厅端：更新菜品（上下架等）')
def admin_menu_update(dish_id: int, body: Dict[str, Any]) -> Dict[str, Any]:
    try:
        allowed = {'dish_name', 'price', 'description', 'category', 'spice_level',
                   'flavor', 'main_ingredients', 'cooking_method', 'is_vegetarian',
                   'allergens', 'image_url', 'is_available'}
        fields = {k: v for k, v in body.items() if k in allowed}
        fields = db_tool.validate_menu_fields(fields)
        if not fields:
            raise HTTPException(status_code=400, detail='没有可更新的字段')
        sets = ', '.join(f'{k} = %s' for k in fields)
        values = list(fields.values()) + [dish_id]
        from tools.db_tool import db_cursor
        with db_cursor(commit=True) as cursor:
            cursor.execute(
                f'UPDATE menu_items SET {sets}, updated_at = NOW() WHERE id = %s',
                values,
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail='菜品不存在')
        # 返回更新后的完整菜品
        dish = db_tool.get_dish_by_id(dish_id)
        return dish
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception('更新菜品失败')
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ================================================================ 公共

@app.get('/health')
def health(deep: bool = False) -> Dict[str, Any]:
    return service.health(deep=deep)


@app.delete('/session/{session_id}')
def clear_session(session_id: str) -> Dict[str, Any]:
    return {'cleared': service.clear_session(session_id), 'session_id': session_id}
