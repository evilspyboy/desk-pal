import os
import sys
import json
import time
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from local_preview import PreviewBridge
from desktop_mode import DesktopWindow


def test_preview_bridge_on_demand():
    """Verify JPEG compression only runs when a client has recently requested frames."""
    bridge = PreviewBridge()
    assert bridge.last_requested == 0

    class DummySurface:
        def get_size(self):
            return (1280, 720)

    # Idle bridge should skip publish
    bridge.publish(DummySurface())
    assert bridge.frame is None
    assert bridge.frame_number == 0

    # Client requests a frame
    bridge.request_frame()
    assert bridge.last_requested > 0


def test_preview_bridge_input_queue():
    """Verify switch and touch inputs are queued and validated properly."""
    bridge = PreviewBridge()
    bridge.enqueue({'kind': 'switch', 'switch': 1}, 1280, 720)
    bridge.enqueue({'kind': 'switch', 'switch': 5}, 1280, 720)
    bridge.enqueue({'kind': 'touch', 'x': 640, 'y': 360}, 1280, 720)

    # Invalid switch (out of bounds or shutdown)
    with pytest.raises(ValueError):
        bridge.enqueue({'kind': 'switch', 'switch': 6}, 1280, 720)

    with pytest.raises(ValueError):
        bridge.enqueue({'kind': 'switch', 'switch': 0}, 1280, 720)

    # Invalid touch
    with pytest.raises(ValueError):
        bridge.enqueue({'kind': 'touch', 'x': 2000, 'y': 360}, 1280, 720)


def test_desktop_window_viewport_scaling():
    """Verify coordinate scaling between PC window and canvas."""
    # 960x540 is exact 16:9 -> scale = 0.75, offset (0, 0)
    ox, oy, tw, th, scale = DesktopWindow.get_viewport_geometry(960, 540)
    assert (ox, oy) == (0, 0)
    assert (tw, th) == (960, 540)
    assert scale == 0.75

    cx, cy = DesktopWindow.map_input_pos((480, 270), (960, 540))
    assert cx == 640
    assert cy == 360


def test_remote_display_html_exists():
    """Verify remote_display.html exists and contains necessary elements."""
    html_path = ROOT / 'src/remote_display.html'
    assert html_path.exists()
    content = html_path.read_text(encoding='utf-8')
    assert 'Desk-Pal Remote Display' in content
    assert '/api/preview/frame' in content
    assert '/api/preview/input' in content
