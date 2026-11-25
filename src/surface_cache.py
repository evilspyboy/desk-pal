"""Bounded LRU storage for derived pygame surfaces, not original artwork."""
from collections import OrderedDict


def surface_bytes(value):
    if hasattr(value, 'get_pitch') and hasattr(value, 'get_height'):
        return value.get_pitch() * value.get_height()
    if isinstance(value, (tuple, list)):
        return sum(surface_bytes(item) for item in value)
    return 0


class SurfaceCache(OrderedDict):
    def __init__(self, max_bytes=48*1024*1024, max_entries=128):
        super().__init__()
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self.bytes_used = 0

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def __setitem__(self, key, value):
        if key in self:
            self.bytes_used -= surface_bytes(super().__getitem__(key))
        super().__setitem__(key, value)
        self.move_to_end(key)
        self.bytes_used += surface_bytes(value)
        # Retain one unusually large surface: callers read immediately after
        # inserting, so discarding that entry would break rendering.
        while len(self) > 1 and (len(self) > self.max_entries or self.bytes_used > self.max_bytes):
            _, old = super().popitem(last=False)
            self.bytes_used -= surface_bytes(old)

    def clear(self):
        super().clear()
        self.bytes_used = 0
