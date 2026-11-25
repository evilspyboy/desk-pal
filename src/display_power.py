"""Power down the Pi panel backlight without disabling touch or its display layout."""
from pathlib import Path
import subprocess
import json

class DisplayPower:
    def __init__(self, root='/sys/class/backlight', state_file=None):
        self.power_file = next(iter(sorted(Path(root).glob('*/bl_power'))), None)
        self.state_file = Path(state_file) if state_file else Path.home() / '.deskpal_display_brightness.json'
        self.is_off = False
        self.error = None

    @staticmethod
    def write_value(path, value):
        if path.read_text().strip() == str(value):
            return
        try:
            path.write_text(str(value))
        except PermissionError:
            subprocess.run(['sudo', '-n', 'tee', str(path)], input=str(value),
                           text=True, capture_output=True, check=True, timeout=3)

    def set_sleeping(self, sleeping):
        if self.power_file is None:
            self.error = 'No panel power control found'
            return False
        # Linux backlight ABI: 0 = unblank; 4 = power down.
        # This panel also needs brightness=0: its driver reports nonzero output with bl_power=4 alone.
        value = '4' if sleeping else '0'
        try:
            brightness = self.power_file.parent / 'brightness'
            current = int(brightness.read_text())
            if sleeping:
                if current > 0:
                    self.state_file.write_text(json.dumps({'brightness': current}))
                self.write_value(brightness, 0)
                self.write_value(self.power_file, value)
            else:
                if current == 0:
                    try:
                        current = int(json.loads(self.state_file.read_text())['brightness'])
                    except (OSError, ValueError, KeyError, TypeError):
                        current = max(1, int((self.power_file.parent / 'max_brightness').read_text()) // 2)
                self.write_value(self.power_file, value)
                self.write_value(brightness, current)
            if self.power_file.read_text().strip() != value:
                raise OSError('Panel did not accept power state')
            if sleeping and int(brightness.read_text()) != 0:
                raise OSError('Backlight did not turn off')
            self.is_off = sleeping
            self.error = None
            return True
        except (OSError, subprocess.SubprocessError) as e:
            self.error = str(e)
            return False
