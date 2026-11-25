"""Bounded, local JSON-lines audit trail for received input and visual playback."""
from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time

_lock = threading.RLock()
# Keep high-frequency duplicate heartbeats in memory (up to 500) to eliminate SD card wear
_ephemeral_heartbeats = deque(maxlen=500)


def append(path, event, **fields):
    if not path:
        return
    row = dict(timestamp=time.time(), time_utc=datetime.now(timezone.utc).isoformat(), event=event, **fields)
    # If this is a duplicate heartbeat receipt, buffer in memory instead of writing to disk
    if event == 'received' and fields.get('source_event') == 'heartbeat' and fields.get('duplicate_suppressed'):
        with _lock:
            _ephemeral_heartbeats.append(row)
        return

    encoded = json.dumps(row, ensure_ascii=False, allow_nan=False, default=str) + '\n'
    with _lock:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.stat().st_size + len(encoded.encode('utf-8')) > 2_000_000:
            oldest = Path(str(p)+'.4')
            oldest.unlink(missing_ok=True)
            for index in range(3, 0, -1):
                source = Path(str(p)+'.'+str(index))
                if source.exists():
                    source.replace(str(p)+'.'+str(index+1))
            p.replace(str(p)+'.1')
        with p.open('a', encoding='utf-8') as stream:
            stream.write(encoded)


def recent(path, limit=5000, include_heartbeat_receipts=True):
    if not path:
        return []
    rows = deque(maxlen=limit)
    with _lock:
        for p in [Path(str(path)+'.'+str(i)) for i in range(4, 0, -1)] + [Path(path)]:
            if not p.exists():
                continue
            with p.open(encoding='utf-8') as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                        if not include_heartbeat_receipts and row.get('event') == 'received' and row.get('source_event') == 'heartbeat':
                            continue
                        rows.append(row)
                    except ValueError:
                        continue
        if include_heartbeat_receipts and _ephemeral_heartbeats:
            rows.extend(list(_ephemeral_heartbeats))
    return sorted(rows, key=lambda r: r.get('timestamp', 0))[-limit:]

