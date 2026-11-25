import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from bridge import AgentBridge


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.requests = []
        requests = self.requests
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                requests.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                self.send_response(200);self.end_headers()
                self.wfile.write(json.dumps({'status': 'received' if self.path.endswith('event') else 'ok'}).encode())
            def do_GET(self):
                self.send_response(200);self.end_headers()
                self.wfile.write(json.dumps({'state': 'travelling', 'pending': [{}, {}], 'private_message': 'not exposed'}).encode())
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True);self.thread.start()
        self.endpoint = 'http://127.0.0.1:'+str(self.http.server_port)
        self.path = Path(self.temp.name)/'state.json'
        self.bridge = AgentBridge(self.endpoint, 'agent', 'My agent', self.path)

    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();self.temp.cleanup()

    def test_event_and_cached_button_status_use_same_app(self):
        result = self.bridge.report('needs_attention', 'task-a', 'Please review my question', 'question-1')
        self.assertEqual(result['delivery'], 'received')
        event, heartbeat = self.requests
        self.assertTrue(event[1]['attention_needed'])
        self.assertEqual(event[1]['event'], 'needs_attention')
        self.assertEqual(heartbeat[1]['button_summary'], event[1]['summary'])
        self.assertEqual(heartbeat[1]['app_id'], event[1]['app_id'])
        self.assertNotIn('action', event[1])

    def test_dedup_survives_restart_and_distinguishes_real_occurrences(self):
        self.bridge.report('completed', 'a', 'Done', 'a-done')
        second = AgentBridge(self.endpoint, 'agent', 'My agent', self.path)
        self.assertEqual(second.report('completed', 'a', 'Done', 'a-done')['delivery'], 'already_delivered')
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(second.report('completed', 'a', 'Done', 'a-done-again')['delivery'], 'received')
        self.assertEqual(len(self.requests), 4)
        with self.assertRaises(ValueError):second.report('completed', 'a', 'Changed', 'a-done')

    def test_failure_is_task_attention_not_monitor_transport_failure(self):
        self.bridge.report('failed', 'a', 'Task failed', 'a-failed')
        self.assertEqual(self.requests[0][1]['event'], 'task_failed')
        self.assertEqual(self.requests[0][1]['status'], 'healthy')
        self.assertTrue(self.requests[0][1]['attention_needed'])

    def test_connection_failure_is_not_claimed_success_or_retried(self):
        calls=[]
        def unavailable(*args):
            calls.append(args);raise OSError('offline')
        self.bridge.request = unavailable
        self.assertEqual(self.bridge.report('started', 'a', 'Starting', 'start')['delivery'], 'unconfirmed')
        self.assertEqual(len(calls), 1)
        self.assertFalse(self.path.exists())
        self.assertFalse(self.bridge.status()['reachable'])

    def test_validation_does_not_send_invalid_reports(self):
        for args in [('unknown', 'a', 'M', '1'), ('coding', '', 'M', '1'), ('coding', 'a', 'x'*501, '1'), ('coding', 'a', 'M', '')]:
            with self.assertRaises(ValueError):self.bridge.report(*args)
        for url in ('file:///tmp/test', 'http://user:pass@example.org', 'http://example.org/private', 'http://example.org?token=x'):
            with self.assertRaises(ValueError):AgentBridge(url, 'agent', 'A', self.path)
        with self.assertRaises(ValueError):AgentBridge(self.endpoint, '../invalid', 'A', self.path)
        self.assertEqual(self.requests, [])

    def test_status_does_not_expose_unrelated_messages(self):
        status=self.bridge.status()
        self.assertTrue(status['reachable']);self.assertEqual(status['pending_count'], 2)
        self.assertNotIn('private_message', status)

    def test_status_failure_after_event_does_not_replay_event(self):
        original=self.bridge.request
        def request(path, payload=None):
            if path.endswith('heartbeat'):raise OSError('offline')
            return original(path, payload)
        self.bridge.request=request
        result=self.bridge.report('coding', 'a', 'Coding', 'a-code')
        self.assertEqual(result['delivery'], 'received');self.assertIn('status_warning',result)
        self.assertEqual(self.bridge.report('coding', 'a', 'Coding', 'a-code')['delivery'], 'already_delivered')
        self.assertEqual(len(self.requests),1)

    def test_distinct_apps_cannot_share_state_file(self):
        self.bridge.report('started', 'a', 'Starting', 'start')
        with self.assertRaises(ValueError):AgentBridge(self.endpoint, 'other', 'Other', self.path)


if __name__ == '__main__':
    unittest.main()
