"""Kitchen-board regressions with mocked database reads; no business-data writes."""
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from tools import db_tool


class KitchenBoardTests(unittest.TestCase):
    def load_rows(self, rows):
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        with patch.object(db_tool, 'db_cursor') as context:
            context.return_value.__enter__.return_value = cursor
            result = db_tool.get_kitchen_orders()
        self.assertIn('o.payment_status = 1', cursor.execute.call_args.args[0])
        return result

    def test_empty_kitchen_retains_configured_stations(self):
        result = self.load_rows([])
        self.assertEqual([s['station'] for s in result['stations']], list(db_tool.STATION_ORDER))
        self.assertEqual((result['total_orders'], result['total_quantity']), (0, 0))
        self.assertTrue(all(s['orders'] == [] and s['total_quantity'] == 0 for s in result['stations']))

    def test_shared_order_only_exposes_each_stations_own_items(self):
        base = dict(order_id=7, order_no='KITCHEN-7', contact_name='客人', delivery_mode=1,
                    table_no=None, status=1, created_at=datetime(2026, 10, 19, 12))
        rows = [dict(base, dish_name='热菜', quantity=2, category='川菜'),
                dict(base, dish_name='凉菜', quantity=1, category='凉菜'),
                dict(base, dish_name='饮品', quantity=3, category='饮品'),
                dict(base, dish_name='另一道热菜', quantity=1, category='川菜')]
        result = self.load_rows(rows)
        self.assertEqual((result['total_orders'], result['total_quantity']), (1, 7))
        by_station = {s['station']: s for s in result['stations']}
        self.assertEqual([i['dish_name'] for i in by_station['热菜档']['orders'][0]['items']], ['热菜', '另一道热菜'])
        self.assertEqual([i['dish_name'] for i in by_station['凉菜档']['orders'][0]['items']], ['凉菜'])
        self.assertEqual([i['dish_name'] for i in by_station['饮品档']['orders'][0]['items']], ['饮品'])
        self.assertEqual([s['total_quantity'] for s in result['stations']], [3, 1, 3])


if __name__ == '__main__':
    unittest.main()
