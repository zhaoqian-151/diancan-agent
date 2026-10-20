"""
数据库查询工具模块

该模块提供MySQL数据库连接和查询功能，
专门用于查询menu数据库中的menu_items表的全部信息

除菜单查询外，还封装了购物车与订单的读写，供上层 Agent 的工具调用。
"""

import logging
import math
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence

import mysql.connector
from mysql.connector import Error as MySqlError

from . import config

logger = logging.getLogger(__name__)

# 辣度等级文案，与 menu_items.spice_level 对应
SPICE_TEXT = {0: '不辣', 1: '微辣', 2: '中辣', 3: '重辣'}

# 订单状态文案，与 orders.status 对应
ORDER_STATUS_TEXT = {0: '待接单', 1: '已接单', 2: '配送中', 3: '已完成', 4: '已取消'}
DELIVERY_MODE_TEXT = {1: '到店自取', 2: '外卖配送'}

# 支付方式 / 支付状态文案，与 orders.payment_method、orders.payment_status 对应
PAYMENT_METHOD_TEXT = {1: '微信支付', 2: '支付宝', 3: '会员余额'}
PAYMENT_STATUS_TEXT = {0: '未支付', 1: '已支付'}
# 支持的支付方式：微信 / 支付宝 / 会员余额
_PAY_METHODS = {1, 2, 3}

# 会员等级 / 优惠券状态文案
MEMBER_LEVEL_TEXT = {1: '普通会员', 2: '银卡会员', 3: '金卡会员'}
COUPON_STATUS_TEXT = {0: '未使用', 1: '已使用', 2: '已过期'}

# menu_items 里要查的字段
_MENU_COLUMNS = (
    'id, dish_name, price, description, category, spice_level, flavor, '
    'main_ingredients, cooking_method, is_vegetarian, allergens, image_url, is_available'
)


class DatabaseError(RuntimeError):
    """数据库访问失败。"""


# ---------------------------------------------------------------- 连接

def get_connection():
    """新建一个 MySQL 连接。调用方负责关闭，或使用 db_cursor()。"""
    try:
        return mysql.connector.connect(
            host=config.MYSQL_HOST,
            port=config.MYSQL_PORT,
            user=config.MYSQL_USER_NAME,
            password=config.MYSQL_USER_PASSWORD,
            database=config.MYSQL_DB_NAME,
            charset=config.MYSQL_CHARSET,
            connection_timeout=10,
        )
    except MySqlError as exc:
        raise DatabaseError(
            f'连接 MySQL 失败（{config.MYSQL_HOST}:{config.MYSQL_PORT}/'
            f'{config.MYSQL_DB_NAME}）：{exc}'
        ) from exc


@contextmanager
def db_cursor(dictionary: bool = True, commit: bool = False):
    """连接 + 游标的上下文管理器，自动提交/回滚与关闭。"""
    conn = get_connection()
    cursor = conn.cursor(dictionary=dictionary)
    try:
        yield cursor
        if commit:
            conn.commit()
    except Exception:
        if commit:
            conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def check_connection() -> Dict[str, Any]:
    """连通性自检，返回服务器版本与菜单条数。"""
    with db_cursor() as cursor:
        cursor.execute('SELECT VERSION() AS version')
        version = cursor.fetchone()['version']
        cursor.execute('SELECT COUNT(*) AS total FROM menu_items')
        total = cursor.fetchone()['total']
    return {'ok': True, 'version': version, 'menu_count': total,
            'database': config.MYSQL_DB_NAME,
            'host': f'{config.MYSQL_HOST}:{config.MYSQL_PORT}'}


# ---------------------------------------------------------------- 格式化

def _to_float(value: Any) -> float:
    """DECIMAL 转 float，方便 JSON 序列化。"""
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def spice_text(level: Optional[int]) -> str:
    return SPICE_TEXT.get(int(level or 0), '不辣')


def format_price(value: Any) -> str:
    return f'¥{_to_float(value):.2f}'


def _normalize_dish(row: Dict[str, Any]) -> Dict[str, Any]:
    """把数据库行整理成统一结构，补上派生字段。"""
    dish = dict(row)
    dish['image_source'] = 'ai' if (dish.get('image_url') or '').startswith('/images/generated/') else 'merchant'
    dish['price'] = _to_float(dish.get('price'))
    dish['formatted_price'] = format_price(dish.get('price'))
    dish['spice_level'] = int(dish.get('spice_level') or 0)
    dish['spice_text'] = spice_text(dish['spice_level'])
    dish['is_vegetarian'] = bool(dish.get('is_vegetarian'))
    dish['is_available'] = bool(dish.get('is_available', 1))
    dish['allergens'] = (dish.get('allergens') or '').strip()
    dish['flavor'] = (dish.get('flavor') or '').strip()
    dish['main_ingredients'] = (dish.get('main_ingredients') or '').strip()
    dish['description'] = (dish.get('description') or '').strip()
    return dish


# ---------------------------------------------------------------- 菜单查询

