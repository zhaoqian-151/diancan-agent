"""验证 tools/db_tool.py 与 tools/amap_tool.py。"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(message)s')

from tools import amap_tool, config, db_tool  # noqa: E402

print('=' * 60)
print('db_tool 验证')
print('=' * 60)

print('\n=== 1) 连接自检 ===')
print(' ', db_tool.check_connection())

print('\n=== 2) 全部菜品（前端列表接口的数据源）===')
for dish in db_tool.get_menu_items_list():
    print(f"  {dish['id']}  {dish['dish_name']:<8} {dish['formatted_price']:>8}  "
          f"{dish['category']:<4} {dish['spice_text']:<4} "
          f"素食={'是' if dish['is_vegetarian'] else '否'}")

print('\n=== 3) 条件筛选 ===')
print('  素食:', [d['dish_name'] for d in db_tool.get_menu_items(vegetarian_only=True)])
print('  辣度<=1:', [d['dish_name'] for d in db_tool.get_menu_items(max_spice_level=1)])
print('  价格<=20:', [d['dish_name'] for d in db_tool.get_menu_items(max_price=20)])
print('  关键词"豆腐":', [d['dish_name'] for d in db_tool.get_menu_items(keyword='豆腐')])
print('  分类列表:', db_tool.get_categories())

print('\n=== 4) 拼给大模型看的菜单文本 ===')
print(db_tool.get_menu_summary_text()[:400])

print('\n=== 5) 购物车读写 ===')
user_id = db_tool.get_default_user_id()
print('  演示用户 user_id =', user_id)
db_tool.clear_cart(user_id)
db_tool.add_to_cart(user_id, 1, 2)
db_tool.add_to_cart(user_id, 3, 1)
db_tool.add_to_cart(user_id, 1, 1)   # 应累加为 3
total = db_tool.cart_total(user_id)
for item in total['items']:
    print(f"  {item['dish_name']:<8} x{item['quantity']}  小计 {item['subtotal']}")
print(f"  合计 {total['formatted_total']}，共 {total['total_quantity']} 件")

print('\n=== 6) 下单 ===')
order = db_tool.create_order(
    user_id=user_id,
    contact_name='测试用户',
    contact_phone='13800000000',
    delivery_address='重庆市大渡口区兴海路204号',
    delivery_distance=1.5,
)
print(f"  订单号 {order['order_no']}  金额 {order['formatted_total']}  "
      f"状态 {order['status_text']}  共 {order['total_quantity']} 件")
print('  购物车已清空:', db_tool.get_cart(user_id) == [])

print('\n=== 7) 历史订单 ===')
for record in db_tool.get_orders(user_id, limit=3):
    print(f"  {record['order_no']}  {record['formatted_total']:>8}  "
          f"{record['status_text']}  {record['created_at']}")

print()
print('=' * 60)
print('amap_tool 验证')
print('=' * 60)

print('\n=== 1) 本店信息 ===')
for key, value in amap_tool.get_merchant_info().items():
    print(f'  {key:<22} {value}')

print('\n=== 2) 地理编码 ===')
for address in ['重庆市大渡口区九宫庙', '重庆市渝中区解放碑', '北京市海淀区中关村大街1号']:
    result = amap_tool.geocode(address)
    if result['success']:
        print(f"  {address:<22} -> {result['location']}  {result['formatted_address']}")
    else:
        print(f"  {address:<22} -> 失败：{result['message']}")

print('\n=== 3) 逆地理编码 ===')
print(' ', amap_tool.regeocode(config.MERCHANT_LONGITUDE, config.MERCHANT_LATITUDE))

print('\n=== 4) 路径规划（三种出行方式）===')
for mode in (1, 2, 3):
    route = amap_tool.get_route('重庆市大渡口区茄子溪', mode=mode)
    if route['success']:
        print(f"  {route['travel_mode_text']:<4} {route['distance_m']:>6} 米  "
              f"{route['duration_s']:>5} 秒  -> {route['formatted_address']}")
    else:
        print(f"  {route['travel_mode_text']:<4} 失败：{route['message']}")

print('\n=== 5) 配送范围判定（前端接口契约）===')
for address in ['重庆市大渡口区茄子溪',
                '重庆市大渡口区九宫庙',
                '重庆市渝中区解放碑',
                '上海市黄浦区外滩',
                '不存在的地址乱码xyz']:
    result = amap_tool.check_delivery_range(address, travel_mode=3)
    print(f"\n  查询：{address}")
    print(f"    success={result['success']}  in_range={result['in_range']}  "
          f"distance={result['distance']} (公里)  duration={result['duration']} (秒)")
    print(f"    formatted_address={result['formatted_address']}")
    print(f"    message={result['message']}")

print('\n=== 6) 前端会怎么渲染（模拟 App.vue 取值）===')
result = amap_tool.check_delivery_range('重庆市大渡口区茄子溪', travel_mode=2)
if result['distance']:
    print(f"  距离: {result['distance']:.2f} 公里")
    print(f"  时间: {result['duration'] // 60} 分钟 {result['duration'] % 60} 秒")
print(f"  地址: {result['formatted_address']}")
print(f"  提示类型: {'success' if result['in_range'] else 'warning'}")

print()
print('db_tool 与 amap_tool 验证完成')