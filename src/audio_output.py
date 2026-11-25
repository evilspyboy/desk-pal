"""Choose the saved speaker backend without changing the OS default output."""
import json, platform, subprocess, sys

def playback_command(output, path):
    if output not in ('headphones', 'usb', 'default'):
        raise ValueError('Choose USB speaker, 3.5 mm jack or system default')
    if platform.system() == 'Windows':
        return [sys.executable, '-c', f'import winsound; winsound.PlaySound(r"""{path}""", winsound.SND_FILENAME)']
    try:
        p = subprocess.run(['pw-dump'], capture_output=True, text=True, timeout=2, check=True)
        nodes = [x.get('info', {}).get('props', {}) for x in json.loads(p.stdout)]
        sinks = [x for x in nodes if x.get('media.class') == 'Audio/Sink']
        match = next((x for x in sinks if ('usb' in x.get('node.name', '').lower()) == (output == 'usb') and ('analog' in x.get('node.name', '').lower() or output == 'usb')), None)
        if output == 'default':
            return ['pw-play', str(path)]
        if match:
            return ['pw-play', '--target', match['node.name'], str(path)]
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    if output == 'usb':
        p = subprocess.run(['aplay', '-l'], capture_output=True, text=True, timeout=2, check=True)
        import re
        match = re.search(r'card \d+: (\w+) \[.*?\], device (\d+): USB Audio', p.stdout)
        if not match:
            raise ValueError('No USB playback device found')
        return ['aplay', '-D', 'plughw:' + match[1] + ',' + match[2], str(path)]
    if platform.system() == 'Darwin':
        return ['afplay', str(path)]
    return ['aplay', '-D', 'default' if output == 'default' else 'plughw:Headphones,0', str(path)]
