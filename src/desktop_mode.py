"""Desktop Companion Mode utilities for Desk-Pal.

Supports running scenes, animations, integrations, event queue, and interactive props
in a resizable PC window without Raspberry Pi hardware.
"""
import math


class DesktopDisplayPower:
    """Simulated display power controller for desktop window mode.
    
    Instead of manipulating Linux sysfs backlight nodes (/sys/class/backlight),
    this controller tracks standby state to darken the window surface and wake
    on mouse or key interaction.
    """
    def __init__(self):
        self.is_off = False
        self.error = None

    def set_sleeping(self, sleeping):
        self.is_off = bool(sleeping)
        self.error = None
        return True


class DesktopWindow:
    """Manages scaling and coordinate transformation between the resizable PC window
    and the fixed 1280x720 logical canvas.
    """
    CANVAS_W = 1280
    CANVAS_H = 720

    @classmethod
    def get_viewport_geometry(cls, win_w, win_h):
        """Calculate the letterboxed/pillarboxed viewport rectangle and scale factor."""
        if win_w <= 0 or win_h <= 0:
            return 0, 0, cls.CANVAS_W, cls.CANVAS_H, 1.0
        scale = min(win_w / cls.CANVAS_W, win_h / cls.CANVAS_H)
        target_w = max(1, int(cls.CANVAS_W * scale))
        target_h = max(1, int(cls.CANVAS_H * scale))
        ox = (win_w - target_w) // 2
        oy = (win_h - target_h) // 2
        return ox, oy, target_w, target_h, scale

    @classmethod
    def map_input_pos(cls, win_pos, win_size):
        """Translate window coordinate (x, y) into logical 1280x720 canvas coordinates."""
        win_w, win_h = win_size
        ox, oy, target_w, target_h, scale = cls.get_viewport_geometry(win_w, win_h)
        if scale <= 0:
            return 0, 0
        cx = int((win_pos[0] - ox) / scale)
        cy = int((win_pos[1] - oy) / scale)
        return max(0, min(cls.CANVAS_W - 1, cx)), max(0, min(cls.CANVAS_H - 1, cy))

    @classmethod
    def render(cls, canvas, window, is_sleeping=False, font=None):
        """Scale and blit the 1280x720 canvas onto the resizable window surface."""
        import pygame
        win_w, win_h = window.get_size()
        ox, oy, target_w, target_h, scale = cls.get_viewport_geometry(win_w, win_h)

        window.fill((0, 0, 0))

        if is_sleeping:
            # Standby mode: show dark screen with subtle hint
            if font:
                txt = font.render("[ Desk-Pal Standby - Click or press any key to wake ]", True, (65, 75, 95))
                window.blit(txt, (win_w // 2 - txt.get_width() // 2, win_h // 2 - txt.get_height() // 2))
            return

        if target_w == cls.CANVAS_W and target_h == cls.CANVAS_H:
            window.blit(canvas, (ox, oy))
        else:
            scaled = pygame.transform.smoothscale(canvas, (target_w, target_h))
            window.blit(scaled, (ox, oy))


def run_remote_viewer(remote_url, window_size=(960, 540)):
    """Connect to a remote Raspberry Pi Desk-Pal instance and mirror its display in a PC window."""
    import pygame
    import urllib.request
    import json
    import io
    import time

    pygame.init()
    remote_url = remote_url.rstrip('/')
    pygame.display.set_caption(f"Desk-Pal Remote Display ({remote_url})")
    window = pygame.display.set_mode(window_size, pygame.RESIZABLE)
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 24)
    running = True

    def send_remote(cmd):
        try:
            req = urllib.request.Request(
                f"{remote_url}/api/preview/input",
                data=json.dumps(cmd).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            urllib.request.urlopen(req, timeout=1.0)
        except Exception:
            pass

    last_frame_surf = None
    is_sleeping = False
    status_text = "Connecting..."
    last_status_check = 0

    while running:
        now = time.monotonic()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                window = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                cx, cy = DesktopWindow.map_input_pos(event.pos, window.get_size())
                send_remote({'kind': 'touch', 'x': cx, 'y': cy})
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
                    send_remote({'kind': 'switch', 'switch': event.key - pygame.K_0})
                elif event.key == pygame.K_SPACE:
                    send_remote({'kind': 'switch', 'switch': 1})

        if now - last_status_check > 2.0:
            last_status_check = now
            try:
                res = urllib.request.urlopen(f"{remote_url}/api/preview/status", timeout=1.5)
                st = json.loads(res.read().decode())
                is_sleeping = bool(st.get('sleeping'))
                status_text = "Standby (Sleep)" if is_sleeping else "Live"
            except Exception:
                status_text = "Disconnected"

        try:
            res = urllib.request.urlopen(f"{remote_url}/api/preview/frame?t={int(now * 1000)}", timeout=1.5)
            img_bytes = res.read()
            if img_bytes:
                last_frame_surf = pygame.image.load(io.BytesIO(img_bytes)).convert()
        except Exception:
            pass

        if last_frame_surf:
            DesktopWindow.render(last_frame_surf, window, is_sleeping=is_sleeping, font=font)
        else:
            window.fill((10, 14, 20))
            txt = font.render(f"[ {status_text} - Connecting to {remote_url} ]", True, (120, 140, 180))
            w, h = window.get_size()
            window.blit(txt, (w // 2 - txt.get_width() // 2, h // 2 - txt.get_height() // 2))

        pygame.display.flip()
        clock.tick(20)

    pygame.quit()