def get_menu_items(
    category: Optional[str] = None,
    max_price: Optional[float] = None,
    min_price: Optional[float] = None,
    max_spice_level: Optional[int] = None,
    vegetarian_only: bool = False,
    keyword: Optional[str] = None,
    only_available: bool = True,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """按条件查询菜品，所有条件都是可选的，全部为空时返回整个菜单。"""
    sql = f'SELECT {_MENU_COLUMNS} FROM menu_items WHERE 1 = 1'
    params: List[Any] = []

    if only_available:
        sql += ' AND is_available = 1'
    if category:
        sql += ' AND category = %s'
        params.append(category)
    if max_price is not None:
        sql += ' AND price <= %s'
        params.append(max_price)
    if min_price is not None:
        sql += ' AND price >= %s'
        params.append(min_price)
    if max_spice_level is not None:
        sql += ' AND spice_level <= %s'
        params.append(max_spice_level)
    if vegetarian_only:
        sql += ' AND is_vegetarian = 1'
    if keyword:
        sql += (' AND (dish_name LIKE %s OR description LIKE %s '
                'OR flavor LIKE %s OR main_ingredients LIKE %s OR category LIKE %s)')
        like = f'%{keyword}%'
        params.extend([like] * 5)

    sql += ' ORDER BY price ASC, id ASC'
    if limit:
        sql += ' LIMIT %s'
        params.append(int(limit))

    with db_cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    return [_normalize_dish(row) for row in rows]


def get_menu_items_list() -> List[Dict[str, Any]]:
    """获取菜品列表（含下架菜品），由前端根据 is_available 渲染。"""
    return get_menu_items(only_available=False)


def validate_menu_fields(dish: Dict[str, Any]) -> Dict[str, Any]:
    dish = dict(dish)
    for key in ('dish_name', 'category'):
        if key in dish:
            value = str(dish[key] or '').strip()
            if not value or len(value) > 50:
                raise ValueError(f'{key} 必须填写且不超过 50 个字符')
            dish[key] = value
    if 'price' in dish:
        price = float(dish['price'])
        if not math.isfinite(price) or price <= 0 or price > 99999:
            raise ValueError('价格必须大于 0 且不超过 99999 元')
        dish['price'] = round(price, 2)
    if 'spice_level' in dish and dish['spice_level'] not in (0, 1, 2, 3):
        raise ValueError('辣度必须在 0 到 3 之间')
    if dish.get('image_url') and not str(dish['image_url']).startswith(('https://', '/images/')):
        raise ValueError('图片请使用 HTTPS 地址或本地 /images/ 路径')
    return dish


def create_menu_item(dish: Dict[str, Any]) -> Dict[str, Any]:
    """新增一道菜品并返回完整记录。

    必传：dish_name, price, category
    可选：description, spice_level, flavor, main_ingredients, cooking_method,
          is_vegetarian, allergens, image_url, is_available
    """
    dish = validate_menu_fields(dish)
    required = ('dish_name', 'price', 'category')
    missing = [k for k in required if not dish.get(k)]
    if missing:
        raise ValueError(f'缺少必填字段：{", ".join(missing)}')

    columns = [
        'dish_name', 'price', 'description', 'category', 'spice_level',
        'flavor', 'main_ingredients', 'cooking_method', 'is_vegetarian',
        'allergens', 'image_url', 'is_available',
    ]
    values = []
    for col in columns:
        v = dish.get(col)
        if v is None:
            v = {
                'description': '',
                'spice_level': 0,
                'flavor': '',
                'main_ingredients': '',
                'cooking_method': '',
                'is_vegetarian': 0,
                'allergens': '',
                'image_url': None,
                'is_available': 1,
            }.get(col, None)
        values.append(v)

    placeholders = ', '.join(['%s'] * len(columns))
    col_list = ', '.join(columns)
    with db_cursor(commit=True) as cursor:
        cursor.execute(
            f'INSERT INTO menu_items ({col_list}) VALUES ({placeholders})',
            values,
        )
        new_id = cursor.lastrowid
    return get_dish_by_id(new_id)


def get_dish_by_id(dish_id: int) -> Optional[Dict[str, Any]]:
    """按 ID 查单个菜品。"""
    with db_cursor() as cursor:
        cursor.execute(f'SELECT {_MENU_COLUMNS} FROM menu_items WHERE id = %s', (dish_id,))
        row = cursor.fetchone()
    return _normalize_dish(row) if row else None


def get_dishes_by_ids(dish_ids: Sequence[int]) -> List[Dict[str, Any]]:
    """按 ID 批量查菜品，返回顺序与 SQL 结果一致（按 id 升序）。"""
    ids = [int(i) for i in dish_ids]
    if not ids:
        return []
    placeholders = ', '.join(['%s'] * len(ids))
    with db_cursor() as cursor:
        cursor.execute(
            f'SELECT {_MENU_COLUMNS} FROM menu_items WHERE id IN ({placeholders}) ORDER BY id',
            ids,
        )
        rows = cursor.fetchall()
    return [_normalize_dish(row) for row in rows]


def get_categories() -> List[str]:
    """返回全部菜品分类。"""
    with db_cursor() as cursor:
        cursor.execute('SELECT DISTINCT category FROM menu_items ORDER BY category')
        rows = cursor.fetchall()
    return [row['category'] for row in rows]


def get_menu_summary_text(items: Optional[Iterable[Dict[str, Any]]] = None) -> str:
    """把菜单整理成一段纯文本，便于直接塞进大模型提示词。"""
    dishes = list(items) if items is not None else get_menu_items()
    if not dishes:
        return '当前没有可供应的菜品。'

    lines = []
    for dish in dishes:
        tags = [dish['category'], dish['spice_text']]
        # 分类本身可能就叫「素食」，避免重复打标签
        if dish['is_vegetarian'] and '素食' not in tags:
            tags.append('素食')
        if dish['allergens'] and dish['allergens'] not in ('无过敏源', '无'):
            tags.append(f"过敏原:{dish['allergens']}")
        lines.append(
            f"{dish['id']}. {dish['dish_name']} {dish['formatted_price']} "
            f"[{'/'.join(tags)}] {dish['description']}"
        )
    return '\n'.join(lines)


# ---------------------------------------------------------------- 购物车

def get_or_create_user(username: str, phone: Optional[str] = None) -> int:
    """按用户名取用户 ID，不存在则创建。"""
    with db_cursor(commit=True) as cursor:
        cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
        row = cursor.fetchone()
        if row:
            return int(row['id'])
        cursor.execute(
            'INSERT INTO users (username, password, phone) VALUES (%s, %s, %s) '
            'ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)',
            (username, '', phone),
        )
        return int(cursor.lastrowid)


def get_default_user_id() -> int:
    """默认演示用户，供前端未登录场景使用。"""
    return get_or_create_user('guest', None)


def add_to_cart(user_id: int, dish_id: int, quantity: int = 1) -> Dict[str, Any]:
    """加入购物车；已存在则累加数量。"""
    quantity = int(quantity)
    if quantity <= 0:
        raise ValueError('数量必须大于 0')

    dish = get_dish_by_id(dish_id)
    if not dish:
        raise ValueError(f'菜品不存在：id={dish_id}')
    if not dish['is_available']:
        raise ValueError(f"菜品「{dish['dish_name']}」当前不可供应")

    with db_cursor(commit=True) as cursor:
        cursor.execute(
            'SELECT id, quantity FROM shopping_cart WHERE user_id = %s AND dish_id = %s',
            (user_id, dish_id),
        )
        row = cursor.fetchone()
        if row:
            new_qty = int(row['quantity']) + quantity
            cursor.execute('UPDATE shopping_cart SET quantity = %s WHERE id = %s',
                           (new_qty, row['id']))
        else:
            new_qty = quantity
            cursor.execute(
                'INSERT INTO shopping_cart (user_id, dish_id, quantity) VALUES (%s, %s, %s)',
                (user_id, dish_id, quantity),
            )

    return {'dish_id': dish_id, 'dish_name': dish['dish_name'], 'quantity': new_qty,
            'unit_price': dish['price'], 'subtotal': round(dish['price'] * new_qty, 2)}


def set_cart_quantity(user_id: int, dish_id: int, quantity: int) -> Dict[str, Any]:
    """直接设置购物车中某道菜的数量；数量 <= 0 时移除该菜品。"""
    quantity = int(quantity)
    if quantity <= 0:
        remove_from_cart(user_id, dish_id)
        return {'dish_id': dish_id, 'quantity': 0, 'removed': True}

    dish = get_dish_by_id(dish_id)
    if not dish:
        raise ValueError(f'菜品不存在：id={dish_id}')

    with db_cursor(commit=True) as cursor:
        cursor.execute(
            'SELECT id FROM shopping_cart WHERE user_id = %s AND dish_id = %s',
            (user_id, dish_id),
        )
        row = cursor.fetchone()
        if row:
            cursor.execute('UPDATE shopping_cart SET quantity = %s WHERE id = %s',
                           (quantity, row['id']))
        else:
            cursor.execute(
                'INSERT INTO shopping_cart (user_id, dish_id, quantity) VALUES (%s, %s, %s)',
                (user_id, dish_id, quantity),
            )

    return {'dish_id': dish_id, 'dish_name': dish['dish_name'], 'quantity': quantity,
            'unit_price': dish['price'], 'subtotal': round(dish['price'] * quantity, 2)}


def get_cart(user_id: int) -> List[Dict[str, Any]]:
    """查看购物车内容。"""
    with db_cursor() as cursor:
        cursor.execute(
            'SELECT c.dish_id, c.quantity, m.dish_name, m.price '
            'FROM shopping_cart c JOIN menu_items m ON m.id = c.dish_id '
            'WHERE c.user_id = %s ORDER BY c.created_at',
            (user_id,),
        )
        rows = cursor.fetchall()

    cart = []
    for row in rows:
        price = _to_float(row['price'])
        qty = int(row['quantity'])
        cart.append({
            'dish_id': row['dish_id'],
            'dish_name': row['dish_name'],
            'quantity': qty,
            'unit_price': price,
            'formatted_price': format_price(price),
            'subtotal': round(price * qty, 2),
        })
    return cart


def remove_from_cart(user_id: int, dish_id: int) -> bool:
    """从购物车移除某道菜。"""
    with db_cursor(commit=True) as cursor:
        cursor.execute('DELETE FROM shopping_cart WHERE user_id = %s AND dish_id = %s',
                       (user_id, dish_id))
        return cursor.rowcount > 0


def clear_cart(user_id: int) -> int:
    """清空购物车，返回删除条数。"""
    with db_cursor(commit=True) as cursor:
        cursor.execute('DELETE FROM shopping_cart WHERE user_id = %s', (user_id,))
        return cursor.rowcount


def cart_total(user_id: int) -> Dict[str, Any]:
    """购物车合计。"""
    cart = get_cart(user_id)
    total = round(sum(item['subtotal'] for item in cart), 2)
    return {'items': cart, 'total_amount': total, 'formatted_total': format_price(total),
            'total_quantity': sum(item['quantity'] for item in cart)}


# ---------------------------------------------------------------- 订单

def _generate_order_no() -> str:
    return datetime.now().strftime('%Y%m%d%H%M%S%f')[:-3]


def create_order(
    user_id: int,
    contact_name: str,
    contact_phone: str,
    delivery_address: Optional[str],
    items: Optional[Sequence[Dict[str, Any]]] = None,
    delivery_distance: Optional[float] = None,
    delivery_mode: int = 2,
    table_no: Optional[str] = None,
    member_id: Optional[int] = None,
    coupon_id: Optional[int] = None,
) -> Dict[str, Any]:
    """创建订单。

    items 为空时直接下单购物车里的全部内容；
    items 形如 [{'dish_id': 1, 'quantity': 2}, ...]。
    delivery_mode：1-自取（地址可为空），2-外卖配送。
    member_id/coupon_id：会员下单时带入，coupon_id 需为该会员名下可用券。
    """
    if items is None:
        items = [{'dish_id': i['dish_id'], 'quantity': i['quantity']} for i in get_cart(user_id)]
    if not items:
        raise ValueError('购物车为空，无法下单')

    delivery_mode = 1 if int(delivery_mode) == 1 else 2
    order_no = _generate_order_no()
    lines, total_amount, total_quantity = [], 0.0, 0

    for item in items:
        dish = get_dish_by_id(int(item['dish_id']))
        if not dish:
            raise ValueError(f"菜品不存在：id={item['dish_id']}")
        if not dish.get('is_available', True):
            raise ValueError(f"菜品「{dish['dish_name']}」已估清，暂时无法下单")
        qty = int(item.get('quantity', 1))
        if qty <= 0:
            raise ValueError(f"菜品「{dish['dish_name']}」数量必须大于 0")
        subtotal = round(dish['price'] * qty, 2)
        total_amount = round(total_amount + subtotal, 2)
        total_quantity += qty
        lines.append((dish['id'], dish['dish_name'], qty, dish['price'], subtotal))

    # 会员与优惠券（未显式给 member_id 时，券一律不生效）
    member_id = int(member_id) if member_id else None
    coupon_id = int(coupon_id) if coupon_id else None
    discount_amount = 0.0

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if member_id:
            cursor.execute('SELECT id FROM members WHERE id = %s', (member_id,))
            if not cursor.fetchone():
                raise ValueError('会员不存在，请先注册会员')
        if coupon_id:
            if not member_id:
                raise ValueError('使用优惠券需先识别会员身份')
            discount_amount = _validate_coupon(cursor, member_id, coupon_id, total_amount)

        cursor.execute(
            'INSERT INTO orders (user_id, member_id, order_no, contact_name, contact_phone, '
            'delivery_address, delivery_mode, table_no, total_amount, discount_amount, coupon_id, '
            'total_quantity, status, delivery_distance) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s)',
            (user_id, member_id, order_no, contact_name, contact_phone, delivery_address,
             delivery_mode, table_no, total_amount, discount_amount, coupon_id,
             total_quantity, delivery_distance),
        )
        order_id = cursor.lastrowid
        cursor.executemany(
            'INSERT INTO order_items (order_id, dish_id, dish_name, quantity, '
            'unit_price, subtotal) VALUES (%s, %s, %s, %s, %s, %s)',
            [(order_id, d_id, d_name, qty, price, sub) for d_id, d_name, qty, price, sub in lines],
        )
        cursor.execute('DELETE FROM shopping_cart WHERE user_id = %s', (user_id,))
        # 库存和订单在同一事务中；不足或失败时全部回滚。
        _deduct_ingredients(cursor, lines)
        _refresh_dish_availability(cursor, [line[0] for line in lines])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    payable = round(total_amount - discount_amount, 2)
    return {
        'order_id': order_id,
        'order_no': order_no,
        'member_id': member_id,
        'total_amount': total_amount,
        'discount_amount': discount_amount,
        'payable_amount': payable,
        'formatted_total': format_price(payable),
        'total_quantity': total_quantity,
        'status': 0,
        'status_text': ORDER_STATUS_TEXT[0],
        'delivery_mode': delivery_mode,
        'delivery_mode_text': DELIVERY_MODE_TEXT[delivery_mode],
        'delivery_address': delivery_address,
        'table_no': table_no,
        'items': [
            {'dish_id': d_id, 'dish_name': d_name, 'quantity': qty,
             'unit_price': price, 'subtotal': sub}
            for d_id, d_name, qty, price, sub in lines
        ],
    }


def get_orders(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """查看用户的历史订单。"""
    with db_cursor() as cursor:
        cursor.execute(
            'SELECT id, order_no, contact_name, contact_phone, delivery_address, delivery_mode, '
            'table_no, total_amount, discount_amount, total_quantity, status, '
            'payment_method, payment_status, paid_at, delivery_distance, created_at '
            'FROM orders WHERE user_id = %s ORDER BY created_at DESC LIMIT %s',
            (user_id, int(limit)),
        )
        rows = cursor.fetchall()

    orders = [_normalize_order(row) for row in rows]
    items_map = get_order_items_map([o['order_id'] for o in orders])
    for order in orders:
        order['items'] = items_map.get(order['order_id'], [])
    return orders


def _normalize_order(row: Dict[str, Any]) -> Dict[str, Any]:
    """把 orders 行整理成统一结构，补上文案与格式化字段。"""
    mode = int(row['delivery_mode'] or 2)
    pay_status = int(row.get('payment_status') or 0)
    pay_method = row.get('payment_method')
    pay_method = int(pay_method) if pay_method is not None else None
    return {
        'order_id': row['id'],
        'order_no': row['order_no'],
        'contact_name': row['contact_name'],
        'contact_phone': row.get('contact_phone', ''),
        'delivery_address': row['delivery_address'],
        'delivery_mode': mode,
        'delivery_mode_text': DELIVERY_MODE_TEXT.get(mode, '外卖配送'),
        'table_no': row.get('table_no'),
        'total_amount': _to_float(row['total_amount']),
        'discount_amount': _to_float(row.get('discount_amount')),
        'payable_amount': round(_to_float(row['total_amount']) - _to_float(row.get('discount_amount')), 2),
        'formatted_total': format_price(_to_float(row['total_amount']) - _to_float(row.get('discount_amount'))),
        'total_quantity': int(row['total_quantity']),
        'status': int(row['status']),
        'status_text': ORDER_STATUS_TEXT.get(int(row['status']), '未知'),
        'payment_method': pay_method,
        'payment_method_text': PAYMENT_METHOD_TEXT.get(pay_method, '') if pay_method else '',
        'payment_status': pay_status,
        'payment_status_text': PAYMENT_STATUS_TEXT.get(pay_status, '未支付'),
        'paid_at': str(row['paid_at']) if row.get('paid_at') else None,
        'delivery_distance': _to_float(row['delivery_distance']) if row.get('delivery_distance') is not None else None,
        'created_at': str(row['created_at']),
    }


def pay_order(order_id: int, payment_method: int) -> Dict[str, Any]:
    """对订单发起支付：微信(1)、支付宝(2)、会员余额(3)。

    支付成功后：若订单用了优惠券则核销，会员按实付金额累加积分（1 元 = 1 分）。
    """
    method = int(payment_method)
    if method not in _PAY_METHODS:
        raise ValueError('不支持的支付方式')
    if method in (1, 2):
        raise ValueError('在线支付渠道尚未接入，订单已保留为待支付；请联系门店确认支付方式')

    with db_cursor(commit=True) as cursor:
        cursor.execute(
            'SELECT id, status, payment_status, total_amount, discount_amount, member_id, coupon_id '
            'FROM orders WHERE id = %s FOR UPDATE',
            (order_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError('订单不存在')
        if int(row['status']) == 4:
            raise ValueError('订单已取消，无法支付')
        if int(row['payment_status']) == 1:
            raise ValueError('该订单已支付，无需重复支付')

        payable = round(_to_float(row['total_amount']) - _to_float(row['discount_amount']), 2)
        member_id = row['member_id']
        coupon_id = row['coupon_id']
        if coupon_id:
            actual_discount = _validate_coupon(cursor, member_id, coupon_id, _to_float(row['total_amount']))
            if actual_discount != round(_to_float(row['discount_amount']), 2):
                raise ValueError('优惠券金额已变化，请联系门店处理')

        if method == 3:
            if not member_id:
                raise ValueError('该订单不是会员订单，无法使用余额支付')
            cursor.execute('SELECT balance FROM members WHERE id = %s FOR UPDATE', (member_id,))
            mrow = cursor.fetchone()
            if not mrow:
                raise ValueError('会员不存在')
            balance = _to_float(mrow['balance'])
            if balance < payable:
                raise ValueError(
                    f'会员余额不足（余额 ¥{balance:.2f}，应付 ¥{payable:.2f}），请改用微信或支付宝')
            cursor.execute(
                'UPDATE members SET balance = balance - %s, updated_at = NOW() WHERE id = %s',
                (payable, member_id),
            )

        cursor.execute(
            'UPDATE orders SET payment_method = %s, payment_status = 1, '
            'paid_at = NOW(), updated_at = NOW() WHERE id = %s',
            (method, order_id),
        )

        # 核销优惠券
        if coupon_id:
            cursor.execute(
                'UPDATE coupons SET status = 1 WHERE id = %s AND status = 0',
                (coupon_id,),
            )
        # 会员积分：实付 1 元积 1 分
        if member_id:
            earned = int(payable)
            if earned > 0:
                cursor.execute(
                    'UPDATE members SET points = points + %s, updated_at = NOW() WHERE id = %s',
                    (earned, member_id),
                )

    return {
        'order_id': order_id,
        'payment_method': method,
        'payment_method_text': PAYMENT_METHOD_TEXT.get(method, ''),
        'payment_status': 1,
        'payment_status_text': PAYMENT_STATUS_TEXT[1],
        'paid_amount': payable,
        'formatted_paid': format_price(payable),
    }


# ---------------------------------------------------------------- 经营报表

def update_order_status(order_id: int, status: int) -> Dict[str, Any]:
    with db_cursor(commit=True) as cursor:
        cursor.execute('SELECT status, payment_status, delivery_mode FROM orders WHERE id = %s FOR UPDATE', (order_id,))
        order = cursor.fetchone()
        if not order:
            raise ValueError('订单不存在')
        current = int(order['status'])
        if status == current:
            return {'order_id': order_id, 'status': status, 'status_text': ORDER_STATUS_TEXT[status]}
        transitions = {0: {1, 4}, 1: {2, 3}, 2: {3}, 3: set(), 4: set()}
        if status not in transitions[current]:
            raise ValueError('不能从当前订单状态跳转到该状态')
        if status == 4:
            if int(order['payment_status']) == 1:
                raise ValueError('已支付订单需先通过退款流程处理，当前暂不支持直接取消')
            cursor.execute('SELECT dish_id, dish_name, quantity, unit_price, subtotal FROM order_items WHERE order_id = %s', (order_id,))
            lines = [(r['dish_id'], r['dish_name'], -int(r['quantity']), r['unit_price'], r['subtotal']) for r in cursor.fetchall()]
            _deduct_ingredients(cursor, lines)
        elif not int(order['payment_status']):
            raise ValueError('订单尚未支付，不能进入制作或完成状态')
        if current == 1 and ((int(order['delivery_mode']) == 1 and status == 2) or (int(order['delivery_mode']) == 2 and status == 3)):
            raise ValueError('请按自取或配送流程推进订单')
        cursor.execute('UPDATE orders SET status = %s, updated_at = NOW() WHERE id = %s', (status, order_id))
    return {'order_id': order_id, 'status': status, 'status_text': ORDER_STATUS_TEXT[status]}

def report_summary() -> Dict[str, Any]:
    """经营数据看板：今日营业额、订单量、客单价、热销菜、分类占比。"""
    with db_cursor() as cursor:
        cursor.execute('SELECT CURDATE() AS day, NOW() AS generated_at')
        clock = cursor.fetchone()
        # 今日订单量（含未支付，反映进单量）
        cursor.execute('SELECT COUNT(*) AS cnt FROM orders WHERE DATE(created_at) = CURDATE()')
        today_orders = int(cursor.fetchone()['cnt'])

        # 今日已支付营业额
        cursor.execute(
            'SELECT IFNULL(SUM(total_amount - discount_amount), 0) AS amt, '
            'COUNT(*) AS cnt FROM orders '
            'WHERE payment_status = 1 AND status <> 4 AND DATE(paid_at) = CURDATE()'
        )
        paid = cursor.fetchone()
        revenue = round(_to_float(paid['amt']), 2)
        paid_orders = int(paid['cnt'])

        # 全部订单状态分布（用于看板概览，不限今日）
        cursor.execute('SELECT status, COUNT(*) AS cnt FROM orders WHERE DATE(created_at) = CURDATE() GROUP BY status')
        status_rows = cursor.fetchall()

        # 热销菜 TOP5（剔除已取消订单）
        cursor.execute(
            'SELECT oi.dish_name, SUM(oi.quantity) AS qty, SUM(oi.subtotal) AS amount '
            'FROM order_items oi JOIN orders o ON o.id = oi.order_id '
            'WHERE o.status <> 4 AND o.payment_status = 1 AND DATE(o.paid_at) = CURDATE() '
            'GROUP BY oi.dish_id, oi.dish_name '
            'ORDER BY qty DESC, amount DESC LIMIT 5'
        )
        top_rows = cursor.fetchall()

        # 分类占比（按金额）
        cursor.execute(
            'SELECT m.category AS category, SUM(oi.quantity) AS qty, SUM(oi.subtotal) AS amount '
            'FROM order_items oi '
            'JOIN menu_items m ON m.id = oi.dish_id '
            'JOIN orders o ON o.id = oi.order_id '
            'WHERE o.status <> 4 AND o.payment_status = 1 AND DATE(o.paid_at) = CURDATE() '
            'GROUP BY m.category ORDER BY amount DESC'
        )
        cat_rows = cursor.fetchall()
        cursor.execute(
            'SELECT DATE(paid_at) AS day, SUM(total_amount - discount_amount) AS amount, COUNT(*) AS cnt '
            'FROM orders WHERE payment_status = 1 AND status <> 4 '
            'AND paid_at >= CURDATE() - INTERVAL 6 DAY AND paid_at < CURDATE() + INTERVAL 1 DAY '
            'GROUP BY DATE(paid_at) ORDER BY day'
        )
        trend_map = {str(r['day']): r for r in cursor.fetchall()}
        cursor.execute('SELECT COUNT(*) AS cnt FROM orders WHERE status = 0 AND payment_status = 1')
        pending_orders = int(cursor.fetchone()['cnt'])

    top_dishes = [
        {'dish_name': r['dish_name'], 'quantity': int(r['qty']),
         'amount': round(_to_float(r['amount']), 2),
         'formatted_amount': format_price(r['amount'])}
        for r in top_rows
    ]
    total_cat_amount = sum(_to_float(r['amount']) for r in cat_rows) or 1.0
    categories = [
        {'category': r['category'], 'quantity': int(r['qty']),
         'amount': round(_to_float(r['amount']), 2),
         'formatted_amount': format_price(r['amount']),
         'ratio': round(_to_float(r['amount']) / total_cat_amount * 100, 1)}
        for r in cat_rows
    ]

    avg_price = round(revenue / paid_orders, 2) if paid_orders else 0.0
    return {
        'date': str(clock['day']),
        'generated_at': str(clock['generated_at']),
        'source': 'MySQL 业务库（包含初始化及测试记录，历史支付标记未经网关核验）',
        'scope': '数据库当地自然日；收入按支付日期，排除取消订单；菜品与分类金额为优惠前销售额',
        'pending_orders': pending_orders,
        'trend': [
            {'date': str(clock['day'] - timedelta(days=offset)),
             'revenue': round(_to_float(trend_map.get(str(clock['day'] - timedelta(days=offset)), {}).get('amount')), 2),
             'paid_orders': int(trend_map.get(str(clock['day'] - timedelta(days=offset)), {}).get('cnt', 0))}
            for offset in range(6, -1, -1)
        ],
        'today_orders': today_orders,
        'paid_orders': paid_orders,
        'revenue': revenue,
        'formatted_revenue': format_price(revenue),
        'avg_order_amount': avg_price,
        'formatted_avg': format_price(avg_price),
        'status_distribution': [
            {'status': int(r['status']),
             'status_text': ORDER_STATUS_TEXT.get(int(r['status']), '未知'),
             'count': int(r['cnt'])}
            for r in status_rows
        ],
        'top_dishes': top_dishes,
        'category_ratio': categories,
    }


# ---------------------------------------------------------------- 后厨分单

# 档口映射：按菜品分类把订单拆给不同档口
STATION_RULES = (
    ('凉菜档', ('凉菜', '凉拌', '小吃', '拼盘', '卤味')),
    ('饮品档', ('饮品', '酒水', '饮料', '茶饮', '果汁')),
)
DEFAULT_STATION = '热菜档'
# 后厨大屏展示的档口顺序
STATION_ORDER = ('热菜档', '凉菜档', '饮品档')

# 桌台状态文案，与 tables.status 对应
TABLE_STATUS_TEXT = {0: '空闲', 1: '占用', 2: '预订'}


def station_of_category(category: Optional[str]) -> str:
    """按菜品分类判断该菜属于哪个档口。"""
    cat = (category or '').strip()
    for station, keywords in STATION_RULES:
        if any(k in cat for k in keywords):
            return station
    return DEFAULT_STATION


def get_order_items_map(order_ids: Sequence[int]) -> Dict[int, List[Dict[str, Any]]]:
    """批量取多个订单的菜品明细（含所属档口）。"""
    ids = [int(i) for i in order_ids]
    if not ids:
        return {}
    placeholders = ', '.join(['%s'] * len(ids))
    with db_cursor() as cursor:
        cursor.execute(
            f'SELECT oi.order_id, oi.dish_id, oi.dish_name, oi.quantity, oi.unit_price, oi.subtotal, m.category '
            f'FROM order_items oi LEFT JOIN menu_items m ON m.id = oi.dish_id '
            f'WHERE oi.order_id IN ({placeholders}) ORDER BY oi.id',
            ids,
        )
        rows = cursor.fetchall()

    result: Dict[int, List[Dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(int(row['order_id']), []).append({
            'dish_id': row['dish_id'],
            'unit_price': _to_float(row['unit_price']),
            'subtotal': _to_float(row['subtotal']),
            'dish_name': row['dish_name'],
            'quantity': int(row['quantity']),
            'station': station_of_category(row['category']),
        })
    return result


def get_kitchen_orders() -> Dict[str, Any]:
    """后厨大屏数据：把待处理订单按档口分组。

    只取「待接单(0) / 已接单(1)」的订单，即还需要后厨出餐的单子。
    """
    with db_cursor() as cursor:
        cursor.execute(
            'SELECT o.id AS order_id, o.order_no, o.contact_name, o.delivery_mode, '
            'o.table_no, o.status, o.created_at, '
            'oi.dish_name, oi.quantity, m.category '
            'FROM orders o '
            'JOIN order_items oi ON oi.order_id = o.id '
            'LEFT JOIN menu_items m ON m.id = oi.dish_id '
            'WHERE o.status IN (0, 1) AND o.payment_status = 1 '
            'ORDER BY o.created_at ASC, oi.id ASC'
        )
        rows = cursor.fetchall()

    orders: Dict[int, Dict[str, Any]] = {}
    # Keep configured stations visible even when the kitchen has no paid orders.
    stations: Dict[str, Dict[str, Any]] = {
        station: {'station': station, 'orders': [], 'total_quantity': 0}
        for station in STATION_ORDER
    }
    station_orders: Dict[Tuple[str, int], Dict[str, Any]] = {}
    seen: Dict[str, set] = {}

    for row in rows:
        oid = int(row['order_id'])
        station = station_of_category(row['category'])
        order = orders.get(oid)
        if order is None:
            mode = int(row['delivery_mode'] or 2)
            order = {
                'order_id': oid,
                'order_no': row['order_no'],
                'contact_name': row['contact_name'],
                'table_no': row['table_no'],
                'delivery_mode': mode,
                'delivery_mode_text': DELIVERY_MODE_TEXT.get(mode, '外卖配送'),
                'status': int(row['status']),
                'status_text': ORDER_STATUS_TEXT.get(int(row['status']), ''),
                'created_at': str(row['created_at']),
                'created_ts': row['created_at'].timestamp() if hasattr(row['created_at'], 'timestamp') else 0,
                'items': [],
            }
            orders[oid] = order

        order['items'].append({
            'dish_name': row['dish_name'],
            'quantity': int(row['quantity']),
            'station': station,
        })

        bucket = stations.setdefault(station, {
            'station': station, 'orders': [], 'total_quantity': 0,
        })
        if oid not in seen.setdefault(station, set()):
            seen[station].add(oid)
            # Each station receives only its own items; do not share the full
            # order object between stations (which duplicated preparation work).
            station_orders[(station, oid)] = {**order, 'items': []}
            bucket['orders'].append(station_orders[(station, oid)])
        station_orders[(station, oid)]['items'].append({
            'dish_name': row['dish_name'],
            'quantity': int(row['quantity']),
            'station': station,
        })
        bucket['total_quantity'] += int(row['quantity'])

    ordered = [stations[s] for s in STATION_ORDER if s in stations]
    # 兜底：出现规则外的档口也一并展示
    ordered += [v for k, v in stations.items() if k not in STATION_ORDER]

    return {
        'stations': ordered,
        'total_orders': len(orders),
        'total_quantity': sum(int(r['quantity']) for r in rows),
    }


# ---------------------------------------------------------------- 桌台管理

def _get_table(cursor, table_no: str) -> Optional[Dict[str, Any]]:
    cursor.execute(
        'SELECT id, table_no, seats, status, current_order_id FROM tables WHERE table_no = %s',
        (table_no,),
    )
    return cursor.fetchone()


def list_tables() -> List[Dict[str, Any]]:
    """全部桌台列表。"""
    with db_cursor() as cursor:
        cursor.execute(
            'SELECT id, table_no, seats, status, current_order_id FROM tables ORDER BY table_no'
        )
        rows = cursor.fetchall()
    return [
        {
            'id': row['id'],
            'table_no': row['table_no'],
            'seats': int(row['seats']),
            'status': int(row['status']),
            'status_text': TABLE_STATUS_TEXT.get(int(row['status']), '空闲'),
            'current_order_id': row['current_order_id'],
        }
        for row in rows
    ]


def open_table(table_no: str) -> Dict[str, Any]:
    """开台：把桌台置为占用。"""
    with db_cursor(commit=True) as cursor:
        row = _get_table(cursor, table_no)
        if not row:
            raise ValueError(f'桌台不存在：{table_no}')
        if int(row['status']) == 1:
            raise ValueError(f'桌台 {table_no} 已是占用状态')
        cursor.execute(
            'UPDATE tables SET status = 1, updated_at = NOW() WHERE id = %s', (row['id'],))
    return {'table_no': table_no, 'status': 1, 'status_text': TABLE_STATUS_TEXT[1]}


def change_table(from_no: str, to_no: str) -> Dict[str, Any]:
    """换台：把 A 桌的订单挪到 B 桌，A 恢复空闲。"""
    if from_no == to_no:
        raise ValueError('换台的目标桌台不能是当前桌台')
    with db_cursor(commit=True) as cursor:
        src = _get_table(cursor, from_no)
        dst = _get_table(cursor, to_no)
        if not src:
            raise ValueError(f'桌台不存在：{from_no}')
        if not dst:
            raise ValueError(f'桌台不存在：{to_no}')
        if int(dst['status']) == 1:
            raise ValueError(f'目标桌台 {to_no} 已被占用，无法换台')
        cursor.execute(
            'UPDATE orders SET table_no = %s, updated_at = NOW() '
            'WHERE table_no = %s AND status IN (0, 1)',
            (to_no, from_no),
        )
        cursor.execute(
            'UPDATE tables SET status = 1, current_order_id = %s, updated_at = NOW() WHERE id = %s',
            (src['current_order_id'], dst['id']),
        )
        cursor.execute(
            'UPDATE tables SET status = 0, current_order_id = NULL, updated_at = NOW() WHERE id = %s',
            (src['id'],),
        )
    return {'from': from_no, 'to': to_no, 'moved': True}


def merge_table(from_no: str, to_no: str) -> Dict[str, Any]:
    """并台：把 A 桌的订单并入 B 桌，A 恢复空闲。"""
    if from_no == to_no:
        raise ValueError('并台的目标桌台不能是当前桌台')
    with db_cursor(commit=True) as cursor:
        src = _get_table(cursor, from_no)
        dst = _get_table(cursor, to_no)
        if not src:
            raise ValueError(f'桌台不存在：{from_no}')
        if not dst:
            raise ValueError(f'桌台不存在：{to_no}')
        cursor.execute(
            'UPDATE orders SET table_no = %s, updated_at = NOW() '
            'WHERE table_no = %s AND status IN (0, 1)',
            (to_no, from_no),
        )
        cursor.execute(
            'UPDATE tables SET status = 1, updated_at = NOW() WHERE id = %s', (dst['id'],))
        cursor.execute(
            'UPDATE tables SET status = 0, current_order_id = NULL, updated_at = NOW() WHERE id = %s',
            (src['id'],),
        )
    return {'from': from_no, 'to': to_no, 'merged': True}


def close_table(table_no: str, settle: bool = True) -> Dict[str, Any]:
    """结账清台：把该桌未完成订单置为已完成，桌台恢复空闲。"""
    with db_cursor(commit=True) as cursor:
        row = _get_table(cursor, table_no)
        if not row:
            raise ValueError(f'桌台不存在：{table_no}')
        settled = 0
        if settle:
            cursor.execute('SELECT id FROM orders WHERE table_no = %s AND status NOT IN (3, 4) AND payment_status = 0 FOR UPDATE', (table_no,))
            if cursor.fetchall():
                raise ValueError('该桌存在待支付订单，请先处理订单后再清台')
            cursor.execute(
                'UPDATE orders SET status = 3, updated_at = NOW() '
                'WHERE table_no = %s AND status NOT IN (3, 4)',
                (table_no,),
            )
            settled = int(cursor.rowcount)
        cursor.execute(
            'UPDATE tables SET status = 0, current_order_id = NULL, updated_at = NOW() WHERE id = %s',
            (row['id'],),
        )
    return {'table_no': table_no, 'settled_orders': settled,
            'status': 0, 'status_text': TABLE_STATUS_TEXT[0]}


# ---------------------------------------------------------------- 库存 / 估清

def _deduct_ingredients(cursor, lines: Sequence[tuple]) -> None:
    """按订单菜品扣减原料库存。lines 形如 [(dish_id, dish_name, qty, price, sub), ...]。"""
    if not lines:
        return
    need_by_dish: Dict[int, int] = {}
    for line in lines:
        need_by_dish[int(line[0])] = need_by_dish.get(int(line[0]), 0) + int(line[2])
    dish_ids = list(need_by_dish.keys())
    placeholders = ', '.join(['%s'] * len(dish_ids))
    cursor.execute(
        f'SELECT dish_id, ingredient_id, quantity FROM dish_ingredients '
        f'WHERE dish_id IN ({placeholders})',
        dish_ids,
    )
    rows = cursor.fetchall()
    consume: Dict[int, float] = {}
    for row in rows:
        qty = need_by_dish.get(int(row['dish_id']), 0)
        amount = float(row['quantity']) * qty
        consume[int(row['ingredient_id'])] = consume.get(int(row['ingredient_id']), 0.0) + amount
    for ing_id, amount in sorted(consume.items()):
        cursor.execute(
            'UPDATE ingredients SET stock = stock - %s, updated_at = NOW() '
            'WHERE id = %s AND stock >= %s',
            (round(amount, 2), ing_id, round(amount, 2)),
        )
        if cursor.rowcount != 1:
            raise ValueError('原料库存不足，无法完成该订单，请减少数量或选择其他菜品')


def _refresh_dish_availability(cursor, dish_ids: Optional[Sequence[int]] = None) -> None:
    """根据原料库存刷新菜品是否可供应：库存不足以做 1 份即估清下架。"""
    sql = ('SELECT di.dish_id AS dish_id, di.quantity AS per, i.stock AS stock '
           'FROM dish_ingredients di JOIN ingredients i ON i.id = di.ingredient_id')
    params: List[Any] = []
    if dish_ids:
        ids = [int(i) for i in dish_ids]
        placeholders = ', '.join(['%s'] * len(ids))
        sql += f' WHERE di.dish_id IN ({placeholders})'
        params = ids
    cursor.execute(sql, params)
    rows = cursor.fetchall()

    max_pcs: Dict[int, int] = {}
    for row in rows:
        per = float(row['per'])
        if per <= 0:
            continue
        can_make = int(float(row['stock']) // per)
        dish_id = int(row['dish_id'])
        max_pcs[dish_id] = min(max_pcs.get(dish_id, 10 ** 9), can_make)

    for dish_id, can_make in max_pcs.items():
        # 自动估清只下架；补货不会擅自重新上架商家手动停售的菜。
        if can_make >= 1:
            continue
        cursor.execute(
            'UPDATE menu_items SET is_available = %s, updated_at = NOW() WHERE id = %s',
            (0, dish_id),
        )


def list_inventory() -> Dict[str, Any]:
    """原料库存列表 + 补货提醒。"""
    with db_cursor() as cursor:
        cursor.execute(
            'SELECT id, name, unit, stock, threshold FROM ingredients '
            'ORDER BY (stock <= threshold) DESC, stock ASC, name ASC'
        )
        ing_rows = cursor.fetchall()
        cursor.execute(
            'SELECT di.ingredient_id, m.dish_name FROM dish_ingredients di '
            'JOIN menu_items m ON m.id = di.dish_id ORDER BY m.dish_name'
        )
        map_rows = cursor.fetchall()

    dish_map: Dict[int, List[str]] = {}
    for row in map_rows:
        dish_map.setdefault(int(row['ingredient_id']), []).append(row['dish_name'])

    ingredients = []
    low_stock = []
    for row in ing_rows:
        stock = _to_float(row['stock'])
        threshold = _to_float(row['threshold'])
        item = {
            'id': row['id'],
            'name': row['name'],
            'unit': row['unit'],
            'stock': round(stock, 2),
            'threshold': round(threshold, 2),
            'low': stock <= threshold,
            'dishes': dish_map.get(int(row['id']), []),
        }
        ingredients.append(item)
        if item['low']:
            low_stock.append(item)

    return {
        'ingredients': ingredients,
        'low_stock': low_stock,
        'total': len(ingredients),
        'low_count': len(low_stock),
    }


def update_ingredient(ingredient_id: int, add: Optional[float] = None,
                      stock: Optional[float] = None,
                      threshold: Optional[float] = None) -> Dict[str, Any]:
    """补货 / 调整原料：add 为增量补货，stock 为直接设定，threshold 为预警阈值。"""
    if add is not None and stock is not None:
        raise ValueError('补货量和直接库存不能同时提交')
    if any(v is not None and (not math.isfinite(v) or v < 0) for v in (add, stock, threshold)):
        raise ValueError('库存及预警阈值必须为非负有限数值')
    sets: List[str] = []
    values: List[Any] = []
    if add is not None:
        sets.append('stock = GREATEST(stock + %s, 0)')
        values.append(float(add))
    if stock is not None:
        sets.append('stock = %s')
        values.append(max(float(stock), 0))
    if threshold is not None:
        sets.append('threshold = %s')
        values.append(max(float(threshold), 0))
    if not sets:
        raise ValueError('没有需要更新的字段')

    with db_cursor(commit=True) as cursor:
        cursor.execute(
            f'UPDATE ingredients SET {", ".join(sets)}, updated_at = NOW() WHERE id = %s',
            values + [ingredient_id],
        )
        if cursor.rowcount == 0:
            raise ValueError('原料不存在')
        # 补货后重新评估用到该原料的菜品是否可恢复供应
        cursor.execute(
            'SELECT dish_id FROM dish_ingredients WHERE ingredient_id = %s', (ingredient_id,))
        dish_ids = [int(r['dish_id']) for r in cursor.fetchall()]
        _refresh_dish_availability(cursor, dish_ids)
        cursor.execute(
            'SELECT id, name, unit, stock, threshold FROM ingredients WHERE id = %s',
            (ingredient_id,),
        )
        row = cursor.fetchone()

    stock_v = _to_float(row['stock'])
    threshold_v = _to_float(row['threshold'])
    return {
        'id': row['id'],
        'name': row['name'],
        'unit': row['unit'],
        'stock': round(stock_v, 2),
        'threshold': round(threshold_v, 2),
        'low': stock_v <= threshold_v,
        'affected_dishes': dish_ids,
    }


# ---------------------------------------------------------------- 会员 / 优惠券

def _validate_coupon(cursor, member_id: int, coupon_id: int,
                     total_amount: float) -> float:
    """校验优惠券是否可用，返回可抵扣金额（不修改券状态，支付成功时才核销）。"""
    cursor.execute(
        'SELECT id, amount, min_spend, status, expire_at FROM coupons '
        'WHERE id = %s AND member_id = %s FOR UPDATE',
        (int(coupon_id), int(member_id)),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError('优惠券不存在或不属于该会员')
    if int(row['status']) != 0:
        raise ValueError('该优惠券已使用或已过期')
    if row['expire_at'] is not None and row['expire_at'] < datetime.now():
        raise ValueError('该优惠券已过期')
    min_spend = _to_float(row['min_spend'])
    if total_amount + 1e-9 < min_spend:
        raise ValueError(f'该优惠券需订单满 ¥{min_spend:.2f} 才能使用')
    amount = _to_float(row['amount'])
    return round(min(amount, total_amount), 2)


def _normalize_coupon(row: Dict[str, Any]) -> Dict[str, Any]:
    status = int(row['status'])
    expire_at = row.get('expire_at')
    return {
        'id': row['id'],
        'member_id': row.get('member_id'),
        'title': row['title'],
        'amount': round(_to_float(row['amount']), 2),
        'min_spend': round(_to_float(row['min_spend']), 2),
        'status': status,
        'status_text': COUPON_STATUS_TEXT.get(status, '未知'),
        'expire_at': str(expire_at) if expire_at else None,
        'expire_text': f'有效期至 {expire_at:%Y-%m-%d}' if expire_at else '长期有效',
    }


def _normalize_member(row: Dict[str, Any], coupon_count: int = 0) -> Dict[str, Any]:
    level = int(row.get('level') or 1)
    return {
        'id': row['id'],
        'phone': row['phone'],
        'name': row.get('name'),
        'balance': round(_to_float(row.get('balance')), 2),
        'points': int(row.get('points') or 0),
        'level': level,
        'level_text': MEMBER_LEVEL_TEXT.get(level, '普通会员'),
        'birthday': str(row['birthday']) if row.get('birthday') else None,
        'coupon_count': coupon_count,
        'created_at': str(row['created_at']) if row.get('created_at') else None,
    }


def list_members(keyword: Optional[str] = None) -> Dict[str, Any]:
    """会员列表，可按手机号/姓名模糊搜索，并附带每人可用券数量。"""
    sql = (
        'SELECT m.id, m.phone, m.name, m.balance, m.points, m.level, '
        'm.birthday, m.created_at, '
        '(SELECT COUNT(*) FROM coupons c WHERE c.member_id = m.id AND c.status = 0 '
        ' AND (c.expire_at IS NULL OR c.expire_at > NOW())) AS coupon_count '
        'FROM members m'
    )
    params: List[Any] = []
    if keyword:
        sql += ' WHERE m.phone LIKE %s OR m.name LIKE %s'
        like = f'%{keyword.strip()}%'
        params = [like, like]
    sql += ' ORDER BY m.created_at DESC'
    with db_cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    members = [_normalize_member(r, int(r['coupon_count'])) for r in rows]
    return {'members': members, 'total': len(members)}


def get_member_detail(member_id: int) -> Dict[str, Any]:
    """会员详情 + 名下全部优惠券。"""
    with db_cursor() as cursor:
        cursor.execute(
            'SELECT id, phone, name, balance, points, level, birthday, created_at '
            'FROM members WHERE id = %s',
            (int(member_id),),
        )
        mrow = cursor.fetchone()
        if not mrow:
            raise ValueError('会员不存在')
        cursor.execute(
            'SELECT id, member_id, title, amount, min_spend, status, expire_at '
            'FROM coupons WHERE member_id = %s ORDER BY status ASC, expire_at IS NULL, expire_at ASC',
            (int(member_id),),
        )
        coupons = [_normalize_coupon(r) for r in cursor.fetchall()]
        usable = sum(1 for c in coupons if c['status'] == 0)
    member = _normalize_member(mrow, usable)
    member['coupons'] = coupons
    return member


def get_member_by_phone(phone: str) -> Optional[Dict[str, Any]]:
    """顾客端：按手机号识别会员，返回余额/积分与当前可用券。"""
    phone = (phone or '').strip()
    if not phone:
        return None
    with db_cursor() as cursor:
        cursor.execute(
            'SELECT id, phone, name, balance, points, level, birthday, created_at '
            'FROM members WHERE phone = %s',
            (phone,),
        )
        mrow = cursor.fetchone()
        if not mrow:
            return None
        cursor.execute(
            'SELECT id, member_id, title, amount, min_spend, status, expire_at '
            'FROM coupons WHERE member_id = %s AND status = 0 '
            'AND (expire_at IS NULL OR expire_at > NOW()) '
            'ORDER BY amount DESC, min_spend ASC',
            (mrow['id'],),
        )
        coupons = [_normalize_coupon(r) for r in cursor.fetchall()]
    member = _normalize_member(mrow, len(coupons))
    member['usable_coupons'] = coupons
    return member


def create_member(phone: str, name: Optional[str] = None) -> Dict[str, Any]:
    """注册新会员；手机号已存在时直接报错（由上层决定是否改为查询）。"""
    phone = (phone or '').strip()
    if not (phone.isdigit() and len(phone) == 11 and phone.startswith('1')):
        raise ValueError('请输入正确的 11 位手机号')
    with db_cursor(commit=True) as cursor:
        cursor.execute('SELECT id FROM members WHERE phone = %s', (phone,))
        if cursor.fetchone():
            raise ValueError('该手机号已是会员，无需重复注册')
        cursor.execute(
            'INSERT INTO members (phone, name, points, balance, level) VALUES (%s, %s, 0, 0, 1)',
            (phone, (name or None)),
        )
        new_id = cursor.lastrowid
        cursor.execute(
            'SELECT id, phone, name, balance, points, level, birthday, created_at '
            'FROM members WHERE id = %s',
            (new_id,),
        )
        mrow = cursor.fetchone()
    return _normalize_member(mrow, 0)


def recharge_member(member_id: int, amount: float) -> Dict[str, Any]:
    """会员余额充值（管理员操作）。"""
    amount = float(amount)
    if amount <= 0:
        raise ValueError('充值金额必须大于 0')
    with db_cursor(commit=True) as cursor:
        cursor.execute(
            'UPDATE members SET balance = balance + %s, updated_at = NOW() WHERE id = %s',
            (amount, int(member_id)),
        )
        if cursor.rowcount == 0:
            raise ValueError('会员不存在')
        cursor.execute(
            'SELECT id, phone, name, balance, points, level, birthday, created_at '
            'FROM members WHERE id = %s',
            (int(member_id),),
        )
        mrow = cursor.fetchone()
    return _normalize_member(mrow)


def issue_coupon(member_id: int, title: str, amount: float,
                 min_spend: float = 0, expire_days: int = 30) -> Dict[str, Any]:
    """给会员发放一张优惠券。"""
    title = (title or '').strip()
    if not title:
        raise ValueError('请填写优惠券名称')
    amount = float(amount)
    if amount <= 0:
        raise ValueError('抵扣金额必须大于 0')
    min_spend = max(float(min_spend or 0), 0)
    expire_days = int(expire_days or 0)
    with db_cursor(commit=True) as cursor:
        cursor.execute('SELECT id FROM members WHERE id = %s', (int(member_id),))
        if not cursor.fetchone():
            raise ValueError('会员不存在')
        expire_sql = 'DATE_ADD(NOW(), INTERVAL %s DAY)' if expire_days > 0 else 'NULL'
        cursor.execute(
            f'INSERT INTO coupons (member_id, title, amount, min_spend, status, expire_at) '
            f'VALUES (%s, %s, %s, %s, 0, {expire_sql})',
            (int(member_id), title, amount, min_spend) if expire_days <= 0
            else (int(member_id), title, amount, min_spend, expire_days),
        )
        new_id = cursor.lastrowid
        cursor.execute(
            'SELECT id, member_id, title, amount, min_spend, status, expire_at '
            'FROM coupons WHERE id = %s',
            (new_id,),
        )
        crow = cursor.fetchone()
    return _normalize_coupon(crow)
