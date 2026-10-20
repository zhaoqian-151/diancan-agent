"""Regression tests for business rules. No writes to the real database."""
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from api.main import app
from tools import db_tool
from agent import mcp


class ProductIntegrityTests(unittest.TestCase):
    def test_external_payments_cannot_record_fake_success(self):
        for method in (1, 2):
            with self.assertRaisesRegex(ValueError, '尚未接入'):
                db_tool.pay_order(1, method)

    def test_inventory_failure_is_not_silently_truncated(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [{'dish_id': 1, 'ingredient_id': 2, 'quantity': .3}]
        cursor.rowcount = 0
        with self.assertRaisesRegex(ValueError, '库存不足'):
            db_tool._deduct_ingredients(cursor, [(1, 'dish', 2, 10, 20)])
        self.assertIn('stock >= %s', cursor.execute.call_args.args[0])

    def test_duplicate_dish_lines_accumulate_inventory(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [{'dish_id': 1, 'ingredient_id': 2, 'quantity': .3}]
        cursor.rowcount = 1
        db_tool._deduct_ingredients(cursor, [(1, 'dish', 2, 10, 20), (1, 'dish', 3, 10, 30)])
        self.assertEqual(cursor.execute.call_args.args[1], (1.5, 2, 1.5))

    def test_restock_does_not_relist_manually_hidden_dishes(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [{'dish_id': 1, 'per': 1, 'stock': 10}]
        db_tool._refresh_dish_availability(cursor, [1])
        self.assertEqual(cursor.execute.call_count, 1)

    def test_negative_and_conflicting_inventory_fields(self):
        for fields in ({'stock': -1}, {'threshold': float('nan')}, {'add': 1, 'stock': 3}):
            with self.assertRaises(ValueError):
                db_tool.update_ingredient(1, **fields)

    def test_invalid_menu_fields(self):
        for fields in ({'price': -1}, {'price': float('inf')}, {'dish_name': '  '}, {'spice_level': 8}, {'image_url': 'javascript:alert(1)'}):
            with self.assertRaises(ValueError):
                db_tool.validate_menu_fields(fields)

    def test_discounted_order_exposes_payable_amount(self):
        row = dict(id=1, order_no='test', contact_name='test', delivery_address=None, delivery_mode=1,
                   total_amount=100, discount_amount=20, total_quantity=1, status=0, created_at='2026-10-19')
        order = db_tool._normalize_order(row)
        self.assertEqual(order['payable_amount'], 80)
        self.assertEqual(order['formatted_total'], '¥80.00')

    def test_canceled_orders_cannot_be_paid(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {'status': 4, 'payment_status': 0}
        with patch.object(db_tool, 'db_cursor') as ctx:
            ctx.return_value.__enter__.return_value = cursor
            with self.assertRaisesRegex(ValueError, '已取消'):
                db_tool.pay_order(1, 3)

    def test_status_transitions_and_unpaid_guard(self):
        for row, target in [({'status': 3, 'payment_status': 1, 'delivery_mode': 2}, 0),
                            ({'status': 0, 'payment_status': 0, 'delivery_mode': 2}, 1),
                            ({'status': 0, 'payment_status': 1, 'delivery_mode': 2}, 4),
                            ({'status': 1, 'payment_status': 1, 'delivery_mode': 1}, 2)]:
            cursor = MagicMock()
            cursor.fetchone.return_value = row
            with patch.object(db_tool, 'db_cursor') as ctx:
                ctx.return_value.__enter__.return_value = cursor
                with self.assertRaises(ValueError):
                    db_tool.update_order_status(1, target)

    def test_preference_constraints_survive_vector_fallback(self):
        wrong = dict(id=1, dish_name='肉菜', price=60, is_available=True, is_vegetarian=False, spice_level=3)
        with patch.object(db_tool, 'get_menu_items', return_value=[wrong]), patch.object(db_tool, 'get_dish_by_id', return_value=wrong), patch.object(mcp.pinecone_tool, 'search_menu_items', return_value=[{'dish_id': 1, 'score': .9}]):
            self.assertEqual(mcp._collect_candidates('20元以内不辣的素菜'), [])

    def test_highlights_only_mention_actual_answer_dishes(self):
        self.assertEqual(mcp._mentioned_menu_ids('没有符合条件的菜', [{'id': 1, 'dish_name': '宫保鸡丁'}]), [])

    def test_delivery_service_failure_blocks_order(self):
        with patch.object(db_tool, 'get_or_create_user', return_value=1), patch.object(db_tool, 'create_order') as create, patch('api.main.amap_tool.check_delivery_range', side_effect=RuntimeError('offline')):
            client = TestClient(app)
            result = client.post('/order', json={'contact_name': '测试', 'contact_phone': '13800000000', 'delivery_address': '重庆市大渡口人民医院', 'delivery_mode': 2})
            self.assertEqual(result.status_code, 503)
            create.assert_not_called()

    def test_invalid_delivery_mode_and_quantities(self):
        client = TestClient(app)
        base = {'contact_name': '测试', 'contact_phone': '13800000000', 'delivery_mode': 1}
        for body in [dict(base, delivery_mode=3), dict(base, items=[{'dish_id': 1, 'quantity': -1}]), dict(base, items=[{'dish_id': 1, 'quantity': 1.5}])]:
            self.assertEqual(client.post('/order', json=body).status_code, 422)

    def test_browser_visitors_are_isolated(self):
        names = []
        def resolve(name):
            names.append(name)
            return int(name[-8:], 16) or 1
        with patch.object(db_tool, 'get_or_create_user', side_effect=resolve), patch.object(db_tool, 'cart_total', side_effect=lambda uid: {'user_id': uid, 'items': []}):
            a, b = TestClient(app), TestClient(app)
            first = a.get('/cart')
            self.assertIn('HttpOnly', first.headers['set-cookie'])
            uid_a = first.json()['user_id']
            uid_b = b.get('/cart').json()['user_id']
            self.assertNotEqual(uid_a, uid_b)
            self.assertEqual(a.get('/cart').json()['user_id'], uid_a)
            self.assertEqual(a.get('/cart', params={'user_id': uid_b}).status_code, 403)

    def test_shop_never_advertises_unconnected_payments(self):
        response = TestClient(app).get('/shop')
        self.assertFalse(response.json()['online_payment_available'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
