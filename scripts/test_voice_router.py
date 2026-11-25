"""Unit tests for voice command router with 3-tier cascade and Cactus Needle."""
import unittest
from unittest.mock import MagicMock, patch
import os, sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import voice_command_router

class TestVoiceCommandRouter(unittest.TestCase):
    def setUp(self):
        self.app = MagicMock()
        self.app.cfg = {
            "active_scene": "cozy",
            "scenes": {
                "cozy": {
                    "name": "Cozy Living Room",
                    "props": [{"id": "prop_tv", "interaction": "tv"}]
                },
                "beach": {
                    "name": "Sunny Beach",
                    "props": []
                }
            },
            "apps": [
                {
                    "id": "fuel_tracker",
                    "name": "Fuel Tracker",
                    "voice_triggers": ["fuel", "petrol"]
                }
            ]
        }
        self.app.apps = self.app.cfg["apps"]
        self.app.app_telemetry = {
            "fuel_tracker": {"summary": "Cheapest fuel is 185.9 cents at 7-Eleven"}
        }

    def test_instant_sleep_and_wake(self):
        matched, reply, action = voice_command_router.match_core_and_app_command("time for bed go to sleep", self.app)
        self.assertTrue(matched)
        self.assertEqual(action, "sleep")
        self.assertIn("Goodnight", reply)
        self.app.enter_standby.assert_called_once()

        matched, reply, action = voice_command_router.match_core_and_app_command("wake up please", self.app)
        self.assertTrue(matched)
        self.assertEqual(action, "wake")
        self.app.wake_from_standby.assert_called_once()

    def test_instant_time_command(self):
        matched, reply, action = voice_command_router.match_core_and_app_command("what time is it", self.app)
        self.assertTrue(matched)
        self.assertEqual(action, "time")
        self.assertIn("It's", reply)

    def test_instant_app_trigger(self):
        matched, reply, action = voice_command_router.match_core_and_app_command("check fuel", self.app)
        self.assertTrue(matched)
        self.assertEqual(action, "fuel_tracker")
        self.assertIn("Fuel Tracker", reply)
        self.assertIn("185.9 cents", reply)

    def test_execute_needle_switch_scene(self):
        matched, reply, action = voice_command_router._execute_needle_tool("switch_scene", {"scene_name": "beach"}, self.app)
        self.assertTrue(matched)
        self.assertEqual(action, "scene:beach")
        self.assertEqual(self.app.pending_scene_destination, "beach")
        self.assertIn("Sunny Beach", reply)

    def test_execute_needle_open_tv(self):
        with patch('interactive_props.open_tv') as mock_open_tv:
            matched, reply, action = voice_command_router._execute_needle_tool("open_tv_viewer", {}, self.app)
            self.assertTrue(matched)
            self.assertEqual(action, "tv")
            self.assertIn("Turning on the TV", reply)
            mock_open_tv.assert_called_once()

    def test_needle_confidence_gating(self):
        mock_engine = MagicMock()
        # High confidence -> matches
        mock_engine.complete.return_value = {
            "confidence": 0.85,
            "function_calls": [{"name": "check_fuel_price", "arguments": {"fuel_type": "petrol"}}]
        }
        with patch('voice_command_router._get_needle_engine', return_value=mock_engine):
            matched, reply, action = voice_command_router.query_cactus_needle("what is petrol price", self.app)
            self.assertTrue(matched)
            self.assertEqual(action, "fuel_tracker")

        # Low confidence -> drops to fallback
        mock_engine.complete.return_value = {
            "confidence": 0.20,
            "function_calls": [{"name": "check_weather", "arguments": {}}]
        }
        with patch('voice_command_router._get_needle_engine', return_value=mock_engine):
            matched, reply, action = voice_command_router.query_cactus_needle("tell me a story about dragons", self.app)
            self.assertFalse(matched)

    def test_dispatch_fallback_chain(self):
        # Query that does not match Tier 1 or Tier 2
        with patch('voice_command_router.match_core_and_app_command', return_value=(False, None, None)):
            with patch('voice_command_router.query_cactus_needle', return_value=(False, None, None)):
                with patch('voice_command_router.query_network_llm', return_value=(True, "Dragons love tacos!", "none")) as mock_net:
                    reply, action = voice_command_router.dispatch_voice_command("tell me about dragons", self.app)
                    self.assertEqual(reply, "Dragons love tacos!")
                    mock_net.assert_called_once()

    def test_split_fallback_primary_fails_secondary_succeeds(self):
        with patch('voice_command_router._get_ai_settings', return_value={
            "chat_fallback_primary": "openai",
            "chat_fallback_secondary": "on_device"
        }):
            with patch('voice_command_router.match_core_and_app_command', return_value=(False, None, None)):
                with patch('voice_command_router.query_cactus_needle', return_value=(False, None, None)):
                    with patch('voice_command_router.query_network_llm', return_value=(False, None, None)) as mock_openai:
                        with patch('voice_command_router.query_on_device_qwen', return_value=(True, "On device reply", "none")) as mock_qwen:
                            reply, action = voice_command_router.dispatch_voice_command("hello", self.app)
                            self.assertEqual(reply, "On device reply")
                            mock_openai.assert_called_once()
                            mock_qwen.assert_called_once()

if __name__ == '__main__':
    unittest.main()
