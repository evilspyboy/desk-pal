"""
Desk-Pal Lightweight Telemetry Client
Drop this file into any project (bmcbf, fuel_tracker, store_monitor, travel_deals).
Fails completely silently if Desk-Pal is offline or sleeping so your core apps are never disrupted.
"""

import requests
import threading

DEFAULT_DESKPAL_HOST = "127.0.0.1"
DEFAULT_DESKPAL_PORT = 7777

class DeskPal:
    def __init__(self, app_id, host=DEFAULT_DESKPAL_HOST, port=DEFAULT_DESKPAL_PORT, timeout=1.0):
        self.app_id = app_id
        self.endpoint = f"http://{host}:{port}/api/v1"
        self.timeout = timeout

    def _post_async(self, path, payload):
        def _send():
            try:
                requests.post(f"{self.endpoint}/{path}", json=payload, timeout=self.timeout)
            except Exception:
                pass  # Fail silent: telemetry should never disrupt the host app
        threading.Thread(target=_send, daemon=True).start()

    def heartbeat(self, activity="Idle", status="healthy", details=None):
        """Report general state and what the app is doing right now."""
        payload = {
            "app_id": self.app_id,
            "status": status,
            "activity": activity,
            "details": details or {}
        }
        self._post_async("heartbeat", payload)

    def alert(self, title, message, severity="warning"):
        """Trigger an immediate attention-seeking animation/alert on the companion."""
        payload = {
            "app_id": self.app_id,
            "title": title,
            "message": message,
            "severity": severity
        }
        self._post_async("alert", payload)

    def new_order(self, store, order_count=1, summary=""):
        """Specialized helper for store sales (drops a parcel in the pet's room)."""
        payload = {
            "app_id": self.app_id,
            "event": "store_order",
            "store": store,
            "count": order_count,
            "summary": summary
        }
        self._post_async("event", payload)

    def fuel_price_drop(self, station, price, drop_amount=0.0):
        """Specialized helper for fuel tracker bargains."""
        payload = {
            "app_id": self.app_id,
            "event": "fuel_drop",
            "station": station,
            "price": price,
            "drop": drop_amount
        }
        self._post_async("event", payload)
