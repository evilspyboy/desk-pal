"""Scene-local TV viewers; input is isolated from application acknowledgement."""
import copy
import math
import random
import time
from pathlib import Path
import os
from contextlib import nullcontext
from prop_runtime import frame_index, prop_time_visible


def tv_channels(cfg, prop):
    library = cfg.get('prop_animations', {})
    ids = prop.get('animation_ids') or [prop.get('animation_id')]
    return [(key, copy.deepcopy(library[key])) for key in dict.fromkeys(ids)
            if key in library and library[key].get('frames')]


def prop_hit(prop, pos, night=0):
    if prop.get('enabled', True) is False or not prop_time_visible(prop, night):
        return False
    quad = prop.get('screen_quad')
    if quad:
        area = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(quad, quad[1:]+quad[:1]))
        if abs(area) >= 1:
            crosses = [(b[0]-a[0])*(pos[1]-a[1])-(b[1]-a[1])*(pos[0]-a[0])
                       for a, b in zip(quad, quad[1:]+quad[:1])]
            if all(c >= 0 for c in crosses) or all(c <= 0 for c in crosses):
                return True
            if (min(a[0] for a in quad)-20 <= pos[0] <= max(a[0] for a in quad)+20
                    and min(a[1] for a in quad)-20 <= pos[1] <= max(a[1] for a in quad)+20):
                return True
    angle = math.radians(-prop.get('rotation', 0))
    dx, dy = pos[0]-prop.get('x', 0), pos[1]-prop.get('y', 0)
    x, y = dx*math.cos(angle)-dy*math.sin(angle), dx*math.sin(angle)+dy*math.cos(angle)
    width = prop.get('width', 120)
    return abs(x) <= width/2 and abs(y) <= width*3/8


def tv_hit(prop, pos, night=0):
    if prop.get('interaction', 'none') not in ('tv', 'overlay_popup') or prop.get('enabled', True) is False or not prop_time_visible(prop, night):
        return False
    quad = prop.get('screen_quad')
    if quad:
        area = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(quad, quad[1:]+quad[:1]))
        if abs(area) < 1:return False
        # Convex screen corners, rather than a rectangle covering neighboring props.
        crosses = [(b[0]-a[0])*(pos[1]-a[1])-(b[1]-a[1])*(pos[0]-a[0])
                   for a, b in zip(quad, quad[1:]+quad[:1])]
        if all(c >= 0 for c in crosses) or all(c <= 0 for c in crosses):
            return True
        # Include the cabinet and the existing inspection target, so a tap on
        # the TV surround cannot fall through to walking into the television.
        return (min(a[0] for a in quad)-20 <= pos[0] <= max(a[0] for a in quad)+20
                and min(a[1] for a in quad)-20 <= pos[1] <= max(a[1] for a in quad)+20) or (
                    abs(pos[0]-prop.get('x', 0)) <= 60 and abs(pos[1]-prop.get('y', 0)) <= 60)
    angle = math.radians(-prop.get('rotation', 0))
    dx, dy = pos[0]-prop.get('x', 0), pos[1]-prop.get('y', 0)
    x, y = dx*math.cos(angle)-dy*math.sin(angle), dx*math.sin(angle)+dy*math.cos(angle)
    width = prop.get('width', 120)
    return abs(x) <= width/2 and abs(y) <= width*3/8


