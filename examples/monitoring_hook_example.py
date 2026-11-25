#!/usr/bin/env python3
"""Example Python monitoring hook for pushing events to Desk-Pal.

Usage:
    DESKPAL_HOST=192.168.1.50 python examples/monitoring_hook_example.py
"""
import functools
import json
import os
import time
import urllib.request

DESKPAL_HOST = os.environ.get("DESKPAL_HOST", "127.0.0.1")
DESKPAL_PORT = int(os.environ.get("DESKPAL_PORT", "7777"))


def send_deskpal_event(app_id, event, summary, status="healthy", attention_needed=False):
    url = f"http://{DESKPAL_HOST}:{DESKPAL_PORT}/api/v1/event"
    payload = {
        "app_id": app_id,
        "event": event,
        "status": status,
        "summary": summary,
        "attention_needed": attention_needed,
        "timestamp": time.time(),
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return resp.status
    except Exception:
        return None  # Never block the host job if Desk-Pal is sleeping or offline.


def deskpal_monitor(app_id, event_name="job_completed"):
    """Decorator that reports job completion or failure to Desk-Pal."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                result = fn(*args, **kwargs)
                send_deskpal_event(app_id, event_name, f"{fn.__name__} succeeded")
                return result
            except Exception as err:
                send_deskpal_event(
                    app_id,
                    "job_failed",
                    f"{fn.__name__} failed: {err}",
                    status="error",
                    attention_needed=True,
                )
                raise
        return wrapper
    return decorator


@deskpal_monitor(app_id="ci_monitor", event_name="build_passed")
def run_nightly_build():
    print("Running sample job...")
    time.sleep(0.5)
    return True


if __name__ == "__main__":
    run_nightly_build()
    print(f"Sent sample event to http://{DESKPAL_HOST}:{DESKPAL_PORT}/api/v1/event")
