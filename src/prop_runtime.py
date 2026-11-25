"""Image prop playback and rendering, independent of character animation."""
from surface_cache import SurfaceCache
import math
import time
from pathlib import Path
import re
import random
import os


def validate_prop_config(cfg):
    library = cfg.get('prop_animations', {})
    if not isinstance(library, dict):
        raise ValueError('Prop library must be an object')
    for sequence in library.values():
        frames = sequence.get('frames', [])
        if not isinstance(frames, list) or len(frames) > 256 or any(not isinstance(url, str) or not re.fullmatch(r'/assets/props/[a-f0-9]{32}\.png', url) for url in frames):
            raise ValueError('Use up to 256 uploaded PNG frames per prop')
        if sequence.get('playback_mode', 'loop') not in ('once', 'repeat', 'loop', 'ping_pong'):
            raise ValueError('Invalid prop playback mode')
        for key, lower, upper in [('fps', 1, 60), ('repeat_count', 1, 1000)]:
            value = float(sequence.get(key, 4 if key == 'fps' else 1))
            if not math.isfinite(value) or not lower <= value <= upper:
                raise ValueError('Invalid prop ' + key)
    rooms = [cfg] + list(cfg.get('scenes', {}).values())
    for room in rooms:
        for prop in room.get('props', []):
            if prop.get('interaction', 'none') not in ('none', 'tv', 'overlay_popup', 'app_action', 'game_script', 'trigger_animation'):
                raise ValueError('Invalid prop tap interaction')
            if prop.get('time_of_day', 'both') not in ('both', 'day', 'night'):
                raise ValueError('Invalid prop day/night visibility')
            if not prop.get('animation_id'):
                continue
            for url in [prop.get('inactive_frame')]:
                if url is not None and not re.fullmatch(r'/assets/props/[a-f0-9]{32}\.png', str(url)):
                    raise ValueError('Invalid inactive prop frame')
            roundness = prop.get('screen_roundness', 0)
            if not isinstance(roundness, (int,float)) or not math.isfinite(roundness) or not 0 <= roundness <= .5:
                raise ValueError('Invalid screen corner rounding')
            choices = prop.get('animation_ids', [])
            if not isinstance(choices, list) or any(not isinstance(a, str) for a in choices):
                raise ValueError('Invalid prop animation choices')
            if prop['animation_id'] not in library or any(a not in library for a in prop.get('animation_ids', [])):
                raise ValueError('Prop placement references a missing animation')
            quad = prop.get('screen_quad')
            if quad is not None and (not isinstance(quad, list) or len(quad) != 4 or any(not isinstance(p, list) or len(p) != 2 or any(not isinstance(v, (int,float)) or not math.isfinite(v) or not 0 <= v <= limit for v,limit in zip(p,(1280,720))) for p in quad)):
                raise ValueError('Screen requires four corners inside the scene')
            if prop.get('trigger', 'always') not in ('always', 'typing', 'pose', 'action'):
                raise ValueError('Invalid prop trigger')
            for key, lower, upper in [('width', 4, 1280), ('x', 0, 1280), ('y', 0, 720), ('rotation', -36000, 36000), ('depth_y', 0, 720)]:
                value = float(prop.get(key, 120 if key == 'width' else 0))
                if not math.isfinite(value) or not lower <= value <= upper:
                    raise ValueError('Invalid prop placement ' + key)


def frame_index(sequence, elapsed):
    count = len(sequence.get('frames', []))
    if not count:
        return None
    tick = max(0, int(elapsed * max(1, min(60, float(sequence.get('fps', 4))))))
    mode = sequence.get('playback_mode', 'loop')
    if mode == 'once':
        return min(tick, count - 1)
    if mode == 'repeat' and tick >= count * max(1, int(sequence.get('repeat_count', 1))):
        return count - 1
    if mode == 'ping_pong' and count > 1:
        tick %= count * 2 - 2
        return tick if tick < count else count * 2 - 2 - tick
    return tick % count


def prop_time_visible(prop, night):
    period = prop.get('time_of_day', 'both')
    return period == 'both' or (period == 'night' if night >= .5 else period == 'day')


def prop_is_active(app, prop):
    """A placement trigger only starts after arrival, while awake."""
    if getattr(app, 'is_sleeping', False):
        return False
    trigger = prop.get('trigger', 'always')
    if trigger == 'always':
        return True
    if trigger in ('typing', 'pose'):
        spot_id = prop.get('typing_spot_id') if trigger == 'typing' else prop.get('pose_spot_id')
        role = 'typing' if trigger == 'typing' else prop.get('pose_animation')
        if getattr(app, 'rest_transition', None):
            return False
        resting = getattr(app, 'active_rest_role', None)
        if resting:
            return bool(spot_id and role == resting
                        and getattr(app, 'active_rest_spot_id', None) == spot_id)
        return bool(spot_id and role and app.current_anim == role
                    and getattr(app, 'target_spot_id', None) == spot_id
                    and math.hypot(app.char_x-app.target_x, app.char_y-app.target_y) < 1)
    if trigger == 'action':
        overlay = getattr(app, 'active_prop_overlays', {}).get(prop['id'])
        return bool(overlay and time.time()-overlay['start_time'] <= overlay.get('duration', 20))
    return False


def warp_screen(image, quad, roundness=0):
    """Cacheable nearest-pixel projection into two screen triangles."""
    import pygame
    if roundness:
        mask = pygame.Surface(image.get_size(), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255,255,255,255), mask.get_rect(), border_radius=round(min(image.get_size())*roundness))
        image = image.copy()
        image.blit(mask, (0,0), special_flags=pygame.BLEND_RGBA_MULT)
    left, top = math.floor(min(p[0] for p in quad)), math.floor(min(p[1] for p in quad))
    width = math.ceil(max(p[0] for p in quad))-left+1
    height = math.ceil(max(p[1] for p in quad))-top+1
    result = pygame.Surface((width, height), pygame.SRCALPHA)
    uv = [(0,0), (1,0), (1,1), (0,1)]
    for ids in ((0,1,2), (0,2,3)):
        a,b,c = [quad[i] for i in ids]
        denominator = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(denominator) < .01:
            continue
        for y in range(max(top, math.floor(min(a[1],b[1],c[1]))), min(top+height, math.ceil(max(a[1],b[1],c[1]))+1)):
            for x in range(max(left, math.floor(min(a[0],b[0],c[0]))), min(left+width, math.ceil(max(a[0],b[0],c[0]))+1)):
                wa = ((b[1]-c[1])*(x+.5-c[0])+(c[0]-b[0])*(y+.5-c[1]))/denominator
                wb = ((c[1]-a[1])*(x+.5-c[0])+(a[0]-c[0])*(y+.5-c[1]))/denominator
                wc = 1-wa-wb
                if min(wa,wb,wc) < -1e-8:
                    continue
                u,v = [sum(weight*uv[i][axis] for weight,i in zip((wa,wb,wc),ids)) for axis in (0,1)]
                result.set_at((x-left,y-top), image.get_at((min(image.get_width()-1,max(0,int(u*image.get_width()))), min(image.get_height()-1,max(0,int(v*image.get_height()))))))
    return result, (left,top)


def draw_props(app, front):
    import pygame
    if not hasattr(app, '_image_prop_state'):
        app._image_prop_state = {}
        app._image_prop_cache = SurfaceCache()
    now = time.monotonic()
    local_assets = Path(__file__).resolve().parent.parent / 'assets'
    root = local_assets if os.environ.get('DESKPAL_LOCAL_PREVIEW') == '1' else Path('/home/admin/assets') if Path('/home/admin/assets').is_dir() else local_assets
    if os.environ.get('DESKPAL_DATA_DIR'):
        root = Path(os.environ['DESKPAL_DATA_DIR']) / 'assets'
    for prop in app.cfg.get('props', []):
        if not prop_time_visible(prop, getattr(app, 'lighting_night_amount', 0)):
            app._image_prop_state.pop((app.cfg.get('active_scene'), prop['id']), None)
            continue
        library = app.cfg.get('prop_animations', {})
        choices = [a for a in prop.get('animation_ids', [prop.get('animation_id')]) if a in library]
        if not choices or prop.get('enabled', True) is False:
            continue
        layer = prop.get('layer', 'depth')
        is_front = layer == 'front' or (layer == 'depth' and prop.get('depth_y', prop.get('y', 0)) > app.char_y)
        if is_front != front:
            continue
        active = prop_is_active(app, prop)
        key = (app.cfg.get('active_scene'), prop['id'])
        state = app._image_prop_state.setdefault(key, {'active': False, 'start': now, 'animation_id': choices[0]})
        if active and not state['active']:
            state['start'] = now
            state['animation_id'] = random.choice(choices)
        if state['animation_id'] not in choices:
            state['animation_id'] = choices[0]
        sequence = library[state['animation_id']]
        state['active'] = active
        if not active and prop.get('hide_when_inactive', False):
            continue
        index = frame_index(sequence, now-state['start'] if active else 0)
        if index is None:
            continue
        url = prop.get('inactive_frame', sequence['frames'][index]) if not active else sequence['frames'][index]
        if not isinstance(url, str) or not url.startswith('/assets/props/'):
            continue
        path = (root / url.removeprefix('/assets/')).resolve()
        if not path.is_relative_to((root / 'props').resolve()):
            continue
        if url not in app._image_prop_cache:
            try:
                app._image_prop_cache[url] = pygame.image.load(str(path)).convert_alpha()
            except (OSError, pygame.error):
                app._image_prop_cache[url] = None
        image = app._image_prop_cache[url]
        if image is None:
            continue
        quad = prop.get('screen_quad')
        if quad:
            cache_key = (url, 'quad', tuple(tuple(p) for p in quad), prop.get('screen_roundness', 0))
            if cache_key not in app._image_prop_cache:
                app._image_prop_cache[cache_key] = warp_screen(image, quad, prop.get('screen_roundness', 0))
            surface, origin = app._image_prop_cache[cache_key]
            app.screen.blit(surface, origin)
            continue
        width = max(4, min(1280, int(prop.get('width', 120))))
        height = max(4, min(1280, int(width * image.get_height()/image.get_width())))
        angle = float(prop.get('rotation', 0)) % 360
        cache_key = (url, width, height, angle)
        if cache_key not in app._image_prop_cache:
            app._image_prop_cache[cache_key] = pygame.transform.rotate(pygame.transform.scale(image, (width, height)), -angle)
        surface = app._image_prop_cache[cache_key]
        app.screen.blit(surface, surface.get_rect(center=(prop.get('x', 640), prop.get('y', 360))))
