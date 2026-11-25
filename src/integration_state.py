"""Persist received application state; delivery freshness is separate from summary."""
import json
import os
import threading
import time
from pathlib import Path

_lock = threading.RLock()


def load_telemetry(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_telemetry(path, data):
    with _lock:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        os.replace(temporary, target)


def summary_for(telemetry, app_name, now=None):
    now = time.time() if now is None else now
    seen = telemetry.get('last_seen', 0)
    summary = telemetry.get('summary') or telemetry.get('activity') or telemetry.get('status')
    if not seen or not summary:
        return 'No update received from ' + app_name + ' yet.'
    age = max(0, now - seen)
    ttl = max(30, float(telemetry.get('ttl_seconds', 300)))
    if age <= ttl:
        return summary
    amount = f'{int(age//3600)}h' if age >= 3600 else f'{int(age//60)}m'
    return str(summary) + ' (last update ' + amount + ' ago; awaiting a new response)'


def value_at(payload, path):
    value = payload
    for key in path.split('.'):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def button_summary_for(telemetry, app_name, now=None):
    """Normal buttons show status; acknowledging attention keeps its event elsewhere."""
    heartbeat = telemetry.get('received_events', {}).get('heartbeat', {})
    data = heartbeat.get('data', {})
    if data:
        status = dict(data, last_seen=heartbeat.get('last_seen', 0))
    else:
        status = dict(telemetry)
        data = telemetry.get('data', {})
    status['summary'] = data.get('button_summary') or status.get('summary')
    return summary_for(status, app_name, now)


def record_received(telemetry, name, payload, now=None, suppression=None):
    """Keep samples per event so a later heartbeat does not hide useful event fields."""
    events = telemetry.setdefault('received_events', {})
    if name not in events and len(events) >= 40:
        del events[min(events, key=lambda key: events[key].get('last_seen', 0))]
    previous = events.get(name, {})
    now = time.time() if now is None else now
    samples = [sample for sample in previous.get('recent_receipts', []) if sample[0] > now-300]
    samples.append([now, suppression or 'received'])
    events[name] = dict(count=previous.get('count', 0)+1, last_seen=now, data=payload,
                       recent_receipts=samples[-5000:], last_suppression=suppression,
                       suppressed_count=previous.get('suppressed_count', 0)+int(bool(suppression)))


def normal_update_action(app):
    """Routine updates can be visualized without opening a summary popup every poll."""
    import copy
    selected = app.get('heartbeat_action_id', '__primary__')
    if not selected: return None
    actions = app.get('actions', [])
    action = next((a for a in actions if a.get('id') == selected), None)
    if selected == '__primary__':
        action = next((a for a in actions if a.get('is_primary') or a.get('id') == 'status_check'), None)
    if not action: return None
    result = copy.deepcopy(action)
    result.update(speech='', display_mode='none', attention_needed=False)
    return result


def suppress_successive_duplicate(app, event, previous, payload):
    enabled = app.get('suppress_duplicate_events', {}).get(event, event != 'heartbeat')
    if not enabled or previous is None:
        return False
    # Transport freshness is not a new occurrence. Task IDs/run timestamps remain
    # significant so a repeated task can have the same result and still play.
    ignored = {'last_seen', 'received_at', 'polled_at', 'ttl_seconds'}
    clean = lambda value: {k: v for k, v in value.items() if k not in ignored}
    return clean(previous) == clean(payload)


def conditions_match(action, payload):
    for condition in action.get('conditions', []):
        actual = value_at(payload, condition.get('field', ''))
        expected = condition.get('value')
        op = condition.get('op', 'eq')
        if actual is None:
            return False
        try:
            if op in ('lt', 'lte', 'gt', 'gte'):
                a, b = float(actual), float(expected)
                ok = {'lt': a < b, 'lte': a <= b, 'gt': a > b, 'gte': a >= b}[op]
            elif op == 'contains':
                ok = str(expected).lower() in str(actual).lower()
            elif op == 'neq':
                ok = str(actual).lower() != str(expected).lower()
            else:
                ok = str(actual).lower() == str(expected).lower()
        except (TypeError, ValueError):
            return False
        if not ok:
            return False
    return True
