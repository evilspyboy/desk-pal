import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pytest
from unittest.mock import MagicMock
sys.modules['pygame'] = MagicMock()

from activity_queue import ActivityQueue

def test_heartbeat_suppression_and_error_alerting():
    # Setup mock DeskPal app
    from deskpal_app import DeskPalApp
    app = DeskPalApp.__new__(DeskPalApp)
    app.apps = [{
        'id': 'test_service',
        'name': 'Test Service',
        'suppressed_events': {'heartbeat': True},
        'actions': []
    }]
    app.app_telemetry = {}
    app.attention_seen = {}
    app.integration_attention = {}
    app.integration_health_attention = {}
    app.activity_history_path = None
    app.telemetry_path = None
    app.char_x = app.char_y = 0
    app.target_x = app.target_y = 0
    app.current_anim = app.target_animation = 'idle'
    app.persist_telemetry = MagicMock()
    app.audit_activity = MagicMock()
    app.request_attention = MagicMock()
    app.queue_action = MagicMock()

    # 1. Healthy heartbeat with suppressed_events: heartbeat=True
    hb_healthy = {
        'app_id': 'test_service',
        'status': 'healthy',
        'activity': 'Running smoothly',
        'summary': 'All good',
        'ttl_seconds': 60
    }
    app.receive_heartbeat(hb_healthy)
    
    # Healthy heartbeat should update last_seen and last_healthy
    assert 'last_seen' in app.app_telemetry['test_service']
    assert 'last_healthy' in app.app_telemetry['test_service']
    # But because heartbeat is suppressed, request_attention and queue_action should NOT have been called
    assert not app.request_attention.called
    assert not app.queue_action.called

    # 2. Service outage / connection error arrives
    hb_offline = {
        'app_id': 'test_service',
        'status': 'offline',
        'activity': 'Unreachable',
        'summary': 'Test Service is unreachable (Connection refused)',
        'refresh_error': 'Connection refused',
        'ttl_seconds': 60
    }
    prev_seen = app.app_telemetry['test_service']['last_seen']
    time.sleep(0.01)
    app.receive_heartbeat(hb_offline)

    # Outage MUST NOT update last_seen as a healthy update
    assert app.app_telemetry['test_service']['last_seen'] == prev_seen
    assert app.app_telemetry['test_service'].get('refresh_error') == 'Connection refused'
    # Outage MUST trigger request_attention even though routine heartbeats are suppressed!
    assert app.request_attention.called
    app.request_attention.assert_called_with('test_service', 'Test Service is unreachable (Connection refused)')
    assert app.attention_seen['test_service'] == 'outage'

    # 3. Repeated outage heartbeats while still down must NOT re-alert
    app.request_attention.reset_mock()
    app.receive_heartbeat(hb_offline)
    assert not app.request_attention.called

    # 4. check_integration_health while down must NOT re-alert (no ping-pong between heartbeat and health check)
    app.integration_started = time.time() - 200
    app.check_integration_health()
    assert not app.request_attention.called

    # 5. User acknowledges the alert via touch/tap
    queue = ActivityQueue()
    app.activity_queue = queue
    action = {'id': 'outage_alert', '_source_app_id': 'test_service', '_attention_waiting': True,
              'attention_until_interaction': True}
    item = (action, 'Test Service', (255, 0, 0), 'Test Service is unreachable', [], None)
    queue.active = item
    assert queue.acknowledge_attention(app)
    assert app.attention_seen['test_service'] == 'acknowledged'

    # 6. Successive offline heartbeats while acknowledged must NOT re-alert
    app.request_attention.reset_mock()
    app.receive_heartbeat(hb_offline)
    assert not app.request_attention.called

    # 7. Service recovers
    app.request_attention.reset_mock()
    hb_recovered = {
        'app_id': 'test_service',
        'status': 'healthy',
        'activity': 'Running smoothly again',
        'summary': 'All good',
        'ttl_seconds': 60
    }
    app.receive_heartbeat(hb_recovered)
    assert 'test_service' not in app.attention_seen
    assert not app.request_attention.called

    # 8. Subsequent new outage later MUST trigger alert again
    app.request_attention.reset_mock()
    app.receive_heartbeat(hb_offline)
    assert app.request_attention.called
    assert app.attention_seen['test_service'] == 'outage'