class TVViewer:
    def __init__(self, cfg, prop, now=None, current_channel=None):
        self.channels = tv_channels(cfg, prop)
        if not self.channels:
            raise ValueError('This TV has no playable prop frames.')
        self.label = prop.get('label') or 'TV'
        self.prop_id = prop['id']
        self.scene = cfg.get('active_scene')
        self.index = next((i for i, (key, _) in enumerate(self.channels) if key == current_channel), 0)
        self.started = time.monotonic() if now is None else now
        self.elapsed = 0
        self.static_until = self.started + .3
        self.buttons = []
        self.cache = {}

    def command(self, command, now=None):
        now = time.monotonic() if now is None else now
        if command in ('previous', 'next'):
            self.index = (self.index + (1 if command == 'next' else -1)) % len(self.channels)
            self.started, self.elapsed, self.static_until = now, 0, now + .3
        return command == 'close'

    def switch(self, number):
        return {2: 'previous', 3: 'next', 5: 'close'}.get(number)

    def touch(self, pos):
        return next((command for command, rect in self.buttons if rect.collidepoint(pos)), None)

    def draw(self, app):
        import pygame
        now = time.monotonic()
        screen = app.screen
        width, height = screen.get_size()
        # A charcoal 1990s CRT, with the apartment visible around the cabinet.
        cabinet = pygame.Rect(0, 0, int(width*.67), int(height*.82))
        cabinet.center = (width//2, height//2)
        shadow = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(shadow, (0, 0, 0, 130), cabinet.move(12, 14), border_radius=14)
        screen.blit(shadow, (0, 0))
        pygame.draw.rect(screen, (25, 28, 32), cabinet, border_radius=14)
        pygame.draw.rect(screen, (80, 84, 89), cabinet, 5, border_radius=14)
        pygame.draw.line(screen, (115, 119, 123), (cabinet.left+14,cabinet.top+8), (cabinet.right-14,cabinet.top+8), 3)
        _, sequence = self.channels[self.index]
        channel_name = sequence.get('name', 'Channel '+str(self.index+1)).replace('TV — ', '')
        content = pygame.Rect(cabinet.left+38, cabinet.top+32, cabinet.width-76, cabinet.height-142)
        pygame.draw.rect(screen, (10, 12, 15), content.inflate(24, 24), border_radius=28)
        pygame.draw.rect(screen, (69, 73, 76), content.inflate(24, 24), 5, border_radius=28)
        title = app.font_sm.render(channel_name, True, (175, 184, 192))
        screen.blit(title, title.get_rect(center=(cabinet.centerx,content.bottom+18)))
        elapsed = now-self.started
        index = frame_index(sequence, elapsed)
        url = sequence['frames'][index]
        if now < self.static_until:
            noise = pygame.Surface((160, 90))
            for y in range(90):
                for x in range(160):
                    value = random.randrange(40, 220)
                    noise.set_at((x, y), (value, value, value))
            screen.blit(pygame.transform.scale(noise, content.size), content)
        else:
            if url not in self.cache:
                if len(self.cache) >= 12:self.cache.pop(next(iter(self.cache)))
                root = Path(os.environ['DESKPAL_DATA_DIR'])/'assets' if os.environ.get('DESKPAL_DATA_DIR') else Path(__file__).resolve().parent.parent/'assets'
                if not os.environ.get('DESKPAL_DATA_DIR') and os.environ.get('DESKPAL_LOCAL_PREVIEW') != '1' and Path('/home/admin/assets').is_dir():root = Path('/home/admin/assets')
                path = (root/url.removeprefix('/assets/')).resolve()
                if not path.is_relative_to((root/'props').resolve()):
                    raise ValueError('TV frames must be uploaded prop assets.')
                try:
                    image = pygame.image.load(str(path)).convert_alpha()
                    scale = min(content.width/image.get_width(), content.height/image.get_height())
                    size = (max(1, round(image.get_width()*scale)), max(1, round(image.get_height()*scale)))
                    self.cache[url] = pygame.transform.scale(image, size)
                except (OSError, pygame.error):self.cache[url] = None
            pygame.draw.rect(screen, (5, 9, 13), content)
            image = self.cache[url]
            if image is not None:screen.blit(image, image.get_rect(center=content.center))
            else:
                text = app.font_md.render('Channel unavailable', True, (240, 210, 160));screen.blit(text, text.get_rect(center=content.center))
        self.buttons = []
        controls_y = cabinet.bottom-53
        # Speaker slots at both ends of the lower bezel.
        for side in (cabinet.left+20, cabinet.right-100):
            for y in range(controls_y-20, controls_y+24, 7):
                pygame.draw.line(screen, (9, 11, 14), (side,y), (side+80,y), 3)
        gap, button_width = 16, 84
        left = cabinet.centerx-(5*button_width+4*gap)//2
        for i, (command, label) in enumerate([('close',''),('previous','CH'),('next','CH'),(None,'VOL -'),(None,'VOL +')]):
            rect = pygame.Rect(left+i*(button_width+gap), controls_y-22, button_width, 44)
            pygame.draw.rect(screen, (12, 14, 17), rect.inflate(6,6), border_radius=5)
            pygame.draw.rect(screen, (58, 62, 67), rect, border_radius=3)
            pygame.draw.line(screen, (105, 110, 115), rect.topleft, rect.topright, 2)
            ink = (210, 218, 223) if command else (135, 143, 148)
            if command == 'close':
                cx, cy = rect.center
                pygame.draw.arc(screen, ink, pygame.Rect(cx-12,cy-12,24,24), -math.pi/2+.55, 3*math.pi/2-.55, 3)
                pygame.draw.line(screen, ink, (cx,cy-16), (cx,cy-2), 3)
            else:
                text = app.font_sm.render(label, True, ink)
                screen.blit(text,text.get_rect(center=(rect.centerx-10 if command else rect.centerx,rect.centery)))
                if command in ('previous','next'):
                    cx, cy = rect.right-18, rect.centery
                    sign = 1 if command == 'previous' else -1
                    pygame.draw.lines(screen, ink, False, [(cx-6,cy-sign*4),(cx,cy+sign*4),(cx+6,cy-sign*4)], 3)
            if command:self.buttons.append((command,rect.inflate(8,16)))
        pygame.draw.circle(screen, (80, 224, 113), (left-15,controls_y), 4)
        queue = getattr(app, 'activity_queue', None)
        with queue.lock if queue else nullcontext():
            active = queue.active[0] if queue and queue.active else {}
            pending = list(queue.items) if queue else []
        waiting = bool(getattr(app, 'integration_attention', None) or getattr(app, 'active_popup_modal', None)
                       or active.get('_attention_waiting') and not active.get('_attention_acknowledged')
                       or any(item[0].get('attention_needed') or item[0].get('attention_until_interaction') for item in pending))
        if waiting:
            text = app.font_sm.render('Attention waiting - close TV to view', True, (255, 204, 92))
            pygame.draw.rect(screen, (20, 20, 26), (content.x, content.bottom-40, content.width, 40))
            screen.blit(text, (content.x+12, content.bottom-37))


def open_tv(app, prop):
    state = getattr(app, '_image_prop_state', {}).get((app.cfg.get('active_scene'), prop['id']), {})
    app.tv_viewer = TVViewer(app.cfg, prop, current_channel=state.get('animation_id'))
    app.audit_activity('interactive_prop_opened', prop_id=prop['id'], view='tv')


def close_tv(app, reason='closed'):
    viewer = getattr(app, 'tv_viewer', None)
    if viewer:
        app.audit_activity('interactive_prop_closed', prop_id=viewer.prop_id, view='tv', reason=reason)
        app.tv_viewer = None


def tv_switch(app, number):
    viewer = getattr(app, 'tv_viewer', None)
    if not viewer:return False
    if number in (1, 6):
        close_tv(app, 'sleep' if number == 1 else 'power')
        return False
    command = viewer.switch(number)
    if command and viewer.command(command):close_tv(app)
    return True


def tv_touch(app, pos):
    viewer = getattr(app, 'tv_viewer', None)
    if not viewer:return False
    command = viewer.touch(pos)
    if command and viewer.command(command):close_tv(app)
    return True
