"""Read real APIs and validate real MySQL transactions with forced rollback."""
import argparse
import json
import math
import sys
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import db_tool

parser = argparse.ArgumentParser()
parser.add_argument('--external', action='store_true', help='Also call configured AI, vector and map services')
args = parser.parse_args()
results = []


def record(name, detail):
    results.append({'name': name, 'passed': True, 'detail': detail})
    print(f'PASS: {name}', flush=True)


with httpx.Client(base_url='http://127.0.0.1:3000/api', timeout=120, trust_env=False) as client:
    for route in ['/health', '/shop', '/menu/list', '/cart', '/order/list', '/admin/orders', '/admin/reports/summary', '/admin/inventory', '/admin/tables', '/admin/members', '/admin/kitchen']:
        response = client.get(route)
        response.raise_for_status()
        body = response.json()
        if route == '/health':
            assert body['checks']['mysql']['ok']
        record(f'API {route}', response.status_code)

    summary = client.get('/admin/reports/summary').json()
    with db_tool.db_cursor() as cursor:
        cursor.execute('SELECT COUNT(*) AS cnt FROM orders WHERE DATE(created_at) = CURDATE()')
        assert summary['today_orders'] == cursor.fetchone()['cnt']
        cursor.execute('SELECT IFNULL(SUM(total_amount-discount_amount),0) AS amount FROM orders WHERE payment_status=1 AND status<>4 AND DATE(paid_at)=CURDATE()')
        assert summary['revenue'] == float(cursor.fetchone()['amount'])
    assert len(summary['trend']) == 7 and summary['trend'][-1]['date'] == summary['date']
    assert summary['trend'][-1]['revenue'] == summary['revenue']
    record('Report independently matches SQL and seven-day trend', {'date': summary['date'], 'today_orders': summary['today_orders'], 'revenue': summary['revenue']})

    def snapshot():
        with db_tool.db_cursor() as cursor:
            cursor.execute('SELECT COUNT(*) AS cnt FROM orders')
            count = cursor.fetchone()['cnt']
            cursor.execute('SELECT id, stock FROM ingredients ORDER BY id')
            stock = [(r['id'], str(r['stock'])) for r in cursor.fetchall()]
            cursor.execute('SELECT id, is_available FROM menu_items ORDER BY id')
            availability = [(r['id'], r['is_available']) for r in cursor.fetchall()]
        return count, stock, availability

    with db_tool.db_cursor() as cursor:
        cursor.execute('SELECT id FROM users ORDER BY id LIMIT 1')
        uid = cursor.fetchone()['id']
        cursor.execute('SELECT m.id, i.stock, di.quantity FROM menu_items m JOIN dish_ingredients di ON m.id=di.dish_id JOIN ingredients i ON i.id=di.ingredient_id WHERE m.is_available=1 AND i.stock>=di.quantity LIMIT 1')
        dish = cursor.fetchone()
    assert dish, 'No available ingredient-mapped dish for rollback verification'
    before = snapshot()
    original_connect = db_tool.get_connection
    commits_rolled_back = []

    class RollbackConnection:
        def __init__(self):
            self.connection = original_connect()
        def __getattr__(self, key):
            return getattr(self.connection, key)
        def commit(self):
            commits_rolled_back.append(True)
            self.connection.rollback()

    with patch.object(db_tool, 'get_connection', side_effect=RollbackConnection):
        db_tool.create_order(uid, '验收回滚', '13800000000', None, items=[{'dish_id': dish['id'], 'quantity': 1}], delivery_mode=1)
    assert commits_rolled_back and snapshot() == before
    record('Real successful order transaction forced to roll back', 'Order count, inventory and menu availability unchanged; no test order retained')

    excessive = math.floor(float(dish['stock']) / float(dish['quantity'])) + 2
    with patch.object(db_tool, 'get_connection', side_effect=RollbackConnection):
        try:
            db_tool.create_order(uid, '验收回滚', '13800000000', None, items=[{'dish_id': dish['id'], 'quantity': excessive}], delivery_mode=1)
        except ValueError as exc:
            assert '库存不足' in str(exc)
        else:
            raise AssertionError('Oversold order accepted')
    assert snapshot() == before
    record('Real insufficient stock transaction rolls back', 'No oversell, no retained order, inventory unchanged')

    if args.external:
        response = client.get('/health', params={'deep': 'true'})
        response.raise_for_status()
        health = response.json()
        for name, check in health['checks'].items():
            if not check.get('ok'):
                results.append({'name': f'External dependency {name}', 'passed': False, 'detail': str(check)[:500]})
                print(f'FAIL: External dependency {name}', flush=True)
            else:
                record(f'External dependency {name}', 'Live connection verified')
        response = client.post('/chat', json={'query': '推荐20元以内不辣的素菜，请按实际菜单回答'})
        response.raise_for_status()
        chat = response.json()
        assert chat.get('type') != 'error', chat.get('response')
        menu = client.get('/menu/list').json()['menu_items']
        ids = chat.get('menu_ids') or []
        assert ids, 'Live AI did not recommend a matching dish'
        for dish_id in ids:
            d = next(d for d in menu if d['id'] == dish_id)
            assert d['price'] <= 20 and d['spice_level'] == 0 and d['is_vegetarian'] and d['is_available']
        record('Live AI recommendation honors database constraints', {'menu_ids': ids, 'tool_calls': chat.get('tool_calls'), 'elapsed_ms': chat.get('elapsed_ms')})

out = Path(__file__).resolve().parents[1] / 'artifacts/review'
out.mkdir(parents=True, exist_ok=True)
(out / 'integration-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'checks': len(results), 'failed': sum(not r['passed'] for r in results)}), flush=True)
if any(not r['passed'] for r in results):
    sys.exit(1)
