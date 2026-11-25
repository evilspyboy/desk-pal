"""Main-thread rendering bridge for the isolated local browser preview."""
import io,math,queue,time
from concurrent.futures import Future

class PreviewDisplayPower:
    def __init__(self):self.is_off=False;self.error=None
    def set_sleeping(self,value):self.is_off=bool(value)

class PreviewBridge:
    def __init__(self):
        self.inputs = queue.SimpleQueue()
        self.calls = queue.SimpleQueue()
        self.frame = None
        self.frame_number = 0
        self.last_frame = 0
        self.last_requested = 0

    def call(self, callback):
        future = Future()
        self.calls.put((future, callback))
        return future.result(timeout=120)

    def request_frame(self):
        """Mark bridge as actively observed and return the latest rendered frame."""
        self.last_requested = time.monotonic()
        return self.frame

    def enqueue(self, command, width, height):
        if command.get('kind') == 'switch':
            value = command.get('switch')
            if type(value) is not int or not 1 <= value <= 5:
                raise ValueError('Preview supports buttons 1–5; shutdown is disabled')
            self.inputs.put(('switch', value))
        elif command.get('kind') == 'touch':
            x, y = command.get('x'), command.get('y')
            if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in (x, y)) or not 0 <= x < width or not 0 <= y < height:
                raise ValueError('Touch must be inside the preview')
            self.inputs.put(('touch', (int(x), int(y))))
        else:
            raise ValueError('Unknown preview input')

    def tick_inputs(self, app):
        while not self.calls.empty():
            future, callback = self.calls.get_nowait()
            try:
                future.set_result(callback())
            except Exception as error:
                future.set_exception(error)
        while not self.inputs.empty():
            kind, value = self.inputs.get_nowait()
            if kind == 'switch':
                app.on_switch_pressed(value)
            else:
                app.handle_touch_down(value)
                app.handle_touch_up()

    def publish(self, surface, sleeping=False):
        now = time.monotonic()
        # On-demand capture: if no client has polled or requested a frame in the last 4.0 seconds,
        # skip JPEG compression completely to preserve CPU cycles on Raspberry Pi.
        if now - self.last_requested > 4.0:
            return
        # Cap frame rate at ~15 FPS (66ms)
        if now - self.last_frame < 0.066:
            return
        import pygame
        if sleeping:
            surface = pygame.Surface(surface.get_size())
        stream = io.BytesIO()
        pygame.image.save(surface, stream, 'preview.jpg')
        self.frame = stream.getvalue()
        self.frame_number += 1
        self.last_frame = now
