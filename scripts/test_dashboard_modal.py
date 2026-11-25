"""Unit tests for Dashboard Popup Modal parser and layout generator."""
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path('src').resolve()))
if 'pygame' not in sys.modules:
    mock_pygame = MagicMock()
    mock_pygame.Rect = lambda *args: MagicMock()
    sys.modules['pygame'] = mock_pygame

from deskpal_app import parse_dashboard_modal


class TestDashboardModal(unittest.TestCase):
    def test_parse_explicit_dashboard(self):
        modal = {
            'title': 'Fuel Tracker',
            'hero_value': '254.5¢',
            'hero_subhead': 'U-Go Loganholme',
            'badge': 'BUY NOW',
            'badge_color': (46, 204, 113),
            'tiles': [
                {'label': 'AREA AVG', 'value': '262.0¢'},
                {'label': 'TREND', 'value': 'Rising 48h'},
                {'label': 'DISTANCE', 'value': '1.1 km'}
            ]
        }
        res = parse_dashboard_modal(modal)
        self.assertEqual(res['hero_value'], '254.5¢')
        self.assertEqual(res['hero_subhead'], 'U-Go Loganholme')
        self.assertEqual(res['badge'], 'BUY NOW')
        self.assertEqual(len(res['tiles']), 3)

    def test_parse_fuel_summary_auto(self):
        modal = {
            'title': 'Fuel Tracker',
            'summary': 'In 4128 (5km radius), Premium Unleaded 98 averages 262.0¢/L. The cheapest option is U-Go Loganholme at 254.5¢/L (1.1km away). Prices are expected to rise over the next 48 hours. Recommended: Buy now before prices increase.'
        }
        res = parse_dashboard_modal(modal)
        self.assertIn('254.5', res['hero_value'])
        self.assertIn('U-Go Loganholme', res['hero_subhead'])
        self.assertEqual(res['badge'], 'BUY NOW')
        self.assertTrue(len(res['tiles']) >= 1)

    def test_parse_weather_summary_auto(self):
        modal = {
            'title': 'Weather',
            'summary': 'Today 14.1–22.2°C · Rain 66%\nWind up to 15.8 km/h · UV 6.75'
        }
        res = parse_dashboard_modal(modal)
        self.assertIn('22.2°C', res['hero_value'])
        self.assertIn('Rain 66%', res['badge'])
        self.assertTrue(len(res['tiles']) >= 1)

    def test_parse_orders_summary_auto(self):
        modal = {
            'title': 'Store Monitor',
            'summary': 'Etsy: 2 active orders awaiting shipment.\nBig Cartel: 0 active orders awaiting shipment.'
        }
        res = parse_dashboard_modal(modal)
        self.assertIn('2', res['hero_value'])
        self.assertEqual(res['badge'], 'ORDERS')


if __name__ == '__main__':
    unittest.main()
