"""Unit tests for Desk-Pal external REST API endpoints."""
import sys
import unittest
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path('src').resolve()))
if 'pygame' not in sys.modules:
    mock_pygame = MagicMock()
    mock_pygame.Rect = lambda *args: MagicMock()
    sys.modules['pygame'] = mock_pygame

from deskpal_app import DeskPalHTTPHandler
from activity_queue import ActivityQueue


class FakeSocket:
    def __init__(self, data=b""):
        self._file = BytesIO(data)

    def makefile(self, *args, **kwargs):
        return self._file


class TestRestAPI(unittest.TestCase):
    def setUp(self):
        self.queue = ActivityQueue()
        self.app = SimpleNamespace(
            cfg={'active_character': 'adventurer', 'theme': 'cozy_study', 'scenes': {'cozy_study': {'name': 'Study'}, 'beach': {'name': 'Beach'}}},
            activity_queue=self.queue,
            radar_nearby_present=True,
            last_radar_nearby={'targets': [{'x': 0, 'y': 1.0}]},
            hardware_monitor=SimpleNamespace(
                lock=MagicMock(__enter__=lambda s: None, __exit__=lambda s, *a: None),
                config={'radar': {'enabled': True, 'presence_range_m': 2.0},
                        'speaker': {'enabled': True, 'output': 'default', 'volume': 0.8}}
            ),
            char_x=0, char_y=0, target_x=0, target_y=0,
            wander_timer=0,
            current_anim='idle', target_animation='idle',
            is_sleeping=False,
            active_popup_modal=None, pending_popup_modal=None,
            audit_activity=lambda *args, **kwargs: None,
            load_scene_backgrounds=lambda: None,
            save_config=lambda: None
        )
        self.app.queue_action = lambda action, app_name="APP", color=(0,229,255), summary="", ticker=None, badge=None, priority=False: self.queue.enqueue((action, app_name, color, summary, ticker, badge), self.app)
        DeskPalHTTPHandler.app_ref = self.app

    def make_request(self, method, path, body=None):
        raw_body = json.dumps(body).encode('utf-8') if body is not None else b""
        request_text = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nContent-Length: {len(raw_body)}\r\n\r\n"
        input_stream = BytesIO(request_text.encode('utf-8') + raw_body)
        output_stream = BytesIO()

        handler = DeskPalHTTPHandler.__new__(DeskPalHTTPHandler)
        handler.rfile = BytesIO(raw_body)
        handler.wfile = output_stream
        handler.headers = {
            'Content-Length': str(len(raw_body)),
            'content-length': str(len(raw_body)),
            'Host': 'localhost',
            'Content-Type': 'application/json'
        }
        handler.path = path
        handler.command = method
        handler.requestline = f"{method} {path} HTTP/1.1"
        handler.request_version = "HTTP/1.1"

        if method == "GET":
            handler.do_GET()
        elif method == "POST":
            handler.do_POST()
        elif method == "OPTIONS":
            handler.do_OPTIONS()

        raw_output = output_stream.getvalue()
        parts = raw_output.split(b"\r\n\r\n", 1)
        header_text = parts[0].decode('utf-8', errors='replace')
        response_body = parts[1] if len(parts) > 1 else b""
        status_line = header_text.splitlines()[0] if header_text else ""
        status_code = int(status_line.split()[1]) if status_line else 500
        return status_code, response_body

    def test_options_cors(self):
        code, _ = self.make_request("OPTIONS", "/api/v1/notify")
        self.assertEqual(code, 200)

    def test_get_status(self):
        code, body = self.make_request("GET", "/api/v1/status")
        self.assertEqual(code, 200)
        data = json.loads(body.decode())
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["character"], "adventurer")
        self.assertTrue(data["radar_present"])
        self.assertFalse(data["sleeping"])

    def test_get_presence(self):
        code, body = self.make_request("GET", "/api/v1/presence")
        self.assertEqual(code, 200)
        data = json.loads(body.decode())
        self.assertTrue(data["radar_enabled"])
        self.assertTrue(data["present"])
        self.assertEqual(data["targets"], 1)

    def test_post_notify(self):
        code, body = self.make_request("POST", "/api/v1/notify", {
            "title": "Home Assistant",
            "summary": "Front gate opened",
            "attention": True,
            "voice_phrase": "Hey, someone is at the front gate!"
        })
        self.assertEqual(code, 200)
        data = json.loads(body.decode())
        self.assertEqual(data["status"], "queued")
        self.assertTrue(data["attention"])
        self.assertEqual(len(self.queue.items), 1)
        queued_action = self.queue.items[0][0]
        self.assertTrue(queued_action.get("attention_until_interaction"))
        self.assertEqual(queued_action["voice_phrase"], "Hey, someone is at the front gate!")

    def test_post_action(self):
        code, body = self.make_request("POST", "/api/v1/action", {
            "animation": "wave_arms",
            "speech": "Hello there!",
            "scene": "beach"
        })
        self.assertEqual(code, 200)
        data = json.loads(body.decode())
        self.assertEqual(data["status"], "queued")
        self.assertEqual(data["animation"], "wave_arms")
        self.assertEqual(data["scene"], "beach")

    def test_post_scene_switch(self):
        code, body = self.make_request("POST", "/api/v1/scene", {
            "scene": "beach"
        })
        self.assertEqual(code, 200)
        data = json.loads(body.decode())
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["scene"], "beach")
        self.assertEqual(self.app.cfg["active_scene"], "beach")

    def test_post_say(self):
        mock_output = MagicMock()
        self.app.speech_output = mock_output
        code, body = self.make_request("POST", "/api/v1/say", {
            "text": "Desk Pal is speaking."
        })
        self.assertEqual(code, 200)
        data = json.loads(body.decode())
        self.assertEqual(data["status"], "speaking")
        self.assertEqual(data["text"], "Desk Pal is speaking.")

    def test_companion_services_endpoints(self):
        mock_supervisor = MagicMock()
        mock_supervisor.discover_services.return_value = [{"id": "flight_radar", "name": "Flight Radar", "status": "running", "port": 5000}]
        mock_supervisor.get_logs.return_value = ["Log line 1", "Log line 2"]
        mock_supervisor.get_service_code.return_value = {"success": True, "code": "print('hello')", "manifest": {}}
        mock_supervisor.start_service.return_value = {"success": True, "message": "Service started"}
        self.app.service_supervisor = mock_supervisor

        # Test GET /api/services
        code, body = self.make_request("GET", "/api/services")
        self.assertEqual(code, 200)
        data = json.loads(body.decode())
        self.assertEqual(len(data["services"]), 1)
        self.assertEqual(data["services"][0]["id"], "flight_radar")

        # Test GET /api/services/logs
        code, body = self.make_request("GET", "/api/services/logs?id=flight_radar")
        self.assertEqual(code, 200)
        data = json.loads(body.decode())
        self.assertEqual(len(data["logs"]), 2)

        # Test POST /api/services/action
        code, body = self.make_request("POST", "/api/services/action", {"id": "flight_radar", "action": "start"})
        self.assertEqual(code, 200)
        data = json.loads(body.decode())
        self.assertTrue(data["success"])

    def test_system_stats_endpoint(self):
        # Test GET /api/system_stats
        code, body = self.make_request("GET", "/api/system_stats")
        self.assertEqual(code, 200)
        data = json.loads(body.decode())
        self.assertIn("memory", data)
        self.assertIn("storage", data)
        self.assertIn("used_gb", data["memory"])
        self.assertIn("available_gb", data["memory"])
        self.assertIn("used_gb", data["storage"])
        self.assertIn("available_gb", data["storage"])

        # Test system_resources in GET /api/v1/status
        code, body = self.make_request("GET", "/api/v1/status")
        self.assertEqual(code, 200)
        status_data = json.loads(body.decode())
        self.assertIn("system_resources", status_data)
        self.assertIn("memory", status_data["system_resources"])


if __name__ == "__main__":
    unittest.main()
