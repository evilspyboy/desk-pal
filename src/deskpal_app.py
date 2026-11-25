#!/usr/bin/env python3
"""
Desk-Pal 16-bit Ambient Desktop Companion GUI & Web Studio Bridge
Runs on Raspberry Pi 4 with 5-inch DSI Touchscreen (1280x720).

Features:
- LucasArts SCUMM style perspective depth scaling based on Y-position
- Built-in Lightweight HTTP Server on port 7777:
    * Serves interactive Web Studio at http://<pi-ip>:7777/
    * REST API for room geometry & obstacle configuration (GET /api/config, POST /api/config)
    * Instant Pygame hot-reloading from PC web browser without restart
    * Event Ingestion for external apps (POST /api/v1/event, POST /api/v1/heartbeat)
- On-device Visual Walkbox & Obstacle Editor (tap [EDIT] on top bar):
    * Completely unrestricted obstacle block placement (move anywhere)
    * Interactive stretch / resize handles and discrete W/H controls
    * [HIDE CHAR] toggle for unobstructed background inspection
    * Dedicated [DONE] and [SAVE] buttons
- 6-Switch GPIO hardware integration with live on-screen visual feedback:
    * SW 1: Sleep / Wake toggle (tap screen or any key to wake)
    * SW 2: BottyMcBotface status
    * SW 3: Fuel Tracker status
    * SW 4: Store Orders status
    * SW 5: Travel Deals status
    * SW 6: Safe Shutdown modal (tap) or 2s hold for direct poweroff
- Top-Right Touchscreen [EXIT] button to cleanly return to Pi Desktop
"""

import sys
import os
import json
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
import random
import threading
import queue
import urllib.parse
import subprocess
import shutil
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from surface_cache import SurfaceCache
import math
import heapq
import copy
import pygame
from display_power import DisplayPower
from scene_world import ensure_world, sync_scene, activate_scene, scene_id, portal, find_route
from scene_lighting import lighting_state, lighting_details, validate_lighting
from action_targets import resolve_action_placement
from system_health import ConnectivityMonitor, update_notifications, settings as health_settings

if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":0"

try:
    from gpiozero import Button
    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "room_config.json")
if os.environ.get('DESKPAL_DATA_DIR'):
    CONFIG_PATH = os.path.join(os.path.abspath(os.environ['DESKPAL_DATA_DIR']), 'config', 'room_config.json')
def pi_path(relative=''):
    if os.environ.get('DESKPAL_DATA_DIR'):
        return os.path.join(os.path.abspath(os.environ['DESKPAL_DATA_DIR']), relative)
    if os.environ.get('DESKPAL_LOCAL_PREVIEW') == '1':
        return os.path.abspath(os.path.join(os.path.dirname(CONFIG_PATH), '..', relative))
    return '/home/admin' + ('/' + relative if relative else '')

DEFAULT_CONFIG_PATH_PI = pi_path('config/room_config.json')

def get_active_config_path():
    if os.environ.get('DESKPAL_LOCAL_PREVIEW') == '1' or os.environ.get('DESKPAL_DATA_DIR'):
        return CONFIG_PATH
    for p in [DEFAULT_CONFIG_PATH_PI, CONFIG_PATH, "room_config.json"]:
        if os.path.exists(p):
            return p
    return CONFIG_PATH

def load_config():
    p = get_active_config_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] Error reading {p}: {e}")
    return {
        "palette": {
            "background": [24, 20, 37], "surface": [38, 43, 68], "surface_light": [58, 68, 102],
            "border": [90, 105, 136], "accent": [240, 160, 80], "green": [106, 190, 48],
            "red": [217, 87, 99], "blue": [75, 105, 204], "text": [238, 238, 240], "text_dim": [139, 155, 180]
        },
        "switches": [
            {"id": 1, "bcm": 26, "pin": 37, "name": "Sleep",    "app_id": "system_sleep", "color": [155, 171, 178]},
            {"id": 2, "bcm": 19, "pin": 35, "name": "BMCBF",    "app_id": "bmcbf",        "color": [217, 160, 102]},
            {"id": 3, "bcm": 13, "pin": 33, "name": "Fuel",     "app_id": "fuel_tracker", "color": [106, 190, 48]},
            {"id": 4, "bcm": 6,  "pin": 31, "name": "Orders",   "app_id": "store_orders", "color": [240, 160, 80]},
            {"id": 5, "bcm": 5,  "pin": 29, "name": "Travel",   "app_id": "travel_deals", "color": [75, 105, 204]},
            {"id": 6, "bcm": 0,  "pin": 27, "name": "Shutdown", "app_id": "system_power", "color": [217, 87, 99]}
        ],
        "walkable_trapezoid": {
            "y_min": 516, "y_max": 700,
            "scale_at_y_min": 275, "scale_at_y_max": 385,
            "back_x_min": 424, "back_x_max": 941,
            "front_x_min": 225, "front_x_max": 1136
        },
        "obstacles": [
            {"id": "floor_books", "x": 480, "y": 510, "w": 120, "h": 50, "label": "Floor Clutter"}
        ],
        "props": [
            {"id": "pc_desk",    "x": 390,  "y": 560, "label": "Botty Terminal", "target_app": "bmcbf"},
            {"id": "postbox",    "x": 1020, "y": 660, "label": "Orders Mailbox", "target_app": "store_orders"},
            {"id": "fuel_gauge", "x": 400,  "y": 520, "label": "Fuel Monitor",   "target_app": "fuel_tracker"},
            {"id": "window",     "x": 640,  "y": 515, "label": "Travel Window",  "target_app": "travel_deals"}
        ],
        "event_mappings": [
            {"id": "map_fuel_drop", "app_id": "fuel_tracker", "event": "fuel_drop", "action": "walk_to_prop", "target_prop": "fuel_gauge", "animation": "inspect", "speech": "{summary}"}
        ]
    }


def _config_save_paths(local_preview=False):
    """Return deduplicated, valid config paths to save to."""
    if local_preview or os.environ.get('DESKPAL_LOCAL_PREVIEW') == '1' or os.environ.get('DESKPAL_DATA_DIR'):
        return [os.path.abspath(get_active_config_path())]
    paths = []
    script_dir_name = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
    config_abs = os.path.abspath(CONFIG_PATH)
    for raw in [get_active_config_path(), CONFIG_PATH, DEFAULT_CONFIG_PATH_PI]:
        ap = os.path.abspath(raw)
        # Only include repo-relative ../config/room_config.json when running from a src/ checkout.
        if ap == config_abs and script_dir_name != 'src':
            continue
        if ap in ('/config/room_config.json', '/home/config/room_config.json'):
            continue
        if ap not in paths:
            paths.append(ap)
    return paths


def save_config(cfg):
    """Save room configuration to disk, syncing local preview and device paths."""
    for p in _config_save_paths():
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            print(f"[CONFIG] Saved config to {p}")
        except Exception as e:
            print(f"[WARN] Could not save config to {p}: {e}")


def obstacle_points(obs):
    """Clockwise ground footprint; old rectangular blocks remain compatible."""
    if obs.get("points"):
        return [tuple(p) for p in obs["points"]]
    x, y, w, h = (obs[k] for k in ("x", "y", "w", "h"))
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def set_obstacle_bounds(obs, **changes):
    old = {k: obs[k] for k in ('x', 'y', 'w', 'h')}
    new = dict(old, **changes)
    if obs.get('points'):
        obs['points'] = [[new['x']+(x-old['x'])*new['w']/max(1, old['w']),
                          new['y']+(y-old['y'])*new['h']/max(1, old['h'])] for x, y in obs['points']]
    obs.update(new)


def point_in_polygon(point, polygon):
    x, y = point
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        cross = (x-a[0])*(b[1]-a[1]) - (y-a[1])*(b[0]-a[0])
        if abs(cross) < 1e-7 and min(a[0], b[0])-1e-7 <= x <= max(a[0], b[0])+1e-7 and min(a[1], b[1])-1e-7 <= y <= max(a[1], b[1])+1e-7:
            return True
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return inside


def segment_intersection(a, b, c, d):
    rx, ry = b[0]-a[0], b[1]-a[1]
    sx, sy = d[0]-c[0], d[1]-c[1]
    denom = rx*sy-ry*sx
    if abs(denom) < 1e-9:
        return None
    qx, qy = c[0]-a[0], c[1]-a[1]
    t, u = (qx*sy-qy*sx)/denom, (qx*ry-qy*rx)/denom
    if -1e-9 <= t <= 1+1e-9 and -1e-9 <= u <= 1+1e-9:
        return (a[0]+t*rx, a[1]+t*ry)
    return None


def valid_floor_points(points):
    if not isinstance(points, list) or not 3 <= len(points) <= 32:
        return False
    if any(not isinstance(p, (list, tuple)) or len(p) != 2 or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in p) for p in points):
        return False
    area = 0
    for a, b in zip(points, points[1:]+points[:1]):
        area += a[0]*b[1]-b[0]*a[1]
        if math.dist(a,b) < .1 or any((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]) < -.01 for p in points):
            return False
    return area > 100


def floor_perspective_height(trap, y):
    """Calibrate at the same polygon boundary points as the editor limit samples."""
    back, front = trap['y_min'], trap['y_max']
    if trap.get('points'):
        points = clip_floor_to_screen(trap['points'])
        lo, hi = min(p[0] for p in points), max(p[0] for p in points)
        bounds = []
        for fraction, rear in ((.25, True), (.75, False)):
            x = lo+(hi-lo)*fraction
            ys = []
            for a, b in zip(points, points[1:]+points[:1]):
                if min(a[0], b[0]) <= x <= max(a[0], b[0]):
                    if abs(b[0]-a[0]) < 1e-9: ys.extend([a[1], b[1]])
                    else: ys.append(a[1]+(x-a[0])*(b[1]-a[1])/(b[0]-a[0]))
            bounds.append(min(ys) if rear else max(ys))
        back, front = bounds
    t = max(0, min(1, (y-back)/max(1, front-back)))
    return trap['scale_at_y_min']+t*(trap['scale_at_y_max']-trap['scale_at_y_min'])


def foreground_depth(obstacle, x):
    override = obstacle.get('foreground', {}).get('depth_y')
    if isinstance(override, (int, float)) and math.isfinite(override):
        return override
    points = obstacle_points(obstacle)
    x = max(min(p[0] for p in points), min(x, max(p[0] for p in points)))
    intersections = []
    for a, b in zip(points, points[1:]+points[:1]):
        if min(a[0], b[0])-1e-9 <= x <= max(a[0], b[0])+1e-9:
            if abs(b[0]-a[0]) < 1e-9:
                intersections.extend([a[1], b[1]])
            else:
                intersections.append(a[1]+(x-a[0])*(b[1]-a[1])/(b[0]-a[0]))
    return max(intersections)


def clip_vector_region(points, origin, normal):
    clipped = []
    side = lambda p: (p[0]-origin[0])*normal[0]+(p[1]-origin[1])*normal[1]
    for p, q in zip(points, points[1:]+points[:1]):
        dp, dq = side(p), side(q)
        if dp >= 0: clipped.append(p)
        if (dp >= 0) != (dq >= 0):
            t = dp/(dp-dq)
            clipped.append([p[0]+t*(q[0]-p[0]), p[1]+t*(q[1]-p[1])])
    return clipped


def vector_leg_regions(points, vector, bounds):
    sx, sy, sw, sh = bounds[:4]
    flip = len(bounds) > 4 and bounds[4]
    guides = vector.get('legs') or [dict(points=vector.get('points', []))]
    world = []
    for guide in guides:
        ps = guide.get('points', [])
        if len(ps) != 3 or not all(len(p) == 2 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in p) for p in ps): continue
        world.append([[sx+sw*(1-p[0] if flip else p[0]), sy+sh*p[1]] for p in ps])
    regions = []
    for i, (_, knee, foot) in enumerate(world):
        region = points
        for j, (_, other, _) in enumerate(world):
            if i == j: continue
            midpoint = [(knee[0]+other[0])/2, (knee[1]+other[1])/2]
            region = clip_vector_region(region, midpoint, [knee[0]-other[0], knee[1]-other[1]])
        normal = [foot[0]-knee[0], foot[1]-knee[1]]
        if normal[1] > 1:
            region = clip_vector_region(region, knee, normal)
            if len(region) >= 3: regions.append(region)
    return regions


def foreground_outlines(obstacles, x, y, role='', spot_id=None, sprite_bounds=None, placement_vector=None):
    outlines = []
    prepared = []
    for o in obstacles:
        fg = o.get('foreground', {})
        if fg.get('parts') or placement_vector and o.get('id') == placement_vector.get('object_id'):
            seated = spot_id in fg.get('seated_spot_ids', []) and role in fg.get('seated_roles', [])
            surfaces = fg.get('parts') or [dict(id='outline', outline=fg.get('outline', []))]
            parts = [dict(part, outline=outline) for part in surfaces for outline in (part.get('seated_outlines', [part.get('outline', [])]) if seated else [part.get('outline', [])])]
            for part in parts:
                vector_part = bool(placement_vector and o.get('id') == placement_vector.get('object_id') and part.get('id') == placement_vector.get('part_id'))
                if seated and part.get('seated_layer') == 'behind' and not vector_part: continue
                mode = 'always_front' if vector_part or seated and part.get('seated_layer') == 'front' else fg.get('mode', 'footprint')
                points = part.get('outline', [])
                if vector_part and sprite_bounds and placement_vector.get('legs'):
                    prepared.extend(dict(o, foreground=dict(fg, outline=region, mode=mode)) for region in vector_leg_regions(points, placement_vector, sprite_bounds))
                    continue
                edge = part.get('seated_clip_line')
                if placement_vector and sprite_bounds and o.get('id') == placement_vector.get('object_id') and part.get('id') == placement_vector.get('part_id'):
                    sx, sy, sw, sh = sprite_bounds[:4]
                    flip = len(sprite_bounds) > 4 and sprite_bounds[4]
                    guide = placement_vector.get('points', [])
                    if len(guide) == 3 and all(len(p) == 2 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in p) for p in guide):
                        hip, knee, foot = [[sx+sw*(1-p[0] if flip else p[0]), sy+sh*p[1]] for p in guide]
                        nx, ny = foot[0]-knee[0], foot[1]-knee[1]
                        if ny > 1:
                            edge = [[knee[0]-ny, knee[1]+nx], [knee[0]+ny, knee[1]-nx]]
                split = part.get('seated_body_front_until')
                if seated and not vector_part and sprite_bounds and isinstance(split, (int, float)):
                    sx, sy, sw, sh = sprite_bounds[:4]
                    edge = [[sx, sy+sh*split], [sx+sw, sy+sh*split]]
                if (seated or vector_part) and edge and len(edge) == 2:
                    # Seat fabric is beneath the hips; only its near edge/frame
                    # covers the legs. Clip in scene coordinates, independent of pose size.
                    a, b = sorted(edge, key=lambda p: p[0])
                    side = lambda p: (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
                    clipped = []
                    for p, q in zip(points, points[1:]+points[:1]):
                        dp, dq = side(p), side(q)
                        if dp >= 0: clipped.append(p)
                        if (dp >= 0) != (dq >= 0):
                            t = dp/(dp-dq)
                            clipped.append([p[0]+t*(q[0]-p[0]), p[1]+t*(q[1]-p[1])])
                    points = clipped
                prepared.append(dict(o, foreground=dict(fg, outline=points, mode=mode)))
            continue
        placement = fg.get('placement_masks', {}).get(spot_id, {})
        if role in placement.get('roles', []):
            prepared.extend(dict(o, foreground=dict(fg, outline=p)) for p in placement.get('outlines', []))
        else:
            prepared.append(o)
    for o in prepared:
        fg = o.get('foreground', {})
        points = fg.get('outline', [])
        if not fg.get('enabled', True) or len(points) < 3:
            continue
        if fg.get('mode') == 'always_front':
            outlines.append(points)
            continue
        # The front boundary may change slope at either side of an angled footprint.
        lo, hi = min(p[0] for p in points), max(p[0] for p in points)
        breaks = sorted({lo, hi, *(p[0] for p in obstacle_points(o) if lo < p[0] < hi)})
        ranges = []
        for left, right in zip(breaks, breaks[1:]):
            da, db = foreground_depth(o, left)-y, foreground_depth(o, right)-y
            if max(da, db) <= 0:
                continue
            if (da > 0) != (db > 0):
                crossing = left+(right-left)*(-da)/(db-da)
                if da <= 0: left = crossing
                else: right = crossing
            if right-left < 1e-9: continue
            if ranges and abs(ranges[-1][1]-left) < 1e-9: ranges[-1][1] = right
            else: ranges.append([left, right])
        for left, right in ranges:
            clipped = points
            for boundary, sign in ((left, 1), (right, -1)):
                source, clipped = clipped, []
                for a, b in zip(source, source[1:]+source[:1]):
                    da, db = (a[0]-boundary)*sign, (b[0]-boundary)*sign
                    if da >= 0: clipped.append(a)
                    if (da >= 0) != (db >= 0):
                        t = da/(da-db)
                        clipped.append([boundary, a[1]+t*(b[1]-a[1])])
            if len(clipped) >= 3: outlines.append(clipped)
    return outlines


def clip_floor_to_screen(points, width=1280, height=720):
    """Intersect a convex floor with the visible scene, retaining edge intersections."""
    points = [tuple(p) for p in points]
    for axis, bound, sign in ((0,0,1),(0,width,-1),(1,0,1),(1,height,-1)):
        source, points = points, []
        for a,b in zip(source, source[1:]+source[:1]):
            a_inside, b_inside = (a[axis]-bound)*sign >= 0, (b[axis]-bound)*sign >= 0
            if a_inside:
                points.append(a)
            if a_inside != b_inside:
                t = (bound-a[axis])/(b[axis]-a[axis])
                points.append((a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])))
    points = [p for i,p in enumerate(points) if math.dist(p,points[i-1]) > .01]
    return points if len(points) >= 3 else []


class FloorNavigation:
    def __init__(self, trap, obstacles):
        self.floor = [tuple(p) for p in trap['points']] if trap.get('points') else [(trap['back_x_min'], trap['y_min']), (trap['back_x_max'], trap['y_min']),
                      (trap['front_x_max'], trap['y_max']), (trap['front_x_min'], trap['y_max'])]
        self.floor = clip_floor_to_screen(self.floor)
        self.blocks = [obstacle_points(o) for o in obstacles]
        self.edges = [(a, b) for poly in self.blocks for a, b in zip(poly, poly[1:]+poly[:1])]
        self._nodes = None

    def free(self, point):
        return 0 <= point[0] <= 1280 and 0 <= point[1] <= 720 and point_in_polygon(point, self.floor) and not any(point_in_polygon(point, p) for p in self.blocks)

    def clear(self, a, b):
        # Floors are validated convex, so a segment between in-floor endpoints stays in-floor.
        return self.free(a) and self.free(b) and not any(segment_intersection(a, b, c, d) is not None for c, d in self.edges)

    def nodes(self):
        if self._nodes is None:
            vertices = [p for poly in [self.floor] + self.blocks for p in poly]
            all_edges = self.edges + list(zip(self.floor, self.floor[1:]+self.floor[:1]))
            for i, (a, b) in enumerate(all_edges):
                for c, d in all_edges[i+1:]:
                    hit = segment_intersection(a, b, c, d)
                    if hit is not None:
                        vertices.append(hit)
            candidates = set()
            for x, y in vertices:
                for i in range(16):
                    angle = i*math.tau/16
                    p = (round(x+2*math.cos(angle), 5), round(y+2*math.sin(angle), 5))
                    if self.free(p):
                        candidates.add(p)
            self._nodes = sorted(candidates)
        return self._nodes

    def nearest(self, point):
        if self.free(point):
            return tuple(point)
        candidates = list(self.nodes())
        # Include edge projections, so a blocked target moves to the nearest boundary.
        for poly in [self.floor] + self.blocks:
            for a, b in zip(poly, poly[1:]+poly[:1]):
                dx, dy = b[0]-a[0], b[1]-a[1]
                t = max(0, min(1, ((point[0]-a[0])*dx+(point[1]-a[1])*dy)/max(1e-9, dx*dx+dy*dy)))
                x, y = a[0]+t*dx, a[1]+t*dy
                for ox, oy in [(0, 0), (2, 0), (-2, 0), (0, 2), (0, -2)]:
                    p = (x+ox, y+oy)
                    if self.free(p):
                        candidates.append(p)
        return min(candidates, key=lambda p: math.dist(point, p)) if candidates else None

    def route(self, start, goal):
        if not self.free(start) or not self.free(goal):
            return []
        if self.clear(start, goal):
            return [goal]
        nodes = [tuple(start), tuple(goal)] + self.nodes()
        costs, parents, queue = {0: 0}, {}, [(math.dist(start, goal), 0, 0)]
        closed = set()
        while queue:
            _, cost, i = heapq.heappop(queue)
            if i in closed:
                continue
            if i == 1:
                path = []
                while i != 0:
                    path.append(nodes[i])
                    i = parents[i]
                return list(reversed(path))
            closed.add(i)
            for j, p in enumerate(nodes):
                if j in closed:
                    continue
                candidate = cost + math.dist(nodes[i], p)
                if candidate < costs.get(j, float('inf')) and self.clear(nodes[i], p):
                    costs[j], parents[j] = candidate, i
                    heapq.heappush(queue, (candidate+math.dist(p, goal), candidate, j))
        return []


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def get_system_stats():
    """Returns system memory (RAM) and storage (Disk) usage statistics."""
    stats = {
        "memory": {
            "total_bytes": 0, "used_bytes": 0, "available_bytes": 0,
            "total_gb": 0.0, "used_gb": 0.0, "available_gb": 0.0,
            "percent": 0.0
        },
        "storage": {
            "total_bytes": 0, "used_bytes": 0, "available_bytes": 0,
            "total_gb": 0.0, "used_gb": 0.0, "available_gb": 0.0,
            "percent": 0.0
        }
    }

    # 1. Storage / Disk
    try:
        root_path = "/" if os.name != "nt" else (os.path.splitdrive(os.path.abspath("."))[0] or "C:")
        st = shutil.disk_usage(root_path)
        t_gb = round(st.total / (1024**3), 1)
        u_gb = round(st.used / (1024**3), 1)
        f_gb = round(st.free / (1024**3), 1)
        pct = round((st.used / st.total * 100), 1) if st.total > 0 else 0.0
        stats["storage"] = {
            "total_bytes": st.total,
            "used_bytes": st.used,
            "available_bytes": st.free,
            "total_gb": t_gb,
            "used_gb": u_gb,
            "available_gb": f_gb,
            "percent": pct
        }
    except Exception:
        pass

    # 2. Memory / RAM
    mem_done = False
    if os.path.exists("/proc/meminfo"):
        try:
            mem = {}
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip().split()[0]
                        try:
                            mem[key] = int(val) * 1024
                        except ValueError:
                            pass
            tot = mem.get("MemTotal", 0)
            avail = mem.get("MemAvailable", mem.get("MemFree", 0))
            used = max(0, tot - avail)
            pct = round((used / tot * 100), 1) if tot > 0 else 0.0
            stats["memory"] = {
                "total_bytes": tot,
                "used_bytes": used,
                "available_bytes": avail,
                "total_gb": round(tot / (1024**3), 2),
                "used_gb": round(used / (1024**3), 2),
                "available_gb": round(avail / (1024**3), 2),
                "percent": pct
            }
            mem_done = True
        except Exception:
            pass

    if not mem_done:
        try:
            import psutil
            vm = psutil.virtual_memory()
            stats["memory"] = {
                "total_bytes": vm.total,
                "used_bytes": vm.used,
                "available_bytes": vm.available,
                "total_gb": round(vm.total / (1024**3), 2),
                "used_gb": round(vm.used / (1024**3), 2),
                "available_gb": round(vm.available / (1024**3), 2),
                "percent": float(vm.percent)
            }
            mem_done = True
        except Exception:
            pass

    if not mem_done and os.name == "nt":
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ('dwLength', ctypes.c_ulong),
                    ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', ctypes.c_ulonglong),
                    ('ullAvailPhys', ctypes.c_ulonglong),
                    ('ullTotalPageFile', ctypes.c_ulonglong),
                    ('ullAvailPageFile', ctypes.c_ulonglong),
                    ('ullTotalVirtual', ctypes.c_ulonglong),
                    ('ullAvailVirtual', ctypes.c_ulonglong),
                    ('sullAvailExtendedVirtual', ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            tot = stat.ullTotalPhys
            avail = stat.ullAvailPhys
            used = tot - avail
            stats["memory"] = {
                "total_bytes": tot,
                "used_bytes": used,
                "available_bytes": avail,
                "total_gb": round(tot / (1024**3), 2),
                "used_gb": round(used / (1024**3), 2),
                "available_gb": round(avail / (1024**3), 2),
                "percent": float(stat.dwMemoryLoad)
            }
        except Exception:
            pass

    return stats


class DeskPalHTTPHandler(BaseHTTPRequestHandler):
    app_ref = None  # Reference to DeskPalApp instance

    def log_message(self, format, *args):
        # Suppress standard logging to keep console clean
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if urllib.parse.urlparse(self.path).path == '/api/system-health':
            monitor=getattr(DeskPalHTTPHandler.app_ref,'connectivity_monitor',None)
            data=json.dumps(monitor.snapshot() if monitor else {'status':'unavailable'}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
        if urllib.parse.urlparse(self.path).path == '/api/debug_app':
            try:
                from scene_world import scene_id
                app = DeskPalHTTPHandler.app_ref
                if not app:
                    data = json.dumps({'error': 'app_ref is None'}).encode()
                else:
                    choice = getattr(app, 'standby_choice', None)
                    data = json.dumps({
                        'is_sleeping': getattr(app, 'is_sleeping', False),
                        'current_anim': str(getattr(app, 'current_anim', None)),
                        'target_animation': str(getattr(app, 'target_animation', None)),
                        'active_rest_role': str(getattr(app, 'active_rest_role', None)),
                        'rest_transition': getattr(app, 'rest_transition', None),
                        'standby_settled_at': getattr(app, 'standby_settled_at', None),
                        'now_monotonic': time.monotonic(),
                        'status_msg': getattr(app, 'status_msg', None),
                        'standby_choice': [choice[0], (choice[1].get('id') if isinstance(choice[1], dict) else None), choice[2]] if (choice and len(choice) >= 3) else None,
                        'target_spot_id': getattr(app, 'target_spot_id', None),
                        'idle_waiting': getattr(app, 'idle_waiting', False),
                        'wander_timer': getattr(app, 'wander_timer', 0),
                        'gesture_role': getattr(app, 'gesture_role', None),
                        'display_power_exists': getattr(app, 'display_power', None) is not None,
                        'display_power_type': type(getattr(app, 'display_power', None)).__name__ if getattr(app, 'display_power', None) else None,
                        'display_power_file': str(getattr(getattr(app, 'display_power', None), 'power_file', None)),
                        'display_power_is_off': getattr(getattr(app, 'display_power', None), 'is_off', False),
                        'display_power_error': str(getattr(getattr(app, 'display_power', None), 'error', None)),
                        'char_pos': [getattr(app, 'char_x', 0), getattr(app, 'char_y', 0)],
                        'target_pos': [getattr(app, 'target_x', 0), getattr(app, 'target_y', 0)],
                        'scene': scene_id(app.cfg) if getattr(app, 'cfg', None) else None,
                        'pending_idle_destination': bool(getattr(app, 'pending_idle_destination', None)),
                        'scene_journey': len(getattr(app, 'scene_journey', []) or []),
                    }).encode()
            except Exception as e:
                data = json.dumps({'error': str(e)}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ('/api/preview/status', '/api/preview/frame'):
            app = DeskPalHTTPHandler.app_ref
            bridge = getattr(app, 'preview_bridge', None)
            if path.endswith('/frame'):
                frame = bridge.request_frame() if bridge else None
                if not frame:
                    self.send_error(503, 'Preview frame is not ready')
                    return
                data = frame
                content_type = 'image/jpeg'
            else:
                data = json.dumps({
                    'enabled': bool(bridge),
                    'mode': 'local' if getattr(app, 'local_preview', False) else 'remote',
                    'is_local': bool(getattr(app, 'local_preview', False)),
                    'width': app.width,
                    'height': app.height,
                    'frame': bridge.frame_number if bridge else 0,
                    'sleeping': app.is_sleeping
                }).encode()
                content_type = 'application/json'
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path == '/api/integration-packages/download':
            try:
                from integration_packages import export_integration
                app_id = urllib.parse.parse_qs(parsed.query).get('application', [''])[0]
                data = export_integration(copy.deepcopy(DeskPalHTTPHandler.app_ref.cfg), app_id)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Disposition', 'attachment; filename="deskpal-integration.json"')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as error:
                self.send_error(400, str(error))
            return

        if path == '/api/character-packages/download':
            try:
                from character_packages import export_character
                character = urllib.parse.parse_qs(parsed.query).get('character', [''])[0]
                config_dir = os.path.dirname(get_active_config_path())
                data = export_character(copy.deepcopy(DeskPalHTTPHandler.app_ref.cfg), character, os.path.join(config_dir, '..', 'assets'), config_dir)
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Disposition', 'attachment; filename="deskpal-character.zip"')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as error:
                self.send_error(400, str(error))
            return

        if path == '/api/scene-packages/download':
            try:
                from scene_packages import export_scene
                scene = urllib.parse.parse_qs(parsed.query).get('scene', [''])[0]
                config_dir = os.path.dirname(get_active_config_path())
                data = export_scene(copy.deepcopy(DeskPalHTTPHandler.app_ref.cfg), scene, os.path.join(config_dir, '..', 'assets'))
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Disposition', 'attachment; filename="deskpal-scene.zip"')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as error:
                self.send_error(400, str(error))
            return

        if path == '/api/backups/download':
            try:
                from backup_packages import export_backup
                config_dir = os.path.dirname(get_active_config_path())
                assets = os.path.join(config_dir, '..', 'assets')
                data = export_backup(copy.deepcopy(DeskPalHTTPHandler.app_ref.cfg), assets, config_dir)
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Disposition', 'attachment; filename="deskpal-backup.zip"')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as error:
                self.send_error(400, str(error))
            return

        if path == '/api/backups/recovery':
            name = urllib.parse.parse_qs(parsed.query).get('name', [''])[0]
            if not (name.startswith('before-restore-') and name.endswith('.zip') and name[15:-4].isdigit()):
                self.send_error(400, 'Invalid recovery backup name')
                return
            target = os.path.join(os.path.dirname(get_active_config_path()), 'backups', name)
            try:
                with open(target, 'rb') as source: data = source.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Disposition', 'attachment; filename="' + name + '"')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except OSError:
                self.send_error(404, 'Recovery backup not found')
            return

        if path in ["/", "/index.html", "/studio"]:
            studio_paths = [
                os.path.join(os.path.dirname(__file__), "web_studio.html"),
                os.path.join(os.path.dirname(__file__), "..", "src", "web_studio.html"),
                pi_path('web_studio.html'),
                "src/web_studio.html"
            ]
            content = None
            for sp in studio_paths:
                if os.path.exists(sp):
                    try:
                        with open(sp, "rb") as f:
                            content = f.read()
                        break
                    except Exception:
                        pass
            if content:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            else:
                self.send_error(404, "web_studio.html not found")
                return

        elif path == "/companion_studio.js":
            js_paths = [
                os.path.join(os.path.dirname(__file__), "companion_studio.js"),
                os.path.join(os.path.dirname(__file__), "..", "src", "companion_studio.js"),
                pi_path('companion_studio.js'),
                "src/companion_studio.js"
            ]
            content = None
            for jp in js_paths:
                if os.path.exists(jp):
                    try:
                        with open(jp, "rb") as f:
                            content = f.read()
                        break
                    except Exception:
                        pass
            if content:
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            else:
                self.send_error(404, "companion_studio.js not found")
                return

        elif path == "/theme_studio.js":
            js_paths = [
                os.path.join(os.path.dirname(__file__), "theme_studio.js"),
                os.path.join(os.path.dirname(__file__), "..", "src", "theme_studio.js"),
                pi_path('theme_studio.js'),
                "src/theme_studio.js"
            ]
            content = None
            for jp in js_paths:
                if os.path.exists(jp):
                    try:
                        with open(jp, "rb") as f:
                            content = f.read()
                        break
                    except Exception:
                        pass
            if content:
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            else:
                self.send_error(404, "theme_studio.js not found")
                return

        elif path == "/api/activity_history":
            from activity_history import recent
            app = DeskPalHTTPHandler.app_ref
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            include_receipts = query.get('heartbeat_receipts', ['1'])[0] != '0'
            payload = json.dumps(recent(getattr(app, 'activity_history_path', None), include_heartbeat_receipts=include_receipts), ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Disposition', 'attachment; filename="deskpal-activity-history.json"')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        elif path in ('/hardware', '/ai', '/display', '/remote-display'):
            if path in ('/display', '/remote-display'):
                filename = os.path.join(os.path.dirname(__file__), 'remote_display.html')
            else:
                filename = os.path.join(os.path.dirname(__file__), 'hardware_studio.html' if path == '/hardware' else 'ai_studio.html')
            with open(filename, 'rb') as source:
                payload = source.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        elif path == '/api/ai/speech':
            from speech_output import output_for
            app=DeskPalHTTPHandler.app_ref
            spk=output_for(app)
            snapshot=spk.snapshot()
            snapshot['animation_active']=bool(getattr(app,'speech_reaction',None))
            payload=json.dumps(snapshot).encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload);return

        elif path == '/api/ai/speech/history':
            from speech_output import output_for
            app=DeskPalHTTPHandler.app_ref
            history=output_for(app).get_history()
            payload=json.dumps({'history': history}).encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload);return

        elif path == '/api/ai/speech/audio':
            from pathlib import Path
            audio_path = Path.home() / '.cache' / 'deskpal' / 'last_speech.wav'
            if audio_path.exists():
                try:
                    data = audio_path.read_bytes()
                    self.send_response(200)
                    self.send_header('Content-Type', 'audio/wav')
                    self.send_header('Content-Length', str(len(data)))
                    self.send_header('Cache-Control', 'no-cache')
                    self.end_headers()
                    self.wfile.write(data)
                    return
                except Exception:
                    pass
            self.send_response(404)
            self.end_headers()
            return

        elif path == '/api/ai/voices':
            from piper_voices import library_for
            payload=json.dumps(library_for(DeskPalHTTPHandler.app_ref).snapshot()).encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload);return

        elif path == '/api/ai/settings':
            from ai_connections import read
            try:
                payload = json.dumps({'settings':read(os.path.join(os.path.dirname(get_active_config_path()),'ai_settings.json'))}).encode('utf-8')
                code = 200
            except (OSError,ValueError) as error:
                payload = json.dumps({'error':str(error)}).encode('utf-8'); code = 400
            self.send_response(code)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(payload)))
            self.end_headers();self.wfile.write(payload);return

        elif path == '/api/ai/stt/status':
            from voice_sentry import sentry_for
            app = DeskPalHTTPHandler.app_ref
            payload = json.dumps(sentry_for(app).snapshot()).encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload);return

        elif path in ('/api/hardware/radar-capture/download', '/api/hardware/imu-capture/download'):
            from optional_hardware import monitor_for
            app = DeskPalHTTPHandler.app_ref
            monitor = monitor_for(app, os.path.join(os.path.dirname(get_active_config_path()), 'hardware_settings.json'))
            try:
                payload = monitor.imu_capture_report() if '/imu-capture/' in path else monitor.radar_capture_report()
            except OSError:
                self.send_error(404, 'No saved capture yet')
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            filename = 'imu_capture_latest.json' if '/imu-capture/' in path else 'radar_capture_latest.json'
            self.send_header('Content-Disposition', 'attachment; filename="'+filename+'"')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        elif path == '/api/hardware/buttons':
            payload = json.dumps(DeskPalHTTPHandler.app_ref.button_controller.snapshot()).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(payload)
            return

        elif path == '/api/hardware':
            from optional_hardware import monitor_for
            app = DeskPalHTTPHandler.app_ref
            monitor = monitor_for(app, os.path.join(os.path.dirname(get_active_config_path()), 'hardware_settings.json'))
            snapshot = monitor.snapshot()
            snapshot['sleep_policy'] = dict(getattr(app, 'sleep_policy_status', {}))
            payload = json.dumps(snapshot).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        elif path == "/api/lighting":
            app = DeskPalHTTPHandler.app_ref
            payload = json.dumps(lighting_details(app.cfg.get('lighting', {}))).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        elif path == "/api/scenes/status":
            app = DeskPalHTTPHandler.app_ref
            payload = json.dumps({'scene': scene_id(app.cfg), 'travelling': bool(getattr(app, 'scene_journey', None) or getattr(app, 'journey_arriving', False) or getattr(app, 'pending_scene_destination', None)), 'error': getattr(app, 'travel_error', None)}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        elif path == "/api/themes":
            from theme_manager import list_themes
            app = DeskPalHTTPHandler.app_ref
            active_tid = (app.cfg.get('theme_profile') or app.cfg.get('theme', 'cozy_study')) if app else 'cozy_study'
            payload = json.dumps({
                'themes': list_themes(active_theme_id=active_tid),
                'active_theme': active_tid
            }, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        elif path == "/api/themes/current":
            from theme_manager import get_theme
            app = DeskPalHTTPHandler.app_ref
            active_tid = app.cfg.get('theme', 'cozy_study') if app else 'cozy_study'
            try:
                theme = get_theme(active_tid)
            except Exception:
                theme = {'id': active_tid, 'palette': app.cfg.get('palette', {})} if app else {}
            payload = json.dumps(theme, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        elif path == "/api/themes/export":
            from theme_manager import export_theme_zip
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            tid = query.get('theme', ['cozy_study'])[0]
            try:
                data = export_theme_zip(tid)
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Disposition', f'attachment; filename="deskpal_theme_{tid}.zip"')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_error(400, f"Theme export error: {e}")
            return

        elif path == "/api/integrations/mapping_status":
            payload = json.dumps(DeskPalHTTPHandler.app_ref.integration_mapping_status()).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        elif path == "/api/v1/status":
            app = DeskPalHTTPHandler.app_ref
            queue = getattr(app, 'activity_queue', None)
            from scene_world import scene_id
            status_data = {
                "status": "ok",
                "character": app.cfg.get("active_character", "adventurer"),
                "scene": scene_id(app.cfg),
                "scenes_available": list(app.cfg.get("scenes", {}).keys()),
                "sleeping": getattr(app, "is_sleeping", False),
                "current_animation": getattr(app, "current_anim", "idle"),
                "target_animation": getattr(app, "target_animation", "idle"),
                "radar_present": getattr(app, "radar_nearby_present", False),
                "attention_waiting": bool(queue and queue.active and queue.active[0].get("_attention_waiting") and not queue.active[0].get("_attention_acknowledged")),
                "modal_active": bool(getattr(app, "active_popup_modal", None)),
                "queue_depth": len(queue.items) if queue else 0,
                "system_resources": get_system_stats()
            }
            payload = json.dumps(status_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        elif path == "/api/v1/world":
            app = DeskPalHTTPHandler.app_ref
            from scene_world import scene_id
            curr_sc = scene_id(app.cfg)
            scenes_info = {}
            for s_name, s_data in app.cfg.get("scenes", {}).items():
                scenes_info[s_name] = {
                    "enabled": s_data.get("enabled", True),
                    "label": s_data.get("name") or s_name.replace("_", " ").title(),
                    "spots": [
                        {
                            "id": sp.get("id"),
                            "label": sp.get("label") or sp.get("id", "").replace("_", " ").title(),
                            "animation": sp.get("animation", "inspect"),
                            "facing": sp.get("facing", "left"),
                            "x": sp.get("x"),
                            "y": sp.get("y")
                        }
                        for sp in s_data.get("interaction_spots", [])
                    ]
                }
            world_data = {
                "status": "ok",
                "current_scene": curr_sc,
                "character": app.cfg.get("active_character", "adventurer_v1"),
                "position": {"x": int(app.char_x), "y": int(app.char_y)},
                "facing": "left" if getattr(app, "facing_left", False) else "right",
                "current_animation": getattr(app, "current_anim", "idle"),
                "scenes": scenes_info,
                "available_animations": sorted(list(getattr(app, "character_sequences", {}).keys())),
                "sleeping": getattr(app, "is_sleeping", False),
                "radar_present": getattr(app, "radar_nearby_present", False)
            }
            payload = json.dumps(world_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        elif path in ("/api/v1/capabilities", "/api/v1/agent/capabilities"):
            app = DeskPalHTTPHandler.app_ref
            from scene_world import scene_id
            curr_sc = scene_id(app.cfg)

            # 1. Dynamic Scenes Introspection
            scenes_catalog = {}
            for s_name, s_data in app.cfg.get("scenes", {}).items():
                is_enabled = s_data.get("enabled", True)
                spots = []
                for sp in s_data.get("interaction_spots", []):
                    sp_id = sp.get("id")
                    if not sp_id:
                        continue
                    spots.append({
                        "id": sp_id,
                        "label": sp.get("label") or sp_id.replace("_", " ").title(),
                        "x": sp.get("x"),
                        "y": sp.get("y"),
                        "facing": sp.get("facing", "left"),
                        "animation": sp.get("animation", "inspect"),
                        "description": sp.get("description", "")
                    })
                props = []
                for pr in s_data.get("interactive_props", []):
                    pr_id = pr.get("id")
                    if not pr_id:
                        continue
                    props.append({
                        "id": pr_id,
                        "label": pr.get("label") or pr_id.replace("_", " ").title(),
                        "prop_type": pr.get("prop_type", "prop"),
                        "x": pr.get("x"),
                        "y": pr.get("y"),
                        "interactive": bool(pr.get("tap_animation") or pr.get("animation_id") or pr.get("actions")),
                        "tap_animation": pr.get("tap_animation")
                    })
                portals = []
                for pt in s_data.get("portals", []):
                    portals.append({
                        "id": pt.get("id"),
                        "name": pt.get("name") or pt.get("id", "").replace("_", " ").title(),
                        "destination": pt.get("destination", ""),
                        "x": pt.get("x"),
                        "y": pt.get("y")
                    })
                walk_trap = s_data.get("walkable_trapezoid", {})
                walkable_area = {
                    "y_min": walk_trap.get("y_min"),
                    "y_max": walk_trap.get("y_max"),
                    "front_x_range": [walk_trap.get("front_x_min"), walk_trap.get("front_x_max")],
                    "back_x_range": [walk_trap.get("back_x_min"), walk_trap.get("back_x_max")]
                } if walk_trap else None

                scenes_catalog[s_name] = {
                    "id": s_name,
                    "label": s_data.get("name") or s_name.replace("_", " ").title(),
                    "enabled": is_enabled,
                    "is_current": (s_name == curr_sc),
                    "spots": spots,
                    "props": props,
                    "portals": portals,
                    "walkable_area": walkable_area
                }

            # 2. Dynamic Animations & Poses Catalog
            active_char = app.cfg.get("active_character", "adventurer_v1")
            raw_seqs = getattr(app, "character_sequences", {})
            custom_poses = app.cfg.get("custom_poses", {})
            animations_catalog = {}

            for role, seq_info in raw_seqs.items():
                if not isinstance(seq_info, dict):
                    continue
                if role.startswith("walk") or role in ("run", "wander"):
                    cat = "locomotion"
                elif role.startswith("idle") or role.startswith("balance"):
                    cat = "idle"
                elif role in ("sitting_rest", "sleeping", "seated_back", "deck_chair_rest", "sit_down", "stand_from_sit", "lie_down", "stand_from_sleep"):
                    cat = "rest"
                else:
                    cat = "interaction"

                allowed_sc = seq_info.get("allowed_scenes", [])
                animations_catalog[role] = {
                    "role": role,
                    "category": cat,
                    "fps": seq_info.get("fps", 8),
                    "playback_mode": seq_info.get("playback_mode", "loop"),
                    "repeat_count": seq_info.get("repeat_count", 1),
                    "allowed_scenes": allowed_sc if allowed_sc else ["all"],
                    "idle_eligible": bool(seq_info.get("idle_eligible", False)),
                    "standby_eligible": bool(seq_info.get("standby_eligible", False)),
                    "supports_thought_bubble": True
                }

            for pose_id, pose_info in custom_poses.items():
                if pose_id not in animations_catalog:
                    animations_catalog[pose_id] = {
                        "role": pose_id,
                        "category": "custom_pose",
                        "fps": 1,
                        "playback_mode": "once",
                        "repeat_count": 1,
                        "allowed_scenes": ["all"],
                        "idle_eligible": False,
                        "standby_eligible": False,
                        "supports_thought_bubble": True,
                        "label": pose_info.get("label", pose_id)
                    }

            all_animations_flat = sorted(list(animations_catalog.keys()))

            # 3. Dynamic Hardware, Voices, and Sensor State
            radar_cfg, imu_cfg = {}, {}
            try:
                from optional_hardware import monitor_for
                h_path = os.path.join(os.path.dirname(get_active_config_path()), "hardware_settings.json")
                m = monitor_for(app, h_path)
                with m.lock:
                    radar_cfg = dict(m.config.get("radar", {}))
                    imu_cfg = dict(m.config.get("imu", {}))
            except Exception:
                pass

            ai_cfg = {}
            try:
                ai_path = os.path.join(os.path.dirname(get_active_config_path()), "ai_settings.json")
                if os.path.exists(ai_path):
                    with open(ai_path, "r", encoding="utf-8") as f:
                        ai_cfg = json.load(f)
            except Exception:
                pass
            tts_cfg = ai_cfg.get("tts", {})
            active_voice = tts_cfg.get("voice", "wheatley1")

            voices_list = []
            try:
                from piper_voices import library_for
                v_snap = library_for(app).snapshot()
                voices_list = [v.get("id") for v in v_snap.get("voices", []) if v.get("id")]
            except Exception:
                pass
            if not voices_list and active_voice:
                voices_list = [active_voice]

            # 4. Dynamic Services Discovery
            services_catalog = []
            sup = getattr(app, "service_supervisor", None)
            if sup:
                try:
                    services_catalog = sup.discover_services()
                except Exception:
                    pass
            if not services_catalog:
                s_dir = pi_path("services") if os.path.isdir(pi_path("services")) else os.path.join(os.path.dirname(__file__), "..", "services")
                if os.path.isdir(s_dir):
                    services_catalog = [{"id": d, "name": d.replace("_", " ").title()} for d in os.listdir(s_dir) if os.path.isdir(os.path.join(s_dir, d)) and not d.startswith(".")]

            # 5. Functions & Actions Catalog Schema
            functions_catalog = {
                "puppeteer": {
                    "description": "Direct character movement, scene travel, spot interaction, gestures, and thought bubbles.",
                    "method": "POST",
                    "path": "/api/v1/action",
                    "parameters": {
                        "scene": {"type": "string", "required": False, "description": f"Target scene name ({', '.join(scenes_catalog.keys())})"},
                        "spot_id": {"type": "string", "required": False, "description": "Named interaction spot to walk to"},
                        "x": {"type": "number", "required": False, "description": "Target screen X coordinate (0-1280)"},
                        "y": {"type": "number", "required": False, "description": "Target screen Y coordinate (0-720)"},
                        "animation": {"type": "string", "required": False, "description": "Animation sequence to trigger upon arrival (e.g. typing, inspect, wave_arms, sitting_rest)"},
                        "facing": {"type": "string", "enum": ["left", "right"], "required": False, "description": "Direction sprite should face"},
                        "speech": {"type": "string", "required": False, "description": "Comic thought bubble text to display above sprite or speak aloud"},
                        "display_mode": {"type": "string", "enum": ["thought_bubble", "none"], "default": "thought_bubble", "description": "Display format for speech"},
                        "duration_seconds": {"type": "number", "default": 6.0, "description": "Duration in seconds to hold the action"},
                        "priority": {"type": "boolean", "default": True, "description": "If true, preempts ambient idle wandering immediately"}
                    }
                },
                "notify": {
                    "description": "Display a full-screen interactive card modal on the 1280x720 touchscreen.",
                    "method": "POST",
                    "path": "/api/v1/notify",
                    "parameters": {
                        "title": {"type": "string", "required": True, "description": "Card header / title (e.g. 'Build Passed', 'Review Ready')"},
                        "summary": {"type": "string", "required": True, "description": "Card body message or markdown description"},
                        "layout": {"type": "string", "enum": ["classic", "dashboard", "wellness"], "default": "classic", "description": "Visual layout template"},
                        "attention": {"type": "boolean", "default": True, "description": "If true, sprite waves arms and card requires touch tap to dismiss"},
                        "speech": {"type": "string", "required": False, "description": "Voice announcement read aloud via Piper TTS"},
                        "slider": {"type": "object", "required": False, "description": "Optional touch slider action (e.g. {'label': 'Slide to Confirm', 'action': 'task_approved'})"},
                        "priority": {"type": "boolean", "default": True, "description": "Display immediately"}
                    }
                },
                "speak": {
                    "description": "Speak text aloud on the room speaker using on-device Piper Neural TTS.",
                    "method": "POST",
                    "path": "/api/v1/say",
                    "parameters": {
                        "text": {"type": "string", "required": True, "description": "Sentence or announcement to speak (1-500 characters)"},
                        "voice": {"type": "string", "required": False, "description": f"Installed voice ID (e.g. {', '.join(voices_list[:5])})"}
                    }
                },
                "get_presence": {
                    "description": "Query 24GHz mmWave radar sensor for real-time human presence sitting at the desk.",
                    "method": "GET",
                    "path": "/api/v1/presence",
                    "returns": {
                        "present": "boolean - whether human is seated in front of Desk-Pal",
                        "targets": "integer - count of detected radar targets",
                        "presence_range_m": "float - radar configured tracking range in meters",
                        "details": "list of objects with distance_mm, speed_cm_s, x_mm, y_mm, angle_deg, tracking_status"
                    }
                },
                "get_world": {
                    "description": "Query live spatial state of the virtual room: current scene, character position (x, y), animation, and radar presence.",
                    "method": "GET",
                    "path": "/api/v1/world"
                },
                "get_capabilities": {
                    "description": "Discover device profile, hardware, dynamic scenes, animations catalog, services, and etiquette guidelines.",
                    "method": "GET",
                    "path": "/api/v1/agent/capabilities"
                },
                "travel_scene": {
                    "description": "Trigger an animated walking travel journey between rooms (e.g. from study to beach).",
                    "method": "POST",
                    "path": "/api/scenes/travel",
                    "parameters": {
                        "scene": {"type": "string", "required": True, "description": "Target scene ID"}
                    }
                },
                "control_display": {
                    "description": "Put the physical touchscreen display into standby or wake it up.",
                    "method": "POST",
                    "path": "/api/v1/display",
                    "parameters": {
                        "action": {"type": "string", "enum": ["sleep", "wake"], "required": True, "description": "'sleep' to enter standby, 'wake' to turn screen back on"}
                    }
                },
                "control_service": {
                    "description": "Start, stop, or restart an installed companion background service.",
                    "method": "POST",
                    "path": "/api/services/action",
                    "parameters": {
                        "id": {"type": "string", "required": True, "description": "Service ID"},
                        "action": {"type": "string", "enum": ["start", "stop", "restart"], "required": True}
                    }
                }
            }

            caps = {
                "name": "Desk-Pal",
                "version": "1.1.0",
                "description": "Embodied physical desk companion running on a 1280x720 touchscreen Raspberry Pi appliance.",
                "device_roles": [
                    "Physical second-screen output for notifications and interactive decision cards",
                    "Voice annunciator (Piper TTS) for concise room updates without hijacking PC audio",
                    "Peripheral presence notifier (character waves arms in the room when human input is required)",
                    "Embodied ambient worker (character types at PC desk, inspects bookshelf, or relaxes while tasks run)"
                ],
                "hardware": {
                    "display": {
                        "resolution": f"{app.width}x{app.height}",
                        "fps": 60,
                        "touchscreen": True,
                        "sleeping": getattr(app, "is_sleeping", False)
                    },
                    "speaker": {
                        "available": True,
                        "tts_enabled": bool(tts_cfg.get("enabled", True)),
                        "active_voice": active_voice,
                        "installed_voices": voices_list
                    },
                    "radar": {
                        "enabled": bool(radar_cfg.get("enabled")),
                        "present": getattr(app, "radar_nearby_present", False),
                        "range_m": radar_cfg.get("presence_range_m", 2.0)
                    },
                    "imu": {
                        "enabled": bool(imu_cfg.get("enabled"))
                    }
                },
                "world": {
                    "current_scene": curr_sc,
                    "active_character": active_char,
                    "character_position": {
                        "x": int(getattr(app, "char_x", 640)),
                        "y": int(getattr(app, "char_y", 500)),
                        "facing": "left" if getattr(app, "facing_left", False) else "right",
                        "current_animation": getattr(app, "current_anim", "idle")
                    },
                    "scenes": scenes_catalog,
                    "available_scenes": [s for s, d in scenes_catalog.items() if d.get("enabled", True)],
                    "all_scenes": list(scenes_catalog.keys())
                },
                "animations": {
                    "available_animations": all_animations_flat,
                    "catalog": animations_catalog
                },
                "functions": functions_catalog,
                "services": services_catalog,
                "modal_layouts": {
                    "wellness": {
                        "description": "Dual-panel health card (hydration progress + animated stretch sprite) with eye-rest rules and touch slider rail",
                        "supported_fields": ["title", "summary", "slider", "wellness"]
                    },
                    "dashboard": {
                        "description": "High-contrast telemetry card with hero metric value, status badge, and up to 4 data tiles",
                        "supported_fields": ["title", "summary", "badge", "ticker", "color", "slider"]
                    },
                    "classic": {
                        "description": "Multiline formatted text card with pagination buttons and touch slider rail",
                        "supported_fields": ["title", "summary", "slider", "attention"]
                    },
                    "thought_bubble": {
                        "description": "In-world comic speech bubble hovering above the character's head inside the room",
                        "supported_fields": ["speech", "duration_seconds"]
                    }
                },
                "etiquette_for_agents": [
                    "Check /api/v1/presence before speaking loudly if human might not be at desk.",
                    "Use thought bubbles (speech in puppeteer) or quiet spot animations during routine background work.",
                    "Use attention=True and full-screen modals only when waiting for human input or on critical task completion.",
                    "Pick appropriate interaction spots to match your task (e.g. computer_desk for coding, bookshelf for research)."
                ]
            }
            payload = json.dumps(caps, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        elif path == "/api/v1/presence":
            app = DeskPalHTTPHandler.app_ref
            radar_cfg = {}
            monitor = getattr(app, 'hardware_monitor', None)
            if monitor:
                with monitor.lock:
                    radar_cfg = dict(monitor.config.get("radar", {}))
            else:
                try:
                    from optional_hardware import monitor_for
                    h_path = os.path.join(os.path.dirname(get_active_config_path()), "hardware_settings.json")
                    m = monitor_for(app, h_path)
                    with m.lock:
                        radar_cfg = dict(m.config.get("radar", {}))
                except Exception:
                    pass
            nearby = getattr(app, "last_radar_nearby", {}) or {}
            presence_data = {
                "radar_enabled": bool(radar_cfg.get("enabled")),
                "present": getattr(app, "radar_nearby_present", False),
                "targets": len(nearby.get("targets", [])),
                "presence_range_m": radar_cfg.get("presence_range_m", 2.0),
                "details": nearby.get("targets", [])
            }
            payload = json.dumps(presence_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        elif path == "/api/v1/sensors":
            app = DeskPalHTTPHandler.app_ref
            monitor = getattr(app, 'hardware_monitor', None)
            if not monitor:
                try:
                    from optional_hardware import monitor_for
                    h_path = os.path.join(os.path.dirname(get_active_config_path()), "hardware_settings.json")
                    monitor = monitor_for(app, h_path)
                except Exception:
                    pass
            light_reading = {}
            light_cfg = {}
            radar_cfg = {}
            imu_cfg = {}
            imu_state = {}
            if monitor:
                with monitor.lock:
                    light_reading = dict(monitor.i2c.get('light', {}))
                    light_cfg = dict(monitor.config.get('light', {}))
                    radar_cfg = dict(monitor.config.get('radar', {}))
                    imu_cfg = dict(monitor.config.get('imu', {}))
                    imu_state = dict(monitor.i2c.get('imu', {}))
            nearby = getattr(app, "last_radar_nearby", {}) or {}
            now = time.monotonic()
            power = getattr(app, 'display_power', None)
            sleep_status = getattr(app, 'sleep_policy_status', {}) or {}
            sensors_data = {
                "status": "ok",
                "light": {
                    "enabled": bool(light_cfg.get("enabled")),
                    "state": light_reading.get("state", "unavailable"),
                    "lux": light_reading.get("lux"),
                    "sleep_below_lux": light_cfg.get("sleep_below_lux", 0.1),
                    "wake_margin_lux": light_cfg.get("wake_margin_lux", 0.2),
                    "sample_age_seconds": round(now - light_reading.get("at", 0), 1) if light_reading.get("at") else None
                },
                "radar": {
                    "enabled": bool(radar_cfg.get("enabled")),
                    "present": getattr(app, "radar_nearby_present", False),
                    "targets": len(nearby.get("targets", [])),
                    "presence_range_m": radar_cfg.get("presence_range_m", 2.0),
                    "details": nearby.get("targets", [])
                },
                "display": {
                    "is_sleeping": getattr(app, "is_sleeping", False),
                    "panel_off": bool(getattr(power, "is_off", False)),
                    "error": str(getattr(power, "error", None)) if getattr(power, "error", None) else None
                },
                "sleep_policy": {
                    "bedtime": light_cfg.get("bedtime", "22:00"),
                    "bedtime_active": sleep_status.get("bedtime_active", False),
                    "evening_keeps_awake": sleep_status.get("evening_keeps_awake", False),
                    "radar_keeps_awake": sleep_status.get("radar_keeps_awake", False),
                    "action": sleep_status.get("action"),
                    "pending": sleep_status.get("pending"),
                    "manual_wake_seconds_remaining": sleep_status.get("manual_wake_seconds_remaining", 0)
                },
                "imu": {
                    "enabled": bool(imu_cfg.get("enabled")),
                    "state": imu_state.get("state", "unavailable"),
                    "error": imu_state.get("error")
                }
            }
            payload = json.dumps(sensors_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        elif path == "/api/config":
            if DeskPalHTTPHandler.app_ref:
                cfg_data = json.dumps(DeskPalHTTPHandler.app_ref.cfg).encode("utf-8")
            else:
                cfg_data = json.dumps(load_config()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(cfg_data)))
            self.end_headers()
            self.wfile.write(cfg_data)
            return

        elif path == "/api/telemetry":
            if DeskPalHTTPHandler.app_ref:
                tele_data = json.dumps(DeskPalHTTPHandler.app_ref.app_telemetry).encode("utf-8")
            else:
                tele_data = b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(tele_data)))
            self.end_headers()
            self.wfile.write(tele_data)
            return

        elif path == "/api/activity_queue":
            queue = getattr(DeskPalHTTPHandler.app_ref, 'activity_queue', None)
            data = json.dumps(queue.snapshot() if queue else {}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        elif path == "/api/system_stats":
            data = json.dumps(get_system_stats()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        elif path == "/api/services":
            app = DeskPalHTTPHandler.app_ref
            sup = getattr(app, 'service_supervisor', None)
            svcs = sup.discover_services() if sup else []
            data = json.dumps({"services": svcs}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        elif path == "/api/services/logs":
            app = DeskPalHTTPHandler.app_ref
            sup = getattr(app, 'service_supervisor', None)
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            sid = query.get("id", [""])[0]
            lines = int(query.get("lines", [100])[0])
            logs = sup.get_logs(sid, max_lines=lines) if sup else []
            data = json.dumps({"id": sid, "logs": logs}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        elif path == "/api/services/code":
            app = DeskPalHTTPHandler.app_ref
            sup = getattr(app, 'service_supervisor', None)
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            sid = query.get("id", [""])[0]
            result = sup.get_service_code(sid) if sup else {"success": False, "error": "Supervisor not running"}
            data = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        elif path.startswith("/assets/"):
            rel_path = path[len("/assets/"):]
            asset_roots = [
                os.path.join(os.path.dirname(__file__), "..", "assets"),
                pi_path('assets'),
                "assets"
            ]
            target_file = None
            for ar in asset_roots:
                candidate = os.path.join(ar, rel_path.replace("/", os.sep))
                if os.path.exists(candidate) and os.path.isfile(candidate):
                    target_file = candidate
                    break
            if target_file:
                ctype = "application/octet-stream"
                if target_file.endswith(".jpg") or target_file.endswith(".jpeg"):
                    ctype = "image/jpeg"
                elif target_file.endswith(".png"):
                    ctype = "image/png"
                elif target_file.endswith(".webp"):
                    ctype = "image/webp"
                try:
                    with open(target_file, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                except Exception as e:
                    self.send_error(500, f"Error reading asset: {e}")
                    return
            self.send_error(404, "Asset not found")
            return

        elif path == "/api/modular_assets":
            asset_roots = [
                os.path.join(os.path.dirname(__file__), "..", "assets"),
                pi_path('assets'),
                "assets"
            ]
            mod_root = None
            for ar in asset_roots:
                candidate = os.path.join(ar, "characters", "adventurer", "modular")
                if os.path.exists(candidate):
                    mod_root = candidate
                    break
            res = {"side": {}, "front": {}, "back": {}}
            if mod_root:
                for v in ["side", "front", "back"]:
                    v_dir = os.path.join(mod_root, v)
                    if os.path.exists(v_dir):
                        for f in os.listdir(v_dir):
                            if f.endswith(".png"):
                                name = f[:-4]
                                res[v][name] = f"/assets/characters/adventurer/modular/{v}/{f}"
            data = json.dumps(res).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        elif path == "/api/animation_frames":
            # Scan adventurer directory for all sprite PNGs for Animation Grid
            asset_roots = [
                os.path.join(os.path.dirname(__file__), "..", "assets"),
                pi_path('assets'),
                "assets"
            ]
            adv_root = None
            for ar in asset_roots:
                candidate = os.path.join(ar, "characters", "adventurer")
                if os.path.exists(candidate):
                    adv_root = candidate
                    break
            frames = {"walk": [], "poses": [], "other": []}
            if adv_root:
                # Top-level PNGs
                for f in sorted(os.listdir(adv_root)):
                    if f.endswith(".png"):
                        name = f[:-4]
                        url = f"/assets/characters/adventurer/{f}"
                        if name.startswith("walk_"):
                            frames["walk"].append({"name": name, "url": url, "source": "root"})
                        else:
                            frames["other"].append({"name": name, "url": url, "source": "root"})
                # walk/ subdir
                walk_dir = os.path.join(adv_root, "walk")
                if os.path.exists(walk_dir):
                    for f in sorted(os.listdir(walk_dir)):
                        if f.endswith(".png"):
                            name = f[:-4]
                            url = f"/assets/characters/adventurer/walk/{f}"
                            frames["walk"].append({"name": name, "url": url, "source": "walk_dir"})
                # walk8/ subdir
                walk8_dir = os.path.join(adv_root, "walk8")
                if os.path.exists(walk8_dir):
                    for f in sorted(os.listdir(walk8_dir)):
                        if f.endswith(".png"):
                            name = f[:-4]
                            url = f"/assets/characters/adventurer/walk8/{f}"
                            frames["walk"].append({"name": name, "url": url, "source": "walk8_dir"})
                # poses/ subdir
                poses_dir = os.path.join(adv_root, "poses")
                if os.path.exists(poses_dir):
                    for f in sorted(os.listdir(poses_dir)):
                        if f.endswith(".png"):
                            name = f[:-4]
                            url = f"/assets/characters/adventurer/poses/{f}"
                            frames["poses"].append({"name": name, "url": url, "source": "poses_dir"})
            if adv_root:
                seen = {f['url'] for group in frames.values() for f in group}
                for directory, folders, files in os.walk(adv_root):
                    folders[:] = [name for name in folders if name not in ('raw', 'modular')]
                    for filename in sorted(files):
                        if not filename.lower().endswith('.png'):
                            continue
                        relative = os.path.relpath(os.path.join(directory, filename), adv_root).replace(os.sep, '/')
                        url = '/assets/characters/adventurer/' + relative
                        if url not in seen:
                            frames['other'].append({'name': filename[:-4], 'url': url, 'source': 'character_folder'})
                            seen.add(url)
            data = json.dumps(frames).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        elif path == "/api/sprite_tags":
            # Per-image character variant tags
            tag_paths = [
                os.path.join(os.path.dirname(__file__), "..", "config", "sprite_tags.json"),
                pi_path('config/sprite_tags.json'),
                "config/sprite_tags.json"
            ]
            content = b"{}"
            for tp in tag_paths:
                if os.path.exists(tp):
                    try:
                        with open(tp, "r", encoding="utf-8") as f:
                            content = f.read().encode("utf-8")
                        break
                    except Exception:
                        pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        elif path == "/api/puppet_rig":
            rig_paths = [
                os.path.join(os.path.dirname(__file__), "..", "config", "puppet_rig.json"),
                pi_path('config/puppet_rig.json'),
                "config/puppet_rig.json"
            ]
            content = b"{}"
            for rp in rig_paths:
                if os.path.exists(rp):
                    with open(rp, "rb") as f:
                        content = f.read()
                    break
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        if path == '/api/ai/voices/upload':
            from piper_voices import library_for
            query=urllib.parse.parse_qs(parsed.query)
            try:
                result=library_for(DeskPalHTTPHandler.app_ref).upload(query.get('voice',[''])[0],query.get('kind',[''])[0],self.rfile,length)
                code=200
            except (OSError,ValueError,subprocess.SubprocessError) as error:
                result={'error':str(error)[:400]};code=400;self.close_connection=True
            payload=json.dumps(result).encode('utf-8')
            self.send_response(code);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload);return
        if path.startswith('/api/ai/') and not 0 <= length <= 8192:
            self.send_error(413,'AI settings request exceeds its limit');return
        if path.startswith('/api/hardware') and not 0 < length <= 4096:
            self.send_error(413, 'Hardware request exceeds its limit')
            return
        if path == '/api/preview/input' and not 0 < length <= 4096:
            self.send_error(413, 'Preview input exceeds its limit')
            return
        if path.startswith('/api/integration-packages/') and not 0 < length <= 1024 * 1024:
            self.send_error(413, 'Integration definitions must be smaller than 1 MB')
            return
        if path.startswith(('/api/backups/', '/api/scene-packages/', '/api/character-packages/')) and not 0 < length <= 512 * 1024 * 1024:
            self.send_error(413, 'Backup upload exceeds the 512 MB limit')
            return
        if path in ('/api/props/frame', '/api/scenes/background', '/api/characters/reference', '/api/characters/frame') and length > 17_100_000:
            self.send_error(413, 'Background upload is too large')
            return
        body = self.rfile.read(length)

        if path == '/api/ai/voices/download':
            from piper_voices import library_for
            try:
                request=json.loads(body)
                if not isinstance(request,dict):raise ValueError('Voice request must be an object')
                result=library_for(DeskPalHTTPHandler.app_ref).download(request.get('voice'))
                code=202
            except (OSError,ValueError) as error:result={'error':str(error)};code=400
            payload=json.dumps(result).encode('utf-8')
            self.send_response(code);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload);return

        if path in ('/api/ai/speak','/api/ai/speech/stop','/api/ai/speech/replay'):
            from speech_output import output_for
            try:
                app=DeskPalHTTPHandler.app_ref;output=output_for(app)
                if path.endswith('/stop'):
                    output.stop()
                    res = output.snapshot()
                elif path.endswith('/replay'):
                    request = json.loads(body) if body else {}
                    item_id = request.get('id') if isinstance(request, dict) else None
                    ok, text = output.replay(item_id=item_id)
                    if not ok:
                        raise ValueError(text or "No speech available to replay")
                    res = {'status': 'replaying', 'text': text}
                else:
                    from optional_hardware import monitor_for
                    monitor=monitor_for(app,os.path.join(os.path.dirname(get_active_config_path()),'hardware_settings.json'))
                    with monitor.lock:speaker=dict(monitor.config['speaker'])
                    request=json.loads(body)
                    if not isinstance(request,dict):raise ValueError('Speech request must be an object')
                    output.speak(request.get('text'),os.path.join(os.path.dirname(get_active_config_path()),'ai_settings.json'),speaker,source='web_test')
                    res = output.snapshot()
                payload=json.dumps(res).encode('utf-8');code=200
            except (OSError,ValueError) as error:
                payload=json.dumps({'error':str(error)}).encode('utf-8');code=400
            self.send_response(code);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload);return

        if path in ('/api/ai/stt/listen', '/api/ai/stt/stop', '/api/ai/stt/test'):
            from voice_sentry import sentry_for
            try:
                app = DeskPalHTTPHandler.app_ref
                sentry = sentry_for(app)
                if path == '/api/ai/stt/listen':
                    ok = sentry.start_listening(app)
                    result = {'status': 'listening' if ok else 'failed'}
                    code = 200
                elif path == '/api/ai/stt/stop':
                    sentry.stop_listening_and_transcribe(app)
                    result = {'status': 'stopped'}
                    code = 200
                elif path == '/api/ai/stt/test':
                    result = sentry.test_record_and_transcribe(duration_s=5.0)
                    code = 200 if result.get('success') else 400
            except Exception as error:
                result = {'error': str(error)}; code = 400
            payload = json.dumps(result).encode('utf-8')
            self.send_response(code); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(payload))); self.end_headers(); self.wfile.write(payload); return

        if path == '/api/ai/settings':
            from ai_connections import save
            try:
                settings = save(os.path.join(os.path.dirname(get_active_config_path()),'ai_settings.json'),json.loads(body))
                if hasattr(DeskPalHTTPHandler.app_ref,'speech_output'):
                    DeskPalHTTPHandler.app_ref.speech_output.configure(settings['tts'])
                if hasattr(DeskPalHTTPHandler.app_ref,'voice_sentry'):
                    DeskPalHTTPHandler.app_ref.voice_sentry.configure(settings.get('stt', {}))
                payload=json.dumps({'settings':settings}).encode('utf-8');code=200
            except (OSError,ValueError) as error:
                payload=json.dumps({'error':str(error)}).encode('utf-8');code=400
            self.send_response(code);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload);return

        if path in ('/api/hardware/settings', '/api/hardware/test', '/api/hardware/calibration', '/api/hardware/radar-capture', '/api/hardware/buttons/test'):
            try:
                from optional_hardware import monitor_for
                app = DeskPalHTTPHandler.app_ref
                monitor = monitor_for(app, os.path.join(os.path.dirname(get_active_config_path()), 'hardware_settings.json'))
                data = json.loads(body)
                if path.endswith('/settings'):
                    previous_buttons = copy.deepcopy(monitor.config['buttons'])
                    monitor.configure(data)
                    if monitor.config['buttons'] != previous_buttons:app._gpio_reconfigure_pending = True
                    if 'microphone' in data and 'wake_peak_threshold' in monitor.config.get('microphone', {}):
                        thresh = int(monitor.config['microphone']['wake_peak_threshold'])
                        if hasattr(app, 'voice_sentry') and app.voice_sentry:
                            with app.voice_sentry.lock:
                                app.voice_sentry.config['wake_peak_threshold'] = thresh
                        ai_cfg_path = os.path.join(os.path.dirname(get_active_config_path()), 'ai_settings.json')
                        try:
                            if os.path.exists(ai_cfg_path):
                                with open(ai_cfg_path, 'r', encoding='utf-8') as f:
                                    ai_cfg = json.load(f)
                                ai_cfg.setdefault('stt', {})['wake_peak_threshold'] = thresh
                                with open(ai_cfg_path, 'w', encoding='utf-8') as f:
                                    json.dump(ai_cfg, f, indent=2)
                        except Exception:
                            pass
                elif path.endswith('/buttons/test'):
                    app.button_controller.test(data.get('enabled'))
                elif path.endswith('/calibration'):
                    monitor.capture_imu(data)
                elif path.endswith('/radar-capture'):
                    monitor.capture_radar(data)
                else:
                    monitor.test(data.get('device'), data.get('level', .25))
                self.send_response(204)
                self.end_headers()
            except Exception as error:
                self.send_error(400, str(error))
            return

        if path == '/api/preview/input':
            try:
                app = DeskPalHTTPHandler.app_ref
                bridge = getattr(app, 'preview_bridge', None)
                if not bridge:
                    raise ValueError('Preview input bridge is not active')
                bridge.enqueue(json.loads(body), app.width, app.height)
                self.send_response(204)
                self.end_headers()
            except Exception as error:
                self.send_error(400, str(error))
            return

        if path in ('/api/integration-packages/preview', '/api/integration-packages/import'):
            try:
                from integration_packages import preview_integration, import_integration
                app = DeskPalHTTPHandler.app_ref
                current = copy.deepcopy(app.cfg)
                query = urllib.parse.parse_qs(parsed.query)
                target = query.get('target', [None])[0]
                mappings = query.get('mappings', ['0'])[0] == '1'
                if path.endswith('/preview'):
                    result = preview_integration(body, current, target, mappings)
                else:
                    if self.headers.get('X-Deskpal-Restore') != 'confirmed':
                        raise ValueError('Review and confirm the integration import first')
                    config_dir = os.path.dirname(get_active_config_path())
                    result = import_integration(body, current, os.path.join(config_dir, '..', 'assets'), config_dir,
                        app.apply_remote_config, query.get('digest', [''])[0], query.get('state', [''])[0], target, mappings)
                data = json.dumps(result).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as error:
                self.send_error(400, str(error))
            return

        if path in ('/api/scene-packages/preview', '/api/scene-packages/import', '/api/character-packages/preview', '/api/character-packages/import'):
            try:
                from scene_packages import read_package, preview_scene, import_scene
                if path.startswith('/api/character-packages/'):
                    from character_packages import read_package, preview_character as preview_scene, import_character as import_scene
                import io
                app = DeskPalHTTPHandler.app_ref
                config_dir = os.path.dirname(get_active_config_path())
                assets = os.path.join(config_dir, '..', 'assets')
                current = copy.deepcopy(app.cfg)
                query = urllib.parse.parse_qs(parsed.query)
                target = query.get('target', [None])[0]
                _, files = read_package(body)
                for name, image_bytes in files.items():
                    if name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                        pygame.image.load(io.BytesIO(image_bytes))
                if path.endswith('/preview'):
                    result = preview_scene(body, current, assets, config_dir, target)
                else:
                    if self.headers.get('X-Deskpal-Restore') != 'confirmed':
                        raise ValueError('Review and confirm the scene import first')
                    result = import_scene(body, current, assets, config_dir, app.apply_remote_config,
                        query.get('digest', [''])[0], query.get('state', [''])[0], target)
                    app.backup_content_reload = True
                data = json.dumps(result).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as error:
                self.send_error(400, str(error))
            return

        if path in ('/api/backups/preview', '/api/backups/restore'):
            try:
                from backup_packages import preview_backup, restore_backup
                app = DeskPalHTTPHandler.app_ref
                config_dir = os.path.dirname(get_active_config_path())
                assets = os.path.join(config_dir, '..', 'assets')
                current = copy.deepcopy(app.cfg)
                from backup_packages import unpack
                import io
                _, _, backup_files = unpack(body)
                for name, image_bytes in backup_files.items():
                    if name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                        pygame.image.load(io.BytesIO(image_bytes))
                if path.endswith('/preview'):
                    result = preview_backup(body, current, assets, config_dir)
                else:
                    if self.headers.get('X-Deskpal-Restore') != 'confirmed':
                        raise ValueError('Review and explicitly confirm the restore first')
                    digest = urllib.parse.parse_qs(parsed.query).get('digest', [''])[0]
                    state = urllib.parse.parse_qs(parsed.query).get('state', [''])[0]
                    result = restore_backup(body, current, assets, config_dir, app.apply_remote_config, digest, state)
                    app.backup_content_reload = True
                data = json.dumps(result).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as error:
                self.send_error(400, str(error))
            return

        if path == '/api/props/frame':
            try:
                from scene_assets import save_prop_frame
                root = pi_path('assets') if os.path.isdir(pi_path('assets')) else os.path.join(os.path.dirname(__file__), '..', 'assets')
                result = save_prop_frame(json.loads(body.decode('utf-8')), root)
                response = json.dumps(result).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(response)))
                self.end_headers()
                self.wfile.write(response)
            except Exception as error:
                self.send_error(400, str(error))
            return

        if path == '/api/characters/frame':
            try:
                from scene_assets import save_character_frame
                payload = json.loads(body.decode('utf-8'))
                app = DeskPalHTTPHandler.app_ref
                cfg = app.cfg if app else load_config()
                character = payload.get('character', '')
                if character not in cfg.get('characters', {}):
                    raise ValueError('Create the character before uploading frames')
                root = pi_path('assets') if os.path.isdir(pi_path('assets')) else os.path.join(os.path.dirname(__file__), '..', 'assets')
                frame = save_character_frame(payload, root)
                tags_path = os.path.join(os.path.dirname(get_active_config_path()), 'sprite_tags.json')
                tags = {}
                if os.path.exists(tags_path):
                    with open(tags_path, encoding='utf-8') as source:
                        tags = json.load(source)
                tags[frame['url']] = {'variant': character}
                with open(tags_path + '.tmp', 'w', encoding='utf-8') as target:
                    json.dump(tags, target, indent=2)
                os.replace(tags_path + '.tmp', tags_path)
                response = json.dumps({'status': 'ok', 'frame': frame}).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(response)))
                self.end_headers()
                self.wfile.write(response)
            except Exception as error:
                self.send_error(400, str(error))
            return

        if path == '/api/characters/reference':
            try:
                from scene_assets import save_character_reference
                payload = json.loads(body.decode('utf-8'))
                app = DeskPalHTTPHandler.app_ref
                cfg = app.cfg if app else load_config()
                character = payload.get('character', '')
                if character not in cfg.get('characters', {}):
                    raise ValueError('Create the character before uploading its reference')
                root = pi_path('assets') if os.path.isdir(pi_path('assets')) else os.path.join(os.path.dirname(__file__), '..', 'assets')
                reference = save_character_reference(payload, root)
                cfg['characters'][character]['reference_sprite'] = reference
                save_config(cfg)
                response = json.dumps({'status': 'ok', 'reference': reference}).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(response)))
                self.end_headers()
                self.wfile.write(response)
            except Exception as error:
                self.send_error(400, str(error))
            return

        if path == '/api/scenes/background':
            try:
                from scene_assets import save_background
                roots = [os.path.join(os.path.dirname(__file__), '..', 'assets'), pi_path('assets')]
                result = save_background(json.loads(body.decode('utf-8')), roots[1] if os.path.isdir(roots[1]) else roots[0])
                response = json.dumps(result).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(response)))
                self.end_headers()
                self.wfile.write(response)
            except Exception as error:
                self.send_error(400, str(error))
            return

        if path == "/api/puppet_rig":
            try:
                rig_paths = [
                    os.path.join(os.path.dirname(__file__), "..", "config", "puppet_rig.json"),
                    pi_path('config/puppet_rig.json'),
                    "config/puppet_rig.json"
                ]
                chosen = rig_paths[1] if os.path.exists(pi_path('')) else rig_paths[0]
                os.makedirs(os.path.dirname(chosen), exist_ok=True)
                with open(chosen, "wb") as f:
                    f.write(body)
                resp = json.dumps({"status": "ok", "message": "Puppet rig calibrated and saved"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                resp = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            return

        if path == "/api/save_pose":
            try:
                import base64
                payload = json.loads(body.decode("utf-8"))
                pose_id = payload.get("pose_id", "custom_pose").strip().replace(" ", "_")
                img_data_b64 = payload.get("image_b64", "")
                puppet_state = payload.get("puppet_state", {})

                if "," in img_data_b64:
                    img_data_b64 = img_data_b64.split(",", 1)[1]

                img_bytes = base64.b64decode(img_data_b64)
                
                # Determine asset dir
                asset_roots = [
                    os.path.join(os.path.dirname(__file__), "..", "assets"),
                    pi_path('assets'),
                    "assets"
                ]
                chosen_asset = asset_roots[1] if os.path.exists(asset_roots[1]) else asset_roots[0]
                pose_dir = os.path.join(chosen_asset, "characters", "adventurer", "poses")
                os.makedirs(pose_dir, exist_ok=True)

                out_png = os.path.join(pose_dir, f"{pose_id}.png")
                with open(out_png, "wb") as f:
                    f.write(img_bytes)

                out_json = os.path.join(pose_dir, f"{pose_id}.json")
                with open(out_json, "w", encoding="utf-8") as f:
                    json.dump(puppet_state, f, indent=2)

                # Hot-reload in DeskPalApp
                if DeskPalHTTPHandler.app_ref:
                    app = DeskPalHTTPHandler.app_ref
                    if "custom_poses" not in app.cfg:
                        app.cfg["custom_poses"] = {}
                    app.cfg["custom_poses"][pose_id] = {
                        "path": f"assets/characters/adventurer/poses/{pose_id}.png",
                        "view": puppet_state.get("view", "side"),
                        "label": payload.get("label", pose_id)
                    }
                    save_config(app.cfg)
                    app.reload_character_sprites()

                resp = json.dumps({"status": "ok", "pose_id": pose_id}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                resp = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            return

        if path == "/api/scenes/travel":
            try:
                destination = json.loads(body.decode('utf-8'))['scene']
                app = DeskPalHTTPHandler.app_ref
                if destination not in app.cfg.get('scenes', {}):
                    raise ValueError('Unknown scene')
                if app.is_sleeping or getattr(app, 'scene_journey', None) or getattr(app, 'journey_arriving', False):
                    raise ValueError('Wake the display and finish the current journey first')
                app.pending_scene_destination = destination
                app.travel_error = None
                self.send_response(202)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status":"queued"}')
            except (ValueError, KeyError) as e:
                self.send_error(400, str(e))
            return

        if path == "/api/themes/apply":
            try:
                data = json.loads(body.decode('utf-8'))
                tid = data.get('theme_id')
                if not tid:
                    raise ValueError("Missing 'theme_id'")
                app = DeskPalHTTPHandler.app_ref
                if not app:
                    raise ValueError("DeskPal app not running")
                res = app.apply_theme(tid)
                payload = json.dumps(res).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                self.send_error(400, f"Theme apply error: {e}")
            return

        if path == "/api/themes/save":
            try:
                data = json.loads(body.decode('utf-8'))
                tid = data.get('id')
                name = data.get('name')
                desc = data.get('description', '')
                card_style = data.get('card_style')
                app = DeskPalHTTPHandler.app_ref
                if not app:
                    raise ValueError("DeskPal app not running")
                from theme_manager import create_theme_from_config
                theme_data = create_theme_from_config(tid, name, desc, app.cfg, card_style=card_style)
                app.cfg['theme'] = tid
                app.save_walkbox_config()
                payload = json.dumps({'status': 'ok', 'theme': theme_data}).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                self.send_error(400, f"Theme save error: {e}")
            return

        if path == "/api/themes/duplicate":
            try:
                data = json.loads(body.decode('utf-8'))
                src_id = data.get('source_id')
                new_id = data.get('new_id')
                new_name = data.get('new_name')
                from theme_manager import duplicate_theme
                cloned = duplicate_theme(src_id, new_id, new_name=new_name)
                payload = json.dumps({'status': 'ok', 'theme': cloned}).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                self.send_error(400, f"Theme duplicate error: {e}")
            return

        if path == "/api/themes/delete":
            try:
                data = json.loads(body.decode('utf-8'))
                tid = data.get('theme_id')
                app = DeskPalHTTPHandler.app_ref
                active_tid = app.cfg.get('theme') if app else None
                from theme_manager import delete_theme
                delete_theme(tid, active_theme_id=active_tid)
                payload = json.dumps({'status': 'ok'}).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                self.send_error(400, f"Theme delete error: {e}")
            return

        if path == "/api/themes/import":
            try:
                from theme_manager import import_theme_zip
                theme_data = import_theme_zip(body)
                payload = json.dumps({'status': 'ok', 'theme': theme_data}).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                self.send_error(400, f"Theme import error: {e}")
            return

        if path == "/api/config":
            try:
                new_cfg = json.loads(body.decode("utf-8"))
                if DeskPalHTTPHandler.app_ref:
                    DeskPalHTTPHandler.app_ref.apply_remote_config(new_cfg)
                resp = json.dumps({"status": "ok", "message": "Config updated and hot-reloaded"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                resp = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            return

        elif path == "/api/services/action":
            try:
                req = json.loads(body.decode("utf-8"))
                sid = req.get("id", "")
                action = req.get("action", "")
                sup = getattr(DeskPalHTTPHandler.app_ref, 'service_supervisor', None)
                if not sup:
                    raise ValueError("Companion supervisor is not running")
                if action == "start":
                    result = sup.start_service(sid)
                elif action == "stop":
                    result = sup.stop_service(sid)
                elif action == "restart":
                    result = sup.restart_service(sid)
                else:
                    raise ValueError(f"Unknown action '{action}'")
                resp = json.dumps(result).encode("utf-8")
                self.send_response(200 if result.get("success") else 400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                resp = json.dumps({"success": False, "error": str(e)}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            return

        elif path == "/api/services/save":
            try:
                req = json.loads(body.decode("utf-8"))
                sid = req.get("id", "")
                name = req.get("name", "")
                desc = req.get("description", "")
                code = req.get("code", "")
                entry = req.get("entrypoint", "main.py")
                auto_start = bool(req.get("auto_start", False))
                port = req.get("port")
                env = req.get("env")
                sup = getattr(DeskPalHTTPHandler.app_ref, 'service_supervisor', None)
                if not sup:
                    raise ValueError("Companion supervisor is not running")
                result = sup.save_service(
                    service_id=sid, name=name, description=desc, code=code,
                    entrypoint=entry, auto_start=auto_start, port=port, env=env
                )
                resp = json.dumps(result).encode("utf-8")
                self.send_response(200 if result.get("success") else 400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                resp = json.dumps({"success": False, "error": str(e)}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            return

        elif path == "/api/services/delete":
            try:
                req = json.loads(body.decode("utf-8"))
                sid = req.get("id", "")
                sup = getattr(DeskPalHTTPHandler.app_ref, 'service_supervisor', None)
                if not sup:
                    raise ValueError("Companion supervisor is not running")
                result = sup.delete_service(sid)
                resp = json.dumps(result).encode("utf-8")
                self.send_response(200 if result.get("success") else 400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                resp = json.dumps({"success": False, "error": str(e)}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            return

        elif path in ("/api/v1/event", "/api/v1/alert"):
            try:
                event_data = json.loads(body.decode("utf-8"))
                if path.endswith("/alert"):
                    event_data.setdefault("event", "alert")
                    event_data["attention_needed"] = True
                if DeskPalHTTPHandler.app_ref:
                    DeskPalHTTPHandler.app_ref.receive_telemetry_event(event_data)
                resp = json.dumps({"status": "received"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                self.send_error(400, f"Invalid event: {e}")
            return

        elif path == "/api/v1/heartbeat":
            try:
                hb_data = json.loads(body.decode("utf-8"))
                if DeskPalHTTPHandler.app_ref:
                    DeskPalHTTPHandler.app_ref.receive_heartbeat(hb_data)
                resp = json.dumps({"status": "ok"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                self.send_error(400, f"Invalid heartbeat: {e}")
            return

        elif path == "/api/v1/notify":
            try:
                data = json.loads(body.decode("utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("Notification payload must be a JSON object")
                app = DeskPalHTTPHandler.app_ref
                title = str(data.get("title") or data.get("app") or data.get("app_name") or "ALERT")[:60]
                summary = str(data.get("summary") or data.get("message") or "Notification received")[:500]
                attention = bool(data.get("attention", True))
                voice_escalation = bool(data.get("voice_escalation", True))
                voice_phrase = data.get("voice_phrase")
                if voice_phrase is not None:
                    voice_phrase = str(voice_phrase)[:200]
                color_raw = data.get("color", [240, 160, 80])
                if isinstance(color_raw, (list, tuple)) and len(color_raw) == 3:
                    color = tuple(int(c) for c in color_raw)
                else:
                    color = (240, 160, 80)
                badge = str(data.get("badge"))[:10] if data.get("badge") is not None else None
                ticker = [str(t)[:120] for t in data.get("ticker", [])] if isinstance(data.get("ticker"), list) else None
                priority = bool(data.get("priority", False))

                import uuid
                action = {
                    "id": "notify_" + uuid.uuid4().hex[:8],
                    "animation": str(data.get("animation") or ("wave_arms" if attention else "inspect")),
                    "attention_until_interaction": attention,
                    "voice_escalation": voice_escalation,
                    "voice_phrase": voice_phrase,
                    "display_mode": "popup_modal" if attention else "thought_bubble",
                    "duration_seconds": float(data.get("duration_seconds", 6)),
                    "speech": "{summary}"
                }
                if data.get("layout"):
                    action["layout"] = data["layout"]
                if data.get("slider"):
                    action["slider"] = data["slider"]
                if data.get("wellness"):
                    action["wellness"] = data["wellness"]
                app.queue_action(action, app_name=title, color=color, summary=summary, ticker=ticker, badge=badge, priority=priority)
                resp = json.dumps({"status": "queued", "activity_id": action.get("_activity_id"), "attention": attention}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                self.send_error(400, f"Notification error: {e}")
            return

        elif path == "/api/v1/action":
            try:
                data = json.loads(body.decode("utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("Action payload must be a JSON object")
                app = DeskPalHTTPHandler.app_ref
                anim = str(data.get("animation") or "idle")
                scene = data.get("scene") or data.get("target_scene")
                if scene is not None:
                    scene = str(scene)
                    if scene not in app.cfg.get("scenes", {}):
                        raise ValueError(f"Unknown scene: {scene}")
                duration = float(data.get("duration_seconds", 6))
                speech = str(data.get("speech") or data.get("summary") or "")[:200]
                display_mode = str(data.get("display_mode") or ("thought_bubble" if speech else "none"))
                priority = bool(data.get("priority", False))
                spot_id = data.get("spot_id")

                import uuid
                action = {
                    "id": "rest_action_" + uuid.uuid4().hex[:8],
                    "animation": anim,
                    "duration_seconds": duration,
                    "speech": speech,
                    "display_mode": display_mode,
                }
                if scene:
                    action["scene"] = scene
                if spot_id:
                    action["spot_id"] = str(spot_id)
                if "x" in data and "y" in data:
                    action["x"] = float(data["x"])
                    action["y"] = float(data["y"])
                    action["target_mode"] = "specific"

                app.queue_action(action, app_name="API", summary=speech, priority=priority)
                resp = json.dumps({"status": "queued", "activity_id": action.get("_activity_id"), "animation": anim, "scene": scene}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                self.send_error(400, f"Action error: {e}")
            return

        elif path in ("/api/v1/say", "/api/v1/speak"):
            try:
                data = json.loads(body.decode("utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("Speech payload must be a JSON object")
                text = data.get("text")
                if not text or not isinstance(text, str) or len(text.strip()) == 0:
                    raise ValueError("Speech requires 'text' (1-500 chars)")
                text = text.strip()[:500]
                app = DeskPalHTTPHandler.app_ref
                from speech_output import output_for
                output = output_for(app)
                config_dir = os.path.dirname(get_active_config_path())
                ai_path = os.path.join(config_dir, "ai_settings.json")
                speaker = {"enabled": True, "output": "default", "volume": 0.5}
                monitor = getattr(app, 'hardware_monitor', None)
                if monitor:
                    with monitor.lock:
                        speaker = dict(monitor.config.get("speaker", speaker))
                else:
                    try:
                        from optional_hardware import monitor_for
                        h_path = os.path.join(config_dir, "hardware_settings.json")
                        m = monitor_for(app, h_path)
                        with m.lock:
                            speaker = dict(m.config.get("speaker", speaker))
                    except Exception:
                        pass
                output.speak(text, ai_path, speaker)
                resp = json.dumps({"status": "speaking", "text": text}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                self.send_error(400, f"Speech error: {e}")
            return

        elif path == "/api/v1/scene":
            try:
                data = json.loads(body.decode("utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("Scene payload must be a JSON object")
                scene = str(data.get("scene", "")).strip()
                app = DeskPalHTTPHandler.app_ref
                if scene not in app.cfg.get("scenes", {}):
                    raise ValueError(f"Unknown scene: {scene}")
                from scene_world import activate_scene
                activate_scene(app.cfg, scene)
                app.load_scene_backgrounds()
                app.save_config()
                resp = json.dumps({"status": "ok", "scene": scene}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                self.send_error(400, f"Scene error: {e}")
            return

        elif path == "/api/v1/display":
            try:
                data = json.loads(body.decode("utf-8")) if body else {}
                action = str(data.get("action", "wake")).strip().lower()
                app = DeskPalHTTPHandler.app_ref
                if action == "sleep":
                    app.enter_standby(source="agent")
                    msg = "Display entered standby"
                elif action == "wake":
                    app.wake_from_standby(source="agent")
                    msg = "Display awakened"
                else:
                    raise ValueError(f"Unknown action '{action}', use 'sleep' or 'wake'")
                resp = json.dumps({"status": "ok", "action": action, "sleeping": getattr(app, "is_sleeping", False), "message": msg}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                self.send_error(400, f"Display action error: {e}")
            return

        elif path in ("/api/v1/modal/show", "/api/v1/morning/trigger"):
            try:
                data = json.loads(body.decode("utf-8")) if body else {}
                app = DeskPalHTTPHandler.app_ref
                app.wake_from_standby(source='agent')

                if path == "/api/v1/morning/trigger" or data.get('layout') == 'morning':
                    from morning_greeting import message, settings
                    from scene_lighting import local_now
                    options = settings(app.cfg.get('morning_greeting'))
                    now = local_now(app.cfg.get('lighting', {}))
                    summary = data.get('summary') or message(app, options, now)
                    weather_tele = app.app_telemetry.get('deskpal_weather', {})
                    progression = data.get('progression') or weather_tele.get('data', {}).get('progression')

                    modal_data = {
                        "title": data.get('title') or "GOOD MORNING!",
                        "summary": summary,
                        "layout": "morning",
                        "color": (255, 175, 40),
                        "progression": progression,
                        "date_str": now.strftime("%A, %d %b"),
                        "timestamp": time.strftime("%I:%M %p"),
                        "expires_at": time.monotonic() + 180,
                        "hold_until_dismissed": True
                    }
                    app.active_popup_modal = modal_data
                    app.pending_popup_modal = None
                    app.wander_timer = 180.0
                else:
                    app.active_popup_modal = data
                    app.pending_popup_modal = None

                resp = json.dumps({"status": "ok", "active": True}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                self.send_error(400, f"Show modal error: {e}")
            return

        elif path in ("/api/v1/modal/dismiss", "/api/v1/dismiss"):
            try:
                app = DeskPalHTTPHandler.app_ref
                dismissed = app.dismiss_active_modal()
                resp = json.dumps({"status": "ok", "dismissed": dismissed}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                self.send_error(400, f"Dismiss error: {e}")
            return

        elif path.startswith("/api/switch/"):
            try:
                sw_id = int(path.split("/")[-1])
                if DeskPalHTTPHandler.app_ref:
                    DeskPalHTTPHandler.app_ref.on_switch_pressed(sw_id)
                resp = json.dumps({"status": "triggered", "switch_id": sw_id}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                self.send_error(400, f"Error triggering switch: {e}")
            return

        if path == "/api/sprite_tags":
            try:
                tags_data = json.loads(body.decode("utf-8"))
                tag_paths = [
                    os.path.join(os.path.dirname(__file__), "..", "config", "sprite_tags.json"),
                    pi_path('config/sprite_tags.json'),
                ]
                chosen = tag_paths[1] if os.path.exists(os.path.dirname(tag_paths[1])) else tag_paths[0]
                os.makedirs(os.path.dirname(chosen), exist_ok=True)
                with open(chosen, "w", encoding="utf-8") as f:
                    json.dump(tags_data, f, indent=2)
                resp = json.dumps({"status": "ok"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                resp = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            return

        if path == "/api/delete_frame":
            try:
                payload = json.loads(body.decode("utf-8"))
                frame_url = payload.get("url", "")
                # Security: only allow deleting within adventurer assets
                if not frame_url.startswith("/assets/characters/adventurer/"):
                    raise ValueError("Cannot delete files outside adventurer assets")
                rel_path = frame_url[len("/assets/"):]
                asset_roots = [
                    os.path.join(os.path.dirname(__file__), "..", "assets"),
                    pi_path('assets'),
                    "assets"
                ]
                deleted = False
                for ar in asset_roots:
                    candidate = os.path.join(ar, rel_path.replace("/", os.sep))
                    if os.path.exists(candidate) and os.path.isfile(candidate):
                        os.remove(candidate)
                        deleted = True
                        break
                resp = json.dumps({"status": "ok", "deleted": deleted}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                resp = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            return

        if path == "/api/set_reference":
            try:
                payload = json.loads(body.decode("utf-8"))
                ref_url = payload.get("url", "")
                ref_name = payload.get("name", "")
                app = DeskPalHTTPHandler.app_ref
                cfg = app.cfg if app else load_config()
                character = payload.get('character')
                reference = {"name": ref_name, "url": ref_url}
                if character:
                    if character not in cfg.get('characters', {}):
                        raise ValueError('Unknown character')
                    cfg['characters'][character]['reference_sprite'] = reference
                else:
                    cfg['reference_sprite'] = reference  # Legacy clients.
                save_config(cfg)
                resp = json.dumps({"status": "ok", "reference": ref_name}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                resp = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            return

        self.send_error(404, "Not Found")


def parse_dashboard_modal(modal):
    """Formats or auto-parses modal data into a high-visibility 5-inch dashboard layout."""
    if not isinstance(modal, dict):
        return {'layout': 'classic', 'summary': ''}

    # If explicitly structured dashboard, return normalized
    if modal.get('hero_value'):
        badge = str(modal.get('badge', '')).strip()
        badge_col = modal.get('badge_color')
        if not badge_col:
            badge_u = badge.upper()
            if any(k in badge_u for k in ('BUY', 'HEALTHY', 'OK', 'ONLINE', 'LOW')):
                badge_col = (46, 204, 113)
            elif any(k in badge_u for k in ('WAIT', 'HOLD', 'WARNING', 'STORM', 'ALERT', 'HIGH')):
                badge_col = (231, 76, 60)
            elif any(k in badge_u for k in ('RAIN', 'WIND', 'ORDER', 'NEW')):
                badge_col = (52, 152, 219)
            else:
                badge_col = tuple(modal.get('color', (0, 229, 255)))
        return {
            'layout': 'dashboard',
            'hero_value': str(modal.get('hero_value', '')),
            'hero_subhead': str(modal.get('hero_subhead', '')),
            'badge': badge,
            'badge_color': badge_col,
            'tiles': modal.get('tiles', [])
        }

    summary = str(modal.get('summary', '')).strip()
    title = str(modal.get('title', '')).upper()

    # 0. Morning Greeting Pattern
    if 'MORNING' in title or modal.get('is_morning_greeting'):
        import re
        date_match = re.search(r'\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\d+\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b', summary)
        date_str = date_match.group(0) if date_match else time.strftime("%A, %d %b")

        tiles = []
        # Weather tile: temperature
        temp_match = re.search(r'Today\s*([\d\.]+[–\-][\d\.]+°C|[\d\.]+°C)', summary)
        if temp_match:
            tiles.append({'label': 'WEATHER', 'value': temp_match.group(1)})
        else:
            single_temp = re.search(r'(\d+\.?\d*)\s*°C', summary)
            if single_temp:
                tiles.append({'label': 'WEATHER', 'value': f"{single_temp.group(1)}°C"})

        # Rain tile
        rain_match = re.search(r'Rain\s*(\d+%)', summary, re.IGNORECASE)
        if rain_match:
            tiles.append({'label': 'RAIN CHANCE', 'value': rain_match.group(1)})

        # Fuel tile
        fuel_price = re.search(r'([\d\.]+)\s*(?:¢/L|c/L|\ufffd/L)', summary)
        if fuel_price:
            tiles.append({'label': 'U98 FUEL', 'value': f"{fuel_price.group(1)}¢"})
        elif '¢' in summary:
            c_match = re.search(r'(\d+\.?\d*)\s*¢', summary)
            if c_match:
                tiles.append({'label': 'FUEL', 'value': f"{c_match.group(1)}¢"})

        # Wind tile
        wind_match = re.search(r'Wind up to\s*([\d\.]+\s*km/h)', summary, re.IGNORECASE)
        if wind_match:
            tiles.append({'label': 'WIND', 'value': wind_match.group(1)})

        return {
            'layout': 'morning',
            'hero_value': "Good Morning!",
            'hero_subhead': f"Daily Briefing · {date_str}",
            'badge': "TODAY",
            'date_str': date_str,
            'badge_color': (255, 175, 40),
            'tiles': tiles[:4],
            'progression': modal.get('progression')
        }

    # 1. Fuel Pattern
    if 'FUEL' in title or '¢/L' in summary or 'CHEAPEST' in summary.upper():
        hero_val = ""
        subhead = ""
        badge = "FUEL"
        badge_color = (0, 200, 255)
        tiles = []

        import re
        cheapest_match = re.search(r'cheapest option is (.+?)\s+at\s+([\d\.]+)\s*(?:¢/L|c/L|\ufffd/L)', summary, re.IGNORECASE)
        if cheapest_match:
            subhead = cheapest_match.group(1).strip()
            hero_val = f"{cheapest_match.group(2).strip()}¢/L"
        else:
            price_match = re.search(r'([\d\.]+)\s*(?:¢/L|c/L|\ufffd/L)', summary)
            if price_match:
                hero_val = f"{price_match.group(1)}¢/L"

        if 'BUY NOW' in summary.upper() or 'GOOD TIME TO BUY' in summary.upper():
            badge = "BUY NOW"
            badge_color = (46, 204, 113)
        elif 'HOLD OFF' in summary.upper() or 'WAIT' in summary.upper():
            badge = "HOLD OFF"
            badge_color = (231, 76, 60)

        avg_match = re.search(r'averages?\s*([\d\.]+)\s*(?:¢/L|c/L|\ufffd/L)', summary, re.IGNORECASE)
        if avg_match:
            tiles.append({'label': 'AREA AVG', 'value': f"{avg_match.group(1)}¢"})

        trend_match = re.search(r'expected to (rise|fall|drop|increase|decrease)[^\.\n]*', summary, re.IGNORECASE)
        if trend_match:
            trend_val = "Rising 48h" if "rise" in trend_match.group(0).lower() or "increase" in trend_match.group(0).lower() else "Falling"
            tiles.append({'label': 'TREND', 'value': trend_val})

        dist_match = re.search(r'\(([\d\.]+km away)\)', summary, re.IGNORECASE)
        if dist_match:
            tiles.append({'label': 'DISTANCE', 'value': dist_match.group(1).replace(' away', '')})

        if hero_val:
            return {
                'layout': 'dashboard',
                'hero_value': hero_val,
                'hero_subhead': subhead or "Local fuel price",
                'badge': badge,
                'badge_color': badge_color,
                'tiles': tiles
            }

    # 2. Weather Pattern
    if 'WEATHER' in title or '°C' in summary or 'RAIN' in summary.upper():
        import re
        max_temp_match = re.search(r'[\d\.]+[–\-](\d+\.?\d*)\s*°C', summary)
        single_temp_match = re.search(r'(\d+\.?\d*)\s*°C', summary)
        hero_temp = (max_temp_match.group(1) if max_temp_match else (single_temp_match.group(1) if single_temp_match else "22")) + "°C"

        badge = "WEATHER"
        badge_color = (0, 180, 240)
        rain_match = re.search(r'Rain\s*(\d+%)', summary, re.IGNORECASE)
        if rain_match:
            badge = f"Rain {rain_match.group(1)}"
            badge_color = (52, 152, 219)

        tiles = []
        min_temp_match = re.search(r'Today\s*([\d\.]+)–', summary)
        if min_temp_match:
            tiles.append({'label': 'MIN TEMP', 'value': f"{min_temp_match.group(1)}°C"})

        wind_match = re.search(r'Wind up to\s*([\d\.]+\s*km/h)', summary, re.IGNORECASE)
        if wind_match:
            tiles.append({'label': 'WIND', 'value': wind_match.group(1)})

        uv_match = re.search(r'UV\s*([\d\.]+)', summary, re.IGNORECASE)
        if uv_match:
            tiles.append({'label': 'UV INDEX', 'value': uv_match.group(1)})

        return {
            'layout': 'dashboard',
            'hero_value': hero_temp,
            'hero_subhead': "Today's forecast",
            'badge': badge,
            'badge_color': badge_color,
            'tiles': tiles
        }

    # 3. Store / Orders Pattern
    if 'ORDER' in title or 'ORDER' in summary.upper() or 'SHIPMENT' in summary.upper():
        import re
        order_match = re.search(r'(\d+)\s*active orders?', summary, re.IGNORECASE)
        count = order_match.group(1) if order_match else "1"
        return {
            'layout': 'dashboard',
            'hero_value': f"{count} Orders",
            'hero_subhead': "Awaiting fulfillment",
            'badge': "ORDERS",
            'badge_color': (243, 156, 18),
            'tiles': [{'label': 'STATUS', 'value': 'Ready to ship'}]
        }

    return {'layout': 'classic', 'summary': summary}


class DeskPalApp:
    def __init__(self, desktop_mode=None, window_size=None):
        self._display_thread = threading.get_ident()
        self._switch_inputs = queue.SimpleQueue()
        self.local_preview = os.environ.get('DESKPAL_LOCAL_PREVIEW') == '1'

        # Desktop Companion Mode detection
        if desktop_mode is None:
            cli_desktop = any(arg in sys.argv for arg in ('--desktop', '-d', '--window', '--windowed'))
            env_desktop = os.environ.get('DESKPAL_DESKTOP_MODE') == '1' or os.environ.get('DESKPAL_DESKTOP') == '1'
            auto_desktop = (os.name == 'nt' or not os.path.exists('/sys/class/backlight')) and not self.local_preview and not any(arg in sys.argv for arg in ('--fullscreen', '--pi'))
            self.desktop_mode = cli_desktop or env_desktop or auto_desktop
        else:
            self.desktop_mode = bool(desktop_mode)

        self.win_width = 960
        self.win_height = 540
        if window_size:
            self.win_width, self.win_height = window_size
        else:
            for i, arg in enumerate(sys.argv):
                if arg in ('--size', '--window-size') and i + 1 < len(sys.argv):
                    try:
                        parts = sys.argv[i + 1].lower().split('x')
                        self.win_width, self.win_height = max(320, int(parts[0])), max(180, int(parts[1]))
                    except Exception:
                        pass
                elif arg.startswith('--size=') or arg.startswith('--window-size='):
                    try:
                        parts = arg.split('=', 1)[1].lower().split('x')
                        self.win_width, self.win_height = max(320, int(parts[0])), max(180, int(parts[1]))
                    except Exception:
                        pass

        if self.local_preview:
            self.studio_url = 'http://127.0.0.1:' + os.environ.get('DESKPAL_PREVIEW_PORT', '7779')
        elif self.desktop_mode:
            port_str = os.environ.get('DESKPAL_PORT', '7777')
            self.studio_url = os.environ.get('DESKPAL_STUDIO_URL', f'http://127.0.0.1:{port_str}')
        else:
            self.studio_url = os.environ.get('DESKPAL_STUDIO_URL', 'http://localhost:7777')

        self.preview_bridge = None
        if self.local_preview or os.environ.get('DESKPAL_REMOTE_DISPLAY', '1') != '0':
            from local_preview import PreviewBridge
            self.preview_bridge = PreviewBridge()
        pygame.init()
        try:
            pygame.mixer.quit()
        except Exception:
            pass
        pygame.mouse.set_visible(True)

        self.cfg = load_config()
        from sensor_events import ensure_sensor_source
        ensure_sensor_source(self.cfg)
        from weather_source import ensure_weather_source
        ensure_weather_source(self.cfg)
        ensure_world(self.cfg)
        activate_scene(self.cfg, scene_id(self.cfg))
        self.palette = {k: tuple(v) for k, v in self.cfg["palette"].items()}
        self.switches = self.cfg["switches"]
        self.props = self.cfg.get("props", [])
        self.event_mappings = self.cfg.get("event_mappings", [])
        self.apps = self.cfg.get("apps", [])
        self.target_facing_left = None
        self.target_animation = "idle"
        self.active_popup_modal = None
        self.pending_popup_modal = None
        self.active_slider_dragging = False
        self.popup_slider_rect = None
        self.popup_slider_data = None
        self.pending_post_travel_action = None
        self.active_prop_overlays = {}
        self.trap = self.cfg.get("walkable_trapezoid", {
            "y_min": 516, "y_max": 700,
            "scale_at_y_min": 275, "scale_at_y_max": 385,
            "back_x_min": 424, "back_x_max": 941,
            "front_x_min": 225, "front_x_max": 1136
        })
        self.obstacles = self.cfg.get("obstacles", [])
        try:
            from voice_sentry import sentry_for
            self.voice_sentry = sentry_for(self)
        except Exception:
            self.voice_sentry = None

        # Display Setup
        self.width = 1280
        self.height = 720
        if self.desktop_mode:
            from desktop_mode import DesktopDisplayPower, DesktopWindow
            self.desktop_helper = DesktopWindow()
            self.display_power = DesktopDisplayPower()
            self.window = pygame.display.set_mode((self.win_width, self.win_height), pygame.RESIZABLE)
            self.screen = pygame.Surface((self.width, self.height))
            pygame.display.set_caption("Desk-Pal Companion")
        elif self.local_preview:
            from local_preview import PreviewDisplayPower
            self.display_power = PreviewDisplayPower()
            self.window = self.screen = pygame.display.set_mode((self.width, self.height), 0)
            pygame.display.set_caption("Desk-Pal")
        else:
            info = pygame.display.Info()
            self.width = info.current_w or 1280
            self.height = info.current_h or 720
            self.display_power = DisplayPower()
            self.window = self.screen = pygame.display.set_mode((self.width, self.height), pygame.FULLSCREEN | pygame.DOUBLEBUF)
            pygame.display.set_caption("Desk-Pal")
        self.clock = pygame.time.Clock()

        self.load_scene_backgrounds()
        self.display_power.set_sleeping(False)  # Recover panel power after a process restart.

        # Character Sprites
        self.raw_sprites = {}
        char_dir_candidates = [
            os.path.join(os.path.dirname(__file__), "..", "assets", "characters", "adventurer"),
            pi_path('assets/characters/adventurer'),
            "assets/characters/adventurer"
        ]
        char_dir = None
        for cd in char_dir_candidates:
            if os.path.exists(cd):
                char_dir = cd
                break

        if char_dir:
            try:
                for f in sorted(os.listdir(char_dir)):
                    if f.endswith(".png"):
                        sname = f[:-4]
                        sp_path = os.path.join(char_dir, f)
                        self.raw_sprites[sname] = pygame.image.load(sp_path).convert_alpha()
                print(f"Loaded {len(self.raw_sprites)} raw adventurer character sprites: {list(self.raw_sprites.keys())}")
            except Exception as e:
                print(f"[WARN] Failed loading raw sprites: {e}")

        self.sprite_cache = SurfaceCache()
        self.char_dir = char_dir
        self.configure_character(self.cfg)

        # Configurable Dynamic UI & Font Scaling (Standard, Large, Extra Large)
        self.ui_font_scale = self.cfg.get("ui_font_scale", "large")
        self._init_fonts(self.ui_font_scale)

        # State
        self.running = True
        self.is_sleeping = False
        self.show_shutdown_modal = False
        self.quick_keys_mode = self.cfg.get("on_screen_buttons", "on_press")
        self.show_quick_keys = (self.quick_keys_mode == "always")
        self.keys_pinned = (self.quick_keys_mode == "always")
        self.keys_dismiss_timer = 0.0
        self.switch_press_times = {s["id"]: 0.0 for s in self.switches}

        # Editor Mode State
        self.edit_mode = False
        self.active_handle = None
        self.active_obstacle_idx = None
        self.is_resizing_obstacle = False
        self.editor_hide_char = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0
        self.save_feedback_timer = 0.0

        # Character State
        self.char_x = float(self.width // 2)
        self.char_y = float((self.trap["y_min"] + self.trap["y_max"]) // 2 + 30)
        self.target_x = self.char_x
        self.target_y = self.char_y
        self.facing_left = False
        self.is_inspecting = False
        self.current_anim = "idle"
        self.target_facing_left = None
        self.target_animation = None
        self.pending_popup_modal = None
        self.active_popup_modal = None
        self.sleep_particles = []

        # Autonomous Wander
        self.anim_frame = 0
        self.anim_timer = 0.0
        self.wander_timer = random.uniform(3.0, 6.0)
        self.status_msg = "Monitoring QLD fuel prices"

        # Telemetry survives restarts independently of editable scene configuration.
        from integration_state import load_telemetry
        self.telemetry_path = os.path.join(os.path.dirname(get_active_config_path()), 'telemetry_state.json')
        self.app_telemetry = load_telemetry(self.telemetry_path)
        from activity_queue import ActivityQueue
        self.activity_queue = ActivityQueue()
        from attention_voice import AttentionVoiceManager
        self.attention_voice_manager = AttentionVoiceManager(os.path.dirname(get_active_config_path()))
        self.activity_history_path = os.path.join(os.path.dirname(get_active_config_path()), 'activity_history.jsonl')
        self.audit_activity('runtime_started')
        self.integration_started = time.time()
        self.integration_attention = {}
        self.attention_seen = {}
        self.connectivity_monitor=ConnectivityMonitor()
        health_options=health_settings(self.cfg.get('system_health'))
        if os.environ.get('DESKPAL_LOCAL_PREVIEW')=='1':health_options['enabled']=False
        self.connectivity_monitor.configure(health_options)
        self.connectivity_monitor.start()

        # Main Header UI Touch Rects
        self.top_controls_open = False
        self.top_swipe_start = None
        self.btn_keys_rect = pygame.Rect(16, 80, 85, 44)
        self.btn_edit_rect = pygame.Rect(108, 80, 85, 44)
        self.btn_font_rect = pygame.Rect(200, 80, 110, 44)
        self.btn_exit_rect = pygame.Rect(self.width - 110, 12, 95, 44)

        # Editor Top Bar Touch Rects (Row 1)
        self.ed_done_rect = pygame.Rect(15, 12, 85, 44)
        self.ed_save_rect = pygame.Rect(108, 12, 85, 44)
        
        self.ed_back_minus = pygame.Rect(205, 14, 32, 40)
        self.ed_back_plus  = pygame.Rect(310, 14, 32, 40)
        self.ed_front_minus = pygame.Rect(355, 14, 32, 40)
        self.ed_front_plus  = pygame.Rect(460, 14, 32, 40)

        self.ed_toggle_char_rect = pygame.Rect(505, 12, 110, 44)
        self.ed_add_block_rect = pygame.Rect(625, 12, 95, 44)
        self.ed_del_block_rect = pygame.Rect(728, 12, 95, 44)

        # Discrete size adjustments for selected block
        self.ed_w_minus = pygame.Rect(840, 14, 30, 40)
        self.ed_w_plus  = pygame.Rect(915, 14, 30, 40)
        self.ed_h_minus = pygame.Rect(960, 14, 30, 40)
        self.ed_h_plus  = pygame.Rect(1035, 14, 30, 40)

        self.modal_cancel_rect = pygame.Rect(self.width // 2 - 220, self.height // 2 + 50, 190, 70)
        self.modal_shutdown_rect = pygame.Rect(self.width // 2 + 30, self.height // 2 + 50, 190, 70)

        # Setup GPIO Switches
        self.gpio_buttons = {}
        self._init_gpio()

        # Start Embedded HTTP Server on Port 7777
        self._init_http_server()

        # Initialize Companion Services Supervisor
        self._init_companion_services()

        # Initialize Speech Output & Warmup
        try:
            from speech_output import output_for
            output_for(self)
        except Exception as e:
            print(f"[Speech] Init error: {e}")

        self.save_config = self.save_walkbox_config

    def _init_fonts(self, scale_name="large"):
        self.ui_font_scale = scale_name
        if scale_name == "extra_large":
            self.font_title = pygame.font.Font(None, 64)
            self.font_lg = pygame.font.Font(None, 52)
            self.font_md = pygame.font.Font(None, 38)
            self.font_sm = pygame.font.Font(None, 28)
            self.font_hero = pygame.font.Font(None, 96)
            self.font_badge = pygame.font.Font(None, 34)
            self.font_tile_val = pygame.font.Font(None, 44)
            self.font_tile_label = pygame.font.Font(None, 26)
            self.font_xs = pygame.font.Font(None, 24)
        elif scale_name == "standard":
            self.font_title = pygame.font.Font(None, 44)
            self.font_lg = pygame.font.Font(None, 36)
            self.font_md = pygame.font.Font(None, 28)
            self.font_sm = pygame.font.Font(None, 22)
            self.font_hero = pygame.font.Font(None, 72)
            self.font_badge = pygame.font.Font(None, 26)
            self.font_tile_val = pygame.font.Font(None, 34)
            self.font_tile_label = pygame.font.Font(None, 20)
            self.font_xs = pygame.font.Font(None, 18)
        else:  # "large" (default for 5-inch 720p)
            self.font_title = pygame.font.Font(None, 56)
            self.font_lg = pygame.font.Font(None, 46)
            self.font_md = pygame.font.Font(None, 34)
            self.font_sm = pygame.font.Font(None, 26)
            self.font_hero = pygame.font.Font(None, 84)
            self.font_badge = pygame.font.Font(None, 30)
            self.font_tile_val = pygame.font.Font(None, 40)
            self.font_tile_label = pygame.font.Font(None, 22)
            self.font_xs = pygame.font.Font(None, 22)
        print(f"[UI] Fonts initialized with scale: {scale_name}")

    def _init_http_server(self):
        DeskPalHTTPHandler.app_ref = self
        try:
            host = '127.0.0.1' if self.local_preview else '0.0.0.0'
            port = int(os.environ.get('DESKPAL_PREVIEW_PORT', '7779')) if self.local_preview else 7777
            self.httpd = ThreadingHTTPServer((host, port), DeskPalHTTPHandler)
            http_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            http_thread.start()
            print(f"[HTTP] Web Studio & REST API running at http://{host}:{port}")
        except Exception as e:
            print(f"[WARN] Failed to start HTTP server on port 7777: {e}")
            if self.local_preview:
                raise

    def _init_companion_services(self):
        try:
            from companion_supervisor import CompanionSupervisor
            services_dir = pi_path('services') if os.path.exists(pi_path('services')) else os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'services'))
            logs_dir = pi_path('logs/services') if os.path.exists(pi_path('logs')) else os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'logs', 'services'))
            self.service_supervisor = CompanionSupervisor(services_dir, logs_dir)
            self.service_supervisor.start_auto_services()
            print(f"[SUPERVISOR] Companion Services active at {services_dir}")
        except Exception as e:
            print(f"[WARN] Failed to start CompanionSupervisor: {e}")
            self.service_supervisor = None

    def configure_character(self, cfg):
        """Load character-owned directional sequences atomically."""
        character = cfg.get("active_character")
        if not character:
            self.walk_frames, self.walk_fps, self.walk_ping_pong = [], 10, False
            self.character_sequences = {}
            return
        with open(os.path.join(os.path.dirname(get_active_config_path()), "sprite_tags.json"), encoding="utf-8") as f:
            tags = json.load(f)
        bindings = cfg.get("characters", {}).get(character, {}).get("animations", {})
        if not bindings.get("walk_side", bindings.get("walk")):
            raise ValueError("Choose a walking sequence belonging to the active character")
        loaded, sequences, metrics = {}, {}, {}
        prefix = "/assets/characters/adventurer/"
        for role in bindings:
            sequence_id = bindings.get(role)
            if not sequence_id:
                continue
            sequence = cfg.get("animation_sequences", {}).get(sequence_id)
            if not sequence or sequence.get("character") != character:
                raise ValueError("Sequence must belong to " + character)
            fps = sequence.get("fps", 8)
            if not isinstance(fps, (int, float)) or not math.isfinite(fps) or not 1 <= fps <= 60:
                raise ValueError("Animation FPS must be between 1 and 60")
            frames = sequence.get("frames", [])
            if not isinstance(frames, list) or not frames:
                raise ValueError("Animation needs at least one frame")
            keys = []
            for frame in frames:
                url = frame.get("url", "")
                if not url.startswith(prefix) or not self.char_dir:
                    raise ValueError("Invalid sprite URL")
                path = os.path.realpath(os.path.join(self.char_dir, url[len(prefix):]))
                if os.path.commonpath([os.path.realpath(self.char_dir), path]) != os.path.realpath(self.char_dir):
                    raise ValueError("Sprite must be inside character assets")
                if tags.get(url, {}).get("variant") != character:
                    raise ValueError("Every animation frame must be tagged as " + character)
                crop = frame.get("crop", tags.get(url, {}).get("crop"))
                reference_height = frame.get('reference_height', tags.get(url, {}).get('reference_height'))
                anchor_x = frame.get('anchor_x', tags.get(url, {}).get('anchor_x', 0.5))
                if reference_height is not None and (not isinstance(reference_height, (int, float)) or not math.isfinite(reference_height) or reference_height <= 0):
                    raise ValueError('Invalid reference height')
                if not isinstance(anchor_x, (int, float)) or not math.isfinite(anchor_x) or not 0 <= anchor_x <= 1:
                    raise ValueError('Invalid frame anchor')
                key = url + ("#" + json.dumps(crop) if crop else "")
                if reference_height is not None or anchor_x != 0.5:
                    key += '#' + json.dumps([reference_height, anchor_x])
                if key not in loaded:
                    sprite = pygame.image.load(path).convert_alpha()
                    from sleep_effects import head_anchor, head_radius
                    sleep_head = head_anchor(tags.get(url, {}).get('skeleton', {}), sprite.get_size(), crop)
                    sleep_radius = head_radius(tags.get(url, {}).get('skeleton', {}), sprite.get_size(), crop)
                    if crop:
                        rect = pygame.Rect(crop)
                        if rect.width <= 0 or rect.height <= 0 or not sprite.get_rect().contains(rect):
                            raise ValueError("Invalid frame crop")
                        sprite = sprite.subsurface(rect).copy()
                    loaded[key] = sprite
                    metrics[key] = dict(reference_height=reference_height, anchor_x=anchor_x, head_anchor=sleep_head, head_radius=sleep_radius)
                keys.append(key)
            mode = sequence.get('playback_mode', 'ping_pong' if sequence.get('ping_pong') else 'loop')
            if mode not in ('once', 'repeat', 'loop', 'ping_pong'):
                raise ValueError('Invalid playback mode')
            repeats = sequence.get('repeat_count', 1)
            if not isinstance(repeats, int) or isinstance(repeats, bool) or not 1 <= repeats <= 1000:
                raise ValueError('Repeat count must be an integer from 1 to 1000')
            sequences[role] = dict(frames=keys, fps=fps, playback_mode=mode, repeat_count=repeats, ping_pong=mode=='ping_pong', idle_eligible=bool(sequence.get('idle_eligible', role.startswith('idle'))), standby_eligible=bool(sequence.get('standby_eligible', role in ('sleeping','sitting_rest','seated_back','deck_chair_rest'))), entry_transition=sequence.get('entry_transition'), exit_transition=sequence.get('exit_transition'), allowed_scenes=sequence.get('allowed_scenes', []), transition_only=bool(sequence.get('transition_only', False)))
        side = sequences.get("walk_side", sequences.get("walk"))
        sequences["walk_side"] = side
        for url, tag in tags.items():
            if tag.get("variant") == character and url.startswith(prefix):
                relative = url[len(prefix):]
                if "/" not in relative and "\\" not in relative:
                    path = os.path.join(self.char_dir, relative)
                    if os.path.isfile(path):
                        loaded[os.path.splitext(relative)[0]] = pygame.image.load(path).convert_alpha()
        idle = sequences.get("idle_side", side)
        loaded["idle"] = loaded[idle["frames"][0]] if "idle_side" in sequences else loaded.get("idle", loaded[side["frames"][0]])
        self.raw_sprites, self.character_sequences = loaded, sequences
        self.sprite_metrics = metrics
        self.walk_frames, self.walk_fps, self.walk_ping_pong = side['frames'], side['fps'], side['ping_pong']
        self.sprite_cache.clear()
        self.anim_frame, self.anim_timer = 0, 0.0
        self.motion_direction = getattr(self, 'motion_direction', 'side')
        self.idle_started = time.monotonic()
        self.gesture_role = None
        print(f"[Animation] Character={character}, loaded roles={list(sequences)}", flush=True)

    def current_walk_sequence(self):
        sequences = getattr(self, 'character_sequences', {})
        return sequences.get('walk_' + getattr(self, 'motion_direction', 'side'),
                             dict(frames=self.walk_frames, fps=self.walk_fps, ping_pong=self.walk_ping_pong))

    @staticmethod
    def sequence_sprite_name(sequence, tick):
        frames = sequence['frames']
        mode = sequence.get('playback_mode', 'ping_pong' if sequence.get('ping_pong') else 'loop')
        limit = DeskPalApp.sequence_tick_limit(sequence)
        if tick >= limit:
            return frames[-1]
        period = 2*len(frames)-2 if mode == 'ping_pong' and len(frames)>1 else len(frames)
        index = tick % period
        if index >= len(frames):
            index = 2*len(frames)-2-index
        return frames[index]

    @staticmethod
    def sequence_tick_limit(sequence):
        mode = sequence.get('playback_mode', 'ping_pong' if sequence.get('ping_pong') else 'loop')
        if mode == 'once':
            return len(sequence['frames'])
        if mode == 'repeat':
            return len(sequence['frames']) * sequence.get('repeat_count', 1)
        return math.inf

    def get_wellness_sprite(self, name):
        if not hasattr(self, '_wellness_sprite_cache'):
            self._wellness_sprite_cache = {}
        if name in self._wellness_sprite_cache:
            return self._wellness_sprite_cache[name]

        surf = None
        if name == 'glass':
            paths = [
                pi_path('assets/props/wellness_glass.png'),
                os.path.join(os.path.dirname(__file__), '..', 'assets', 'props', 'wellness_glass.png'),
                'assets/props/wellness_glass.png'
            ]
            for p in paths:
                if os.path.exists(p):
                    try:
                        raw = pygame.image.load(p).convert_alpha()
                        surf = pygame.transform.smoothscale(raw, (130, 130))
                        break
                    except Exception:
                        pass
        elif name == 'sip':
            paths = [
                pi_path('assets/characters/adventurer/wellness_drink_sip.png'),
                os.path.join(os.path.dirname(__file__), '..', 'assets', 'characters', 'adventurer', 'wellness_drink_sip.png'),
                'assets/characters/adventurer/wellness_drink_sip.png'
            ]
            for p in paths:
                if os.path.exists(p):
                    try:
                        raw = pygame.image.load(p).convert_alpha()
                        surf = pygame.transform.smoothscale(raw, (108, 130))
                        break
                    except Exception:
                        pass
            if not surf and hasattr(self, 'raw_sprites') and 'wellness_drink_sip' in self.raw_sprites:
                surf = pygame.transform.smoothscale(self.raw_sprites['wellness_drink_sip'], (108, 130))
        elif name == 'stretch':
            paths = [
                pi_path('assets/characters/adventurer/resting_stretch.png'),
                os.path.join(os.path.dirname(__file__), '..', 'assets', 'characters', 'adventurer', 'resting_stretch.png'),
                'assets/characters/adventurer/resting_stretch.png'
            ]
            for p in paths:
                if os.path.exists(p):
                    try:
                        raw = pygame.image.load(p).convert_alpha()
                        surf = pygame.transform.smoothscale(raw, (92, 142))
                        break
                    except Exception:
                        pass
            if not surf and hasattr(self, 'raw_sprites') and 'resting_stretch' in self.raw_sprites:
                surf = pygame.transform.smoothscale(self.raw_sprites['resting_stretch'], (92, 142))

        self._wellness_sprite_cache[name] = surf
        return surf

    def get_weather_sprite(self, name, size=(88, 88)):
        if not hasattr(self, '_weather_sprite_cache'):
            self._weather_sprite_cache = {}
        cache_key = (name, size)
        if cache_key in self._weather_sprite_cache:
            return self._weather_sprite_cache[cache_key]

        filename = f"{name}.png" if not name.endswith('.png') else name
        paths = [
            pi_path(f'assets/props/{filename}'),
            os.path.join(os.path.dirname(__file__), '..', 'assets', 'props', filename),
            f'assets/props/{filename}'
        ]
        surf = None
        for p in paths:
            if os.path.exists(p):
                try:
                    raw = pygame.image.load(p).convert_alpha()
                    surf = pygame.transform.smoothscale(raw, size)
                    break
                except Exception:
                    pass
        self._weather_sprite_cache[cache_key] = surf
        return surf

    def get_wellness_stretch_frame(self):
        if not hasattr(self, '_wellness_stretch_frames'):
            frames = []
            for name in ['wellness_stretch_0.png', 'wellness_stretch_1.png']:
                paths = [
                    pi_path(f'assets/characters/adventurer/{name}'),
                    os.path.join(os.path.dirname(__file__), '..', 'assets', 'characters', 'adventurer', name),
                    f'assets/characters/adventurer/{name}'
                ]
                for p in paths:
                    if os.path.exists(p):
                        try:
                            raw = pygame.image.load(p).convert_alpha()
                            target_h = 155
                            target_w = max(1, int(raw.get_width() * target_h / raw.get_height()))
                            surf = pygame.transform.smoothscale(raw, (target_w, target_h))
                            frames.append(surf)
                            break
                        except Exception:
                            pass
            if not frames:
                fallback = self.get_wellness_sprite('stretch')
                if fallback:
                    frames = [fallback]
            self._wellness_stretch_frames = frames

        frames = self._wellness_stretch_frames
        if not frames:
            return None
        idx = int(time.time() * 2.0) % len(frames)
        return frames[idx]

    def walking_sprite_name(self):
        sequence = self.current_walk_sequence()
        return self.sequence_sprite_name(sequence, self.anim_frame) if sequence['frames'] else f"walk_{self.anim_frame % 6}"

    def idle_sprite_name(self):
        direction = getattr(self, 'motion_direction', 'side')
        sequences = getattr(self, 'character_sequences', {})
        sequence = sequences.get('idle_' + direction, sequences.get('idle_side'))
        if not sequence:
            return 'idle'
        started = getattr(self, 'idle_started', time.monotonic())
        if getattr(self, 'gesture_role', None) == 'idle':
            sequence = self.action_sequence('idle') or sequence
            started = self.gesture_started
        tick = int((time.monotonic()-started) * sequence['fps'])
        return self.sequence_sprite_name(sequence, tick)

    def action_sequence(self, role):
        sequence = getattr(self, 'character_sequences', {}).get('idle_side' if role == 'idle' else role)
        if not sequence:
            return None
        active = getattr(getattr(self, 'activity_queue', None), 'active', None)
        if active and active[0].get('_attention_waiting') and not active[0].get('_attention_acknowledged'):
            if role == getattr(self, 'target_animation', None):
                return dict(sequence, playback_mode='loop', ping_pong=False)
        spot = next((s for s in self.cfg.get('interaction_spots', []) if s.get('id') == getattr(self, 'target_spot_id', None)), None)
        override = (spot or {}).get('playback_overrides', {}).get(self.cfg.get('active_character'), {}).get(role)
        override = getattr(self, 'target_playback_override', None) or override
        if getattr(self, 'is_sleeping', False) and (
            role in ('sleeping', 'sitting_rest', 'seated_back', 'deck_chair_rest')
            or sequence.get('standby_eligible')
            or role.startswith(('sleep', 'sitting_', 'seated_'))
        ):
            return dict(sequence, playback_mode='loop', ping_pong=False)
        if not override or override.get('playback_mode') not in ('once', 'repeat', 'loop', 'ping_pong'):
            return sequence
        count = override.get('repeat_count', 1)
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 1000:
            count = 1
        return dict(sequence, playback_mode=override['playback_mode'], repeat_count=count, ping_pong=override['playback_mode']=='ping_pong')

    def gesture_sprite_name(self, role):
        """Start an assigned action loop at its first frame when the action changes."""
        sequence = self.action_sequence(role)
        if not sequence:
            return None
        now = time.monotonic()
        if getattr(self, 'gesture_role', None) != role:
            self.gesture_role, self.gesture_started = role, now
        return self.sequence_sprite_name(sequence, int((now-self.gesture_started)*sequence['fps']))

    def load_scene_backgrounds(self):
        scene = self.cfg['scenes'][scene_id(self.cfg)]
        theme = scene.get('theme', scene_id(self.cfg))
        for attr, filename in (('bg_day', scene.get('background', 'background.jpg')), ('bg_night', scene.get('background_night', 'background_night.jpg'))):
            setattr(self, attr, None)
            for root in (os.path.join(os.path.dirname(__file__), '..'), pi_path('')):
                path = os.path.join(root, 'assets', 'themes', theme, filename)
                if os.path.isfile(path):
                    setattr(self, attr, pygame.transform.scale(pygame.image.load(path), (self.width, self.height)))
                    break
        # Derive lighting surfaces once per scene load, preserving exact artwork.
        self.lighting_night = self.bg_night
        if self.lighting_night is None and self.bg_day is not None:
            self.lighting_night = self.bg_day.copy()
            tint = (80, 100, 145) if theme == 'resort_beach' else (140, 145, 180)
            self.lighting_night.fill(tint, special_flags=pygame.BLEND_RGB_MULT)
            # Outdoor openings need deeper night colour than the lit interiors.
            openings = {
                'video_store': [[(0, 0), (101, 39), (101, 533), (0, 656)]],
                'apartment': [
                    [(563, 32), (646, 33), (645, 98), (564, 97)],
                    [(665, 32), (747, 30), (747, 97), (665, 97)],
                    [(564, 105), (645, 105), (645, 163), (564, 163)],
                    [(665, 105), (746, 104), (746, 162), (665, 164)],
                    [(564, 172), (645, 172), (645, 229), (563, 229)],
                    [(665, 172), (746, 171), (746, 229), (665, 230)],
                    [(1137, 26), (1279, 0), (1279, 407), (1138, 382)],
                ],
            }.get(theme, [])
            if openings:
                mask = pygame.Surface((self.width, self.height))
                mask.fill((255, 255, 255))
                for outline in openings:
                    pygame.draw.polygon(mask, (65, 85, 145), outline)
                self.lighting_night.blit(mask, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    def request_scene_travel(self, destination, standby=False):
        if self.is_sleeping and not standby:
            raise ValueError('Wake the screen before travelling')
        if getattr(self, 'scene_journey', None):
            raise ValueError('A scene journey is already in progress')
        sync_scene(self.cfg)
        route = self.scene_travel_route(destination)
        self.scene_journey = route
        self.journey_arriving = False
        if route:
            self.target_next_portal()
        return len(route)

    def scene_travel_route(self, destination):
        start = scene_id(self.cfg)
        def reachable(room, arrival, departure):
            scene = self.cfg['scenes'][room]
            nav = FloorNavigation(scene['walkable_trapezoid'], scene.get('obstacles', []))
            source = portal(self.cfg, {'scene': room, 'portal': arrival}) if arrival else None
            target = portal(self.cfg, {'scene': room, 'portal': departure})
            a = (source.get('inside_x',source['x']), source.get('inside_y',source['y']+45)) if source else (self.char_x, self.char_y)
            b = (target.get('inside_x',target['x']), target.get('inside_y',target['y']+45))
            return nav.clear(b,(target['x'],target['y'])) and nav.free(a) and bool(nav.route(a, b))
        # Exclude invalid arrival paths before BFS, so a broken shortcut does not
        # prevent using another valid connection to the destination.
        def valid_endpoint(endpoint):
            scene = self.cfg['scenes'].get(endpoint.get('scene'))
            p = portal(self.cfg, endpoint)
            if not scene or not p:
                return False
            nav = FloorNavigation(scene['walkable_trapezoid'], scene.get('obstacles', []))
            return nav.clear((p['x'], p['y']), (p.get('inside_x', p['x']), p.get('inside_y', p['y']+45)))
        routable = dict(self.cfg, scene_links=[link for link in self.cfg.get('scene_links', [])
                            if valid_endpoint(link['a']) and valid_endpoint(link['b'])])
        route = find_route(routable, start, destination, reachable)
        # Validate the arrival end of every link as well, including the final scene.
        for step in route:
            scene = self.cfg['scenes'][step['to']['scene']]
            p = portal(self.cfg, step['to'])
            if not FloorNavigation(scene['walkable_trapezoid'], scene.get('obstacles', [])).clear((p['x'], p['y']), (p.get('inside_x',p['x']),p.get('inside_y',p['y']+45))):
                raise ValueError('An entry path leaves walkable floor or crosses a block')
        return route

    def target_next_portal(self):
        p = portal(self.cfg, self.scene_journey[0]['from'])
        self.target_x, self.target_y = p.get('inside_x',p['x']), p.get('inside_y',p['y']+45)
        self.journey_exiting = False
        self.target_animation = 'idle'
        self.target_spot_id = None
        self.target_playback_override = None
        self.target_facing_left = None
        self.pending_popup_modal = None
        self._route_goal = None

    def advance_scene_journey(self):
        if getattr(self, 'journey_arriving', False):
            self.journey_arriving = False
            if self.scene_journey:
                self.target_next_portal()
            else:
                self.wander_timer = 3
                if getattr(self, 'pending_idle_destination', None):
                    choice, sleeping = self.pending_idle_destination
                    self.pending_idle_destination = None
                    self.apply_cycle_choice(choice, sleeping)
                elif getattr(self, 'pending_post_travel_action', None):
                    act_args = self.pending_post_travel_action
                    self.pending_post_travel_action = None
                    self.trigger_action(*act_args)
            return True
        if not getattr(self, 'scene_journey', None):
            return False
        expected = portal(self.cfg, self.scene_journey[0]['from'])
        if not getattr(self, 'journey_exiting', False):
            inside = (expected.get('inside_x',expected['x']),expected.get('inside_y',expected['y']+45))
            if math.dist((self.char_x,self.char_y),inside) > 1:
                self.scene_journey = []
                self.travel_error = 'Journey interrupted before reaching the entry path'
                return False
            self.target_x, self.target_y = expected['x'], expected['y']
            self._route_goal = None
            self.journey_exiting = True
            return True
        if math.dist((self.char_x,self.char_y),(expected['x'],expected['y'])) > 1:
            self.scene_journey = []
            self.travel_error = 'Journey interrupted before reaching the exit'
            return False
        step = self.scene_journey.pop(0)
        p = portal(self.cfg, step['to'])
        sync_scene(self.cfg)
        activate_scene(self.cfg, step['to']['scene'])
        self.trap = self.cfg['walkable_trapezoid']
        self.obstacles = self.cfg['obstacles']
        self.props = self.cfg['props']
        self.active_prop_overlays = {}
        self.load_scene_backgrounds()
        self.char_x, self.char_y = p['x'], p['y']
        # Walk inward after crossing the threshold; editors can place the landing point.
        self.target_x, self.target_y = self.clamp_to_walkable(p.get('inside_x', p['x']), p.get('inside_y', p['y']+45))
        self._route_goal = None
        self.journey_arriving = True
        self.current_anim = 'walk'
        self.gesture_role = None
        self.save_walkbox_config()
        return True

    def apply_remote_config(self, new_cfg):
        """Hot-reload room configuration pushed from Web Studio."""
        if getattr(self, 'preview_bridge', None) and threading.get_ident() != self._display_thread:
            return self.preview_bridge.call(lambda: self.apply_remote_config(new_cfg))
        for trap in [new_cfg.get('walkable_trapezoid', {})] + [room.get('walkable_trapezoid', {}) for room in new_cfg.get('scenes', {}).values()]:
            if 'points' in trap and not valid_floor_points(trap['points']):
                raise ValueError('Floor must be a convex polygon with 3–32 distinct points')
        previous_scene = scene_id(self.cfg)
        merged = dict(self.cfg, **new_cfg)
        from sensor_events import ensure_sensor_source
        ensure_sensor_source(merged)
        from weather_source import ensure_weather_source
        ensure_weather_source(merged)
        from weather_source import validate_weather
        validate_weather(merged)
        old_background = self.cfg.get('scenes', {}).get(previous_scene, {})
        new_background = merged.get('scenes', {}).get(scene_id(merged), {})
        backgrounds_changed = scene_id(merged) != previous_scene or any(
            old_background.get(key) != new_background.get(key)
            for key in ('theme', 'background', 'background_night'))
        validate_lighting(merged.get('lighting', {}))
        health_settings(merged.get('system_health'))
        from morning_greeting import settings as morning_settings
        morning_settings(merged.get('morning_greeting'))
        navigation_changed = (
            scene_id(merged) != previous_scene
            or merged.get('walkable_trapezoid') != self.cfg.get('walkable_trapezoid')
            or [obstacle_points(o) for o in merged.get('obstacles', [])]
               != [obstacle_points(o) for o in self.cfg.get('obstacles', [])]
            or merged.get('scene_links') != self.cfg.get('scene_links')
        )
        from prop_runtime import validate_prop_config
        validate_prop_config(merged)
        if merged.get('scenes', {}).get(scene_id(merged), {}).get('enabled', True) is False:
            raise ValueError('Enable the selected scene or switch to an enabled scene before saving')
        if merged.get('scenes') and not any(s.get('enabled', True) for s in merged['scenes'].values()):
            raise ValueError('Keep at least one scene enabled')
        # Validate/load first; a rejected sequence must not replace saved settings.
        previous_walk = (self.walk_frames, self.walk_fps, self.walk_ping_pong)
        try:
            self.configure_character(merged)
        except Exception:
            self.walk_frames, self.walk_fps, self.walk_ping_pong = previous_walk
            raise
        self.cfg.update(new_cfg)
        if "walkable_trapezoid" in new_cfg:
            self.trap = new_cfg["walkable_trapezoid"]
            self.cfg["walkable_trapezoid"] = self.trap
        if "obstacles" in new_cfg:
            self.obstacles = new_cfg["obstacles"]
            self.cfg["obstacles"] = self.obstacles
        if "props" in new_cfg:
            self.props = new_cfg["props"]
            self.cfg["props"] = self.props
        if "event_mappings" in new_cfg:
            self.event_mappings = new_cfg["event_mappings"]
            self.cfg["event_mappings"] = self.event_mappings
        if "switches" in new_cfg:
            self.switches = new_cfg["switches"]
        if "apps" in new_cfg:
            self.apps = new_cfg["apps"]
            self.cfg["apps"] = self.apps
        if "ui_font_scale" in new_cfg:
            self._init_fonts(new_cfg["ui_font_scale"])
            self.cfg["ui_font_scale"] = self.ui_font_scale
        if "on_screen_buttons" in new_cfg:
            self.set_on_screen_buttons_mode(new_cfg["on_screen_buttons"])
        if "palette" in new_cfg:
            self.palette = {k: tuple(v) for k, v in self.cfg["palette"].items()}
        ensure_world(self.cfg)
        sync_scene(self.cfg)
        if navigation_changed:
            self.scene_journey = []
            self.journey_arriving = False
        if backgrounds_changed:
            self.load_scene_backgrounds()
        if scene_id(self.cfg) != previous_scene:
            self.active_rest_role = None
            self.rest_transition = None
            self.gesture_role = None
            self.target_animation = 'idle'
            self.current_anim = 'idle'
            self.target_spot_id = None
            self.active_prop_overlays = {}
            self.char_x, self.char_y = self.clamp_to_walkable(self.char_x, self.char_y)
        self.save_walkbox_config()
        if navigation_changed:
            self.target_x, self.target_y = self.clamp_to_walkable(self.char_x, self.char_y)
            self.status_msg = "Room configuration hot-reloaded from Web Studio"
        print("[HTTP] Hot-reloaded room geometry & mappings from Web Studio successfully!")

    def apply_theme(self, theme_data_or_id):
        """Hot-reload theme (palette, active scene, character, visual props) cleanly without restarting companion services."""
        if getattr(self, 'preview_bridge', None) and threading.get_ident() != self._display_thread:
            return self.preview_bridge.call(lambda: self.apply_theme(theme_data_or_id))
        from theme_manager import apply_theme_to_config, get_theme
        if isinstance(theme_data_or_id, str):
            theme = get_theme(theme_data_or_id)
        else:
            theme = theme_data_or_id

        apply_theme_to_config(theme, self.cfg)

        # Wake display on theme switch
        self.is_sleeping = False
        if hasattr(self, 'display_power') and self.display_power:
            self.display_power.set_sleeping(False)

        # Update runtime palette
        if "palette" in self.cfg:
            self.palette = {k: tuple(v) for k, v in self.cfg["palette"].items()}

        # Re-initialize scene world & sync
        ensure_world(self.cfg)
        sync_scene(self.cfg)

        # Reload scene backgrounds
        self.load_scene_backgrounds()

        # Reload character & sequences
        try:
            self.configure_character(self.cfg)
        except Exception as e:
            print(f"[WARN] Error reconfiguring character for theme: {e}")

        # Update runtime floor, obstacles, props for the active scene
        self.trap = copy.deepcopy(self.cfg.get("walkable_trapezoid", self.trap))
        self.obstacles = copy.deepcopy(self.cfg.get("obstacles", self.obstacles))
        self.props = copy.deepcopy(self.cfg.get("props", self.props))
        self.sprite_cache.clear()

        # Reset character stance safely to center of the new scene walkbox
        self.active_rest_role = None
        self.rest_transition = None
        self.gesture_role = None
        self.target_animation = 'idle'
        self.current_anim = 'idle'
        self.target_spot_id = None
        self.active_prop_overlays = {}
        self.scene_journey = []
        self.journey_arriving = False

        self.char_x = float(self.width // 2)
        self.char_y = float((self.trap["y_min"] + self.trap["y_max"]) // 2 + 10)
        self.char_x, self.char_y = self.clamp_to_walkable(self.char_x, self.char_y)
        self.target_x = self.char_x
        self.target_y = self.char_y

        self.save_walkbox_config()
        self.status_msg = f"Theme switched to {theme.get('name', theme.get('id'))}"
        print(f"[THEME] Successfully switched theme to: {theme.get('id')}")
        return {
            "status": "ok",
            "theme": self.cfg.get("theme_profile", self.cfg.get("theme")),
            "active_scene": self.cfg.get("active_scene"),
            "character": self.cfg.get("active_character")
        }


    def trigger_action(self, action_cfg, app_name="APP", color=(0, 229, 255), summary="", ticker=None, badge=None):
        """Executes an action: walks to target point, faces configured direction, plays animation, triggers prop overlay, and triggers bubble or modal."""
        if getattr(self, 'scene_journey', None) or getattr(self, 'journey_arriving', False):
            return
        if getattr(self, 'is_sleeping', False):
            return  # Keep receiving telemetry, but do not interrupt standby.

        self.idle_waiting = False
        self.pending_idle_destination = None
        # Inter-scene traversal: if the action targets a different scene, travel there first!
        target_scene = None if action_cfg.get('target_mode') == 'current' else action_cfg.get("scene") or action_cfg.get("target_scene")
        curr_scene = scene_id(self.cfg)
        if target_scene and self.cfg.get('scenes', {}).get(target_scene, {}).get('enabled', True) is False:
            raise ValueError('Activity received for disabled scene: ' + target_scene)
        if target_scene and target_scene != curr_scene:
            try:
                self.pending_post_travel_action = (action_cfg, app_name, color, summary, ticker, badge)
                self.request_scene_travel(target_scene)
                self.status_msg = f"Heading to {target_scene.replace('_', ' ').title()} for {app_name}..."
                return
            except Exception as e:
                print(f"[SCENE] Cannot travel to {target_scene}: {e}")
                self.pending_post_travel_action = None
                self.status_msg = 'Cannot reach action scene: ' + str(e)
                raise ValueError(self.status_msg) from e

        if action_cfg.get('target_mode', 'specific') != 'specific':
            nav = self.floor_navigation()
            action_cfg = resolve_action_placement(self.cfg, action_cfg, self.character_sequences,
                current=(self.char_x, self.char_y),
                reachable=lambda spot: nav.free((spot['x'], spot['y'])) and bool(nav.route((self.char_x, self.char_y), (spot['x'], spot['y']))))
            if action_cfg.get('target_mode') == 'current':
                action_cfg.setdefault('facing', 'left' if self.facing_left else 'right')

        requested = self.character_sequences.get(action_cfg.get('animation'), {})
        if requested.get('allowed_scenes') and curr_scene not in requested['allowed_scenes']:
            raise ValueError('This animation is only available in its configured scenes')

        # Resolve interaction spot if specified
        spot_id = action_cfg.get("spot_id")
        spot = None
        if spot_id and "interaction_spots" in self.cfg:
            for s in self.cfg["interaction_spots"]:
                if s.get("id") == spot_id:
                    spot = s
                    break
        if not spot and spot_id and "scenes" in self.cfg and curr_scene in self.cfg["scenes"]:
            for s in self.cfg["scenes"][curr_scene].get("interaction_spots", []):
                if s.get("id") == spot_id:
                    spot = s
                    break

        default_x = spot.get("x", self.char_x) if spot else self.char_x
        default_y = spot.get("y", self.char_y) if spot else self.char_y
        default_facing = spot.get("facing", "left") if spot else "left"
        default_anim = spot.get("animation", "inspect") if spot else "inspect"

        tx = default_x if spot else action_cfg.get("x", default_x)
        ty = default_y if spot else action_cfg.get("y", default_y)
        self.target_x, self.target_y = (tx, ty) if action_cfg.get('target_mode') == 'current' else self.clamp_to_walkable(tx, ty)

        facing_val = action_cfg.get("facing", default_facing)
        self.target_facing_left = (str(facing_val).lower() == "left")
        self.target_animation = action_cfg.get("animation", default_anim)
        self.target_spot_id = spot_id if spot else None
        self.target_playback_override = action_cfg.get("playback_override")
        self.current_anim = "walk"
        self.gesture_role = None

        speech_tmpl = action_cfg.get("speech", "{summary}")
        formatted_speech = speech_tmpl.replace("{summary}", summary).replace("{app_id}", app_name)
        display_mode = action_cfg.get("display_mode", "thought_bubble")

        # --- Prop Overlay Reaction ---
        prop_overlay_cfg = action_cfg.get("prop_overlay")
        if not prop_overlay_cfg and action_cfg.get("target_prop"):
            prop_overlay_cfg = {
                "prop_id": action_cfg.get("target_prop"),
                "effect": action_cfg.get("prop_effect", "pulse_beacon"),
                "badge_template": action_cfg.get("badge_template", "{badge}"),
                "duration": action_cfg.get("prop_duration", 20.0)
            }

        if prop_overlay_cfg and isinstance(prop_overlay_cfg, dict):
            pid = prop_overlay_cfg.get("prop_id")
            effect = prop_overlay_cfg.get("effect", "pulse_beacon")
            badge_tmpl = prop_overlay_cfg.get("badge_template", "{badge}")
            badge_val = badge or action_cfg.get("badge")
            if not badge_val:
                # Synthesize informative badge text from summary if not provided
                if "¢" in summary:
                    for part in summary.split():
                        if "¢" in part:
                            badge_val = part
                            break
                elif "dropped" in summary.lower():
                    badge_val = "DROP!"
                else:
                    badge_val = app_name[:8]
            badge_text = badge_tmpl.replace("{badge}", str(badge_val)).replace("{summary}", str(summary)[:18])
            overlay_col = tuple(prop_overlay_cfg.get("color", color))
            duration = float(prop_overlay_cfg.get("duration", 20.0))
            if pid:
                self.active_prop_overlays[pid] = {
                    "effect": effect,
                    "text": badge_text,
                    "color": overlay_col,
                    "start_time": time.time(),
                    "duration": duration
                }
                print(f"[PROP] Activated prop overlay '{effect}' on '{pid}': {badge_text}")

        if display_mode == "popup_modal":
            dash_cfg = action_cfg.get("dashboard", {}) if isinstance(action_cfg.get("dashboard"), dict) else {}
            modal_layout = action_cfg.get("layout") or action_cfg.get("modal_layout") or ("dashboard" if dash_cfg or action_cfg.get("hero_value") else None)
            modal_data = {
                "title": app_name.upper(),
                "summary": summary or "No telemetry summary available.",
                "ticker": ticker or [],
                "color": color,
                "timestamp": time.strftime("%I:%M %p")
            }
            if modal_layout:
                modal_data["layout"] = modal_layout
            hero_val = action_cfg.get("hero_value") or dash_cfg.get("hero_value")
            if hero_val:
                modal_data["hero_value"] = str(hero_val).replace("{summary}", summary).replace("{badge}", str(badge or ""))
            hero_sub = action_cfg.get("hero_subhead") or dash_cfg.get("hero_subhead")
            if hero_sub:
                modal_data["hero_subhead"] = str(hero_sub).replace("{summary}", summary).replace("{app_id}", app_name)
            dash_badge = action_cfg.get("badge") or dash_cfg.get("badge") or badge
            if dash_badge:
                modal_data["badge"] = str(dash_badge)
            bcol = action_cfg.get("badge_color") or dash_cfg.get("badge_color")
            if bcol:
                modal_data["badge_color"] = bcol
            tiles = action_cfg.get("tiles") or dash_cfg.get("tiles")
            if tiles:
                modal_data["tiles"] = tiles
            if action_cfg.get("slider"):
                modal_data["slider"] = action_cfg["slider"]
            if action_cfg.get("wellness"):
                modal_data["wellness"] = action_cfg["wellness"]
            if action_cfg.get("progression"):
                modal_data["progression"] = action_cfg["progression"]
            if action_cfg.get("morning_data"):
                modal_data["morning_data"] = action_cfg["morning_data"]
            if action_cfg.get('_attention_waiting'):
                action_cfg['_attention_modal_data'] = modal_data
                self.active_popup_modal = None
                self.pending_popup_modal = None
                self.status_msg = f"{action_cfg.get('speech', '{summary}').format(summary=summary)}"
            else:
                dx = self.target_x - self.char_x
                dy = self.target_y - self.char_y
                if (dx**2 + dy**2)**0.5 <= 14.0:
                    self.active_popup_modal = modal_data
                    self.pending_popup_modal = None
                    self.facing_left = self.target_facing_left
                    self.motion_direction = "side"
                    self.is_inspecting = (self.target_animation == "inspect")
                else:
                    self.pending_popup_modal = modal_data
                    self.status_msg = f"Checking {action_cfg.get('label', 'station')}..."
        else:
            self.active_popup_modal = None
            self.pending_popup_modal = None
            self.status_msg = formatted_speech
            dx = self.target_x - self.char_x
            dy = self.target_y - self.char_y
            if (dx**2 + dy**2)**0.5 <= 14.0:
                self.facing_left = self.target_facing_left
                self.motion_direction = "side"
                self.is_inspecting = (self.target_animation == "inspect")

    def request_attention(self, app_id, message, health_seen=None):
        if not hasattr(self, 'integration_attention'):
            self.integration_attention = {}
        self.integration_attention[app_id] = str(message)
        if health_seen is not None:
            if not hasattr(self, 'integration_health_attention'):
                self.integration_health_attention = {}
            self.integration_health_attention[app_id] = str(message)
        self.queue_action({
            'animation': 'wave_arms',
            'x': self.char_x,
            'y': self.char_y,
            'speech': '{summary}',
            'duration_seconds': 6,
            'display_mode': 'popup_modal',
            'attention_until_interaction': True,
            'voice_escalation': True,
            '_source_app_id': app_id,
            '_important': True,
            '_health_seen': health_seen
        }, app_id, summary=message)

    def check_integration_health(self):
        # Throttle: only evaluate health once every 10 seconds
        mono_now = time.monotonic()
        if mono_now < getattr(self, '_next_health_check', 0):
            return
        self._next_health_check = mono_now + 10.0

        # Grace period on startup: allow 90 seconds for all services to complete initial polls
        now = time.time()
        if now - getattr(self, 'integration_started', now) < 90:
            return

        for app in self.apps:
            url = (app.get('source_url') or '').strip()
            # Only check external HTTP/HTTPS services
            if not url.startswith(('http://', 'https://')):
                continue
            if app.get('source_enabled') is not True:
                continue
            if app.get('monitor_health', True) is False:
                continue
            if app.get('built_in'):
                continue

            app_id = app['id']
            tele = self.app_telemetry.get(app_id, {})
            seen = max(tele.get('last_seen', 0), tele.get('last_healthy', 0))
            mark = seen if seen > self.integration_started else self.integration_started
            poll_interval = max(5, int(app.get('poll_seconds', 30)))
            ttl = max(180, float(app.get('stale_after_seconds', tele.get('ttl_seconds', 180))), poll_interval * 5 + 45)

            if tele.get('status') in ('healthy', 'ok') and (now - seen) <= ttl:
                if getattr(self, 'attention_seen', {}).get(app_id) in ('stale', 'outage', 'acknowledged'):
                    self.attention_seen.pop(app_id, None)
                continue

            if now - mark > ttl:
                # Alert once per outage until restored
                if getattr(self, 'attention_seen', {}).get(app_id) not in ('stale', 'outage', 'acknowledged'):
                    if not hasattr(self, 'attention_seen'):
                        self.attention_seen = {}
                    self.attention_seen[app_id] = 'outage'
                    app_name = app.get('name', app_id)
                    if not seen or seen <= self.integration_started:
                        msg = f"{app_name} cannot be reached."
                    else:
                        mins = int((now - seen) // 60)
                        if mins < 1:
                            msg = f"{app_name} stopped responding ({int(now - seen)}s ago)."
                        else:
                            msg = f"{app_name} stopped responding ({mins}m ago)."
                    self.request_attention(app_id, msg, health_seen=mark)

    def audit_activity(self, event, **fields):
        path = getattr(self, 'activity_history_path', None)
        if not path:
            return
        from activity_history import append
        try:
            append(path, event, scene=scene_id(self.cfg), x=round(getattr(self, 'char_x', 0), 1),
                   y=round(getattr(self, 'char_y', 0), 1), **fields)
        except (OSError, ValueError) as error:
            print('[History] Could not record activity:', error)

    def queue_action(self, action, app_name='APP', color=(0, 229, 255), summary='', ticker=None, badge=None, source_event=None, priority=False):
        import uuid
        source_app = next((a for a in getattr(self, 'apps', []) if a.get('id') == action.get('_source_app_id') or a.get('name') == app_name), {})
        action = dict(action, _activity_id=uuid.uuid4().hex, _received_at=time.time(),
                      _sleep_max_age_seconds=source_app.get('sleep_max_age_seconds', 900))
        if source_app.get('built_in') == 'sensors':
            action.update(_sensor_event=True, hide_label=action.get('hide_label', True))
        if source_event:
            action = dict(action, source_event=source_event)
        if action.get('_sensor_event') and action.get('target_mode') == 'current' and str(source_event or action.get('event','')).startswith(('tilt_','shake')):
            from sensor_reaction import begin
            if begin(self, action):
                return
            return  # Protected popups/rest/attention do not accumulate motion reactions.
        if (action.get('attention_until_interaction') or action.get('attention_needed')) and not priority:
            action.update(_attention_waiting=True, _important=True, attention_until_interaction=True, voice_escalation=action.get('voice_escalation', True))
            if not action.get('animation') or action.get('animation') in ('idle', 'inspect', 'notebook_write', 'lean_globe'):
                action['animation'] = 'wave_arms'
            mgr = getattr(self, 'attention_voice_manager', None)
            if mgr and mgr.should_defer_for_absence(self, action):
                mgr.defer_alert(self, (action, app_name, color, summary, ticker, badge))
                return
        queue = getattr(self, 'activity_queue', None)
        if queue is not None:
            if priority:
                action.update(_button_action=True, _hold_popup_until_dismissed=action.get('display_mode') == 'popup_modal')
                queue.enqueue_priority(self, (action, app_name, color, summary, ticker, badge))
            else:
                queue.enqueue((action, app_name, color, summary, ticker, badge), self)
            self.audit_activity('queued', activity_id=action['_activity_id'], app=app_name,
                source_event=source_event or action.get('event'), action=action.get('id'),
                requested_scene=action.get('scene') or action.get('target_scene'), animation=action.get('animation'),
                spot_id=action.get('spot_id'), waiting=len(queue.items))
        else:
            self.trigger_action(action, app_name, color, summary, ticker, badge)

    def persist_telemetry(self):
        from integration_state import save_telemetry
        path = getattr(self, 'telemetry_path', None)
        if path:
            try:
                save_telemetry(path, self.app_telemetry)
            except OSError as error:
                print('[Telemetry] Could not persist received state:', error)

    def receive_telemetry_event(self, event):
        """Receive external telemetry event push and map to animations/hotspots."""
        app_id = event.get("app_id", "unknown")
        event_name = event.get("event", "")
        previous = getattr(self, 'app_telemetry', {}).get(app_id, {}).get('received_events', {}).get(event_name, {}).get('data')
        from integration_state import suppress_successive_duplicate
        source_app = next((a for a in self.apps if a.get('id') == app_id), {})
        duplicate = not isinstance(event.get('action'), dict) and suppress_successive_duplicate(source_app, event_name or 'event', previous, event)
        suppressed = not isinstance(event.get('action'), dict) and source_app.get('suppressed_events', {}).get(event_name or 'event') is True
        summary = event.get("summary") or event.get("message") or f"{event_name} event received"
        badge = event.get("badge")
        self.audit_activity('received', app_id=app_id, source_event=event_name or 'event',
            summary=str(summary)[:500], duplicate_suppressed=duplicate, event_suppressed=suppressed)
        event_dash = {k: event[k] for k in ('layout', 'hero_value', 'hero_subhead', 'badge_color', 'tiles') if k in event}
        queue_received = lambda action, *args, **kwargs: self.queue_action(dict(action, _source_app_id=app_id, _important=bool(event.get('attention_needed') or event.get('severity') in ('high', 'critical', 'error')), **event_dash), *args, **kwargs, source_event=event_name or "event")
        print(f"[EVENT] Received event from {app_id} ({event_name}): {summary}")
        
        if app_id not in self.app_telemetry:
            self.app_telemetry[app_id] = {}
        self.app_telemetry[app_id]["status"] = event.get("status", self.app_telemetry[app_id].get("status", "healthy"))
        self.app_telemetry[app_id]["summary"] = summary
        self.app_telemetry[app_id]["last_seen"] = time.time()
        self.app_telemetry[app_id]["data"] = event
        self.app_telemetry[app_id]["ttl_seconds"] = event.get("ttl_seconds", self.app_telemetry[app_id].get("ttl_seconds", 300))
        from integration_state import record_received
        record_received(self.app_telemetry[app_id], event_name or 'event', event, suppression='event' if suppressed else 'duplicate' if duplicate else None)
        self.persist_telemetry()
        if duplicate or suppressed:
            return

        # 0. Direct action execution (e.g. from Web Studio pose stager test)
        if "action" in event and isinstance(event["action"], dict):
            act = event["action"]
            col = tuple(event.get("color", [240, 160, 80]))
            queue_received(act, event.get("app_name", "STUDIO"), col, summary)
            return

        # 1. First check structured apps actions
        app_cfg = next((a for a in self.apps if a["id"] == app_id), None)
        if app_cfg:
            from integration_state import conditions_match
            actions = [a for a in app_cfg.get('actions', []) if (a.get('event') in [event_name, '*'] or a.get('id') == event_name) and conditions_match(a, event)]
            actions.sort(key=lambda a: (len(a.get('conditions', [])), a.get('event') != '*'), reverse=True)
            act = actions[0] if actions else None
            if act:
                col = tuple(app_cfg.get("color", [0, 229, 255]))
                ticker = self.app_telemetry[app_id].get("ticker", [])
                is_attn = bool(act.get('attention_needed') or event.get('attention_needed') or act.get('attention_until_interaction') or event.get('severity') in ('high', 'critical', 'error'))
                if is_attn:
                    act = dict(act, attention_needed=True, attention_until_interaction=True, voice_escalation=True, animation='wave_arms', display_mode='popup_modal')
                queue_received(act, app_cfg.get("name", app_id), col, summary, ticker, badge=badge)
                return

            if app_cfg.get('built_in') in ('sensors','weather'):
                return  # Unmapped sensor events are observations, not generic actions.

        if event.get('attention_needed') or event.get('severity') in ('high', 'critical', 'error'):
            self.request_attention(app_id, summary)
            return


        for mapping in self.event_mappings:
            if mapping.get('app_id') == app_id and mapping.get('event') in (event_name, '*'):
                queue_received({'target_prop': mapping.get('target_prop'), 'animation': mapping.get('animation', 'inspect'), 'speech': mapping.get('speech', '{summary}'), 'duration_seconds': mapping.get('duration_seconds', 8)}, app_id, summary=summary)
                return

        if app_cfg:
            from integration_state import normal_update_action
            fallback = normal_update_action(app_cfg)
            if fallback and conditions_match(fallback, event):
                queue_received(fallback, app_cfg.get('name', app_id), tuple(app_cfg.get('color', [0, 229, 255])), summary, badge=badge)
                return

        self.status_msg = f"[{app_id.upper()}] {summary}"
        self.is_inspecting = True

    def receive_heartbeat(self, hb):
        """Receive external application heartbeat."""
        app_id = hb.get("app_id", "unknown")
        previous = getattr(self, 'app_telemetry', {}).get(app_id, {}).get('received_events', {}).get('heartbeat', {}).get('data')
        from integration_state import suppress_successive_duplicate
        source_app = next((a for a in self.apps if a.get('id') == app_id), {})
        duplicate = suppress_successive_duplicate(source_app, 'heartbeat', previous, hb)
        suppressed = source_app.get('suppressed_events', {}).get('heartbeat') is True
        status = hb.get("status", "healthy")
        activity = hb.get("activity", "Idle")
        summary = hb.get("summary") or activity
        has_error = status in ('error', 'warning', 'offline') or bool(hb.get('refresh_error'))
        queue_received = lambda action, *args, **kwargs: self.queue_action(dict(action, _source_app_id=app_id, _important=has_error or bool(hb.get('attention_needed'))), *args, **kwargs, source_event="heartbeat")
        self.audit_activity('received', app_id=app_id, source_event='heartbeat',
            status=status, summary=str(summary)[:500], duplicate_suppressed=duplicate, event_suppressed=suppressed)
        ticker = hb.get("ticker", [])

        if app_id not in self.app_telemetry:
            self.app_telemetry[app_id] = {}
        tele_update = {
            "status": status,
            "activity": activity,
            "summary": summary,
            "ticker": ticker,
            "ttl_seconds": hb.get("ttl_seconds", 300),
            "data": hb
        }
        if not has_error:
            tele_update["last_seen"] = time.time()
            tele_update["last_healthy"] = time.time()
            tele_update["refresh_error"] = None
        else:
            tele_update["last_attempt"] = time.time()
            if hb.get('refresh_error'):
                tele_update["refresh_error"] = str(hb.get('refresh_error'))

        self.app_telemetry[app_id].update(tele_update)
        from integration_state import record_received
        record_received(self.app_telemetry[app_id], 'heartbeat', hb, suppression='event' if (suppressed and not has_error) else 'duplicate' if (duplicate and not has_error) else None)
        self.persist_telemetry()

        # Service outage / error alert: NEVER swallowed by routine heartbeat suppression!
        if has_error:
            if status in ('offline', 'error'):
                if getattr(self, 'attention_seen', {}).get(app_id) not in ('stale', 'outage', 'acknowledged'):
                    if not hasattr(self, 'attention_seen'):
                        self.attention_seen = {}
                    self.attention_seen[app_id] = 'outage'
                    self.request_attention(app_id, summary)
            return

        # Healthy recovery: clear any lingering error/outage attention
        if getattr(self, 'attention_seen', {}).get(app_id):
            self.attention_seen.pop(app_id, None)
        health_message = getattr(self, 'integration_health_attention', {}).pop(app_id, None)
        if health_message and getattr(self, 'integration_attention', {}).get(app_id) == health_message:
            self.integration_attention.pop(app_id, None)
        elif getattr(self, 'integration_attention', {}).get(app_id) and getattr(self, 'integration_attention', {}).get(app_id) == summary:
            self.integration_attention.pop(app_id, None)

        # Purge any queued, deferred, or active outage alerts for this healthy app
        if hasattr(self, 'activity_queue') and self.activity_queue:
            self.activity_queue.purge_app_alerts(self, app_id)
        mgr = getattr(self, 'attention_voice_manager', None)
        if mgr:
            mgr.purge_deferred_alerts(app_id)

        # For normal healthy heartbeats: suppress animations if configured or duplicate
        if duplicate or suppressed:
            return

        from integration_state import conditions_match
        app_cfg = next((a for a in self.apps if a['id'] == app_id), None)
        if app_cfg:
            event_name = hb.get('event', status)
            matches = [a for a in app_cfg.get('actions', []) if a.get('event') in (event_name, '*', 'heartbeat') and conditions_match(a, hb)]
            matches.sort(key=lambda a: (len(a.get('conditions', [])), a.get('event') != '*'), reverse=True)
            if matches:
                act = matches[0]
                queue_received(act, app_cfg.get('name', app_id), tuple(app_cfg.get('color', [0, 229, 255])), summary, ticker)
                if act.get('attention_needed'):
                    self.request_attention(app_id, summary)
                return


        if status == 'busy':
            for mapping in self.event_mappings:
                if mapping.get('app_id') == app_id and mapping.get('event') == 'busy':
                    queue_received({'target_prop': mapping.get('target_prop'), 'animation': mapping.get('animation', 'inspect'), 'speech': mapping.get('speech', '{summary}'), 'duration_seconds': 8}, app_id, summary=summary)
                    return

        if app_cfg:
            if status in ('healthy', 'busy', 'idle', 'online', 'ok'):
                from integration_state import normal_update_action
                act = normal_update_action(app_cfg)
                if act and conditions_match(act, hb):
                    queue_received(act, app_cfg.get('name', app_id), tuple(app_cfg.get('color', [0, 229, 255])), summary, ticker)
                    return

    def _init_gpio(self):
        from optional_hardware import monitor_for
        from gpio_hardware import ButtonController
        monitor = monitor_for(self, os.path.join(os.path.dirname(get_active_config_path()), 'hardware_settings.json'))
        if not hasattr(self, 'button_controller'):
            use_gpio = GPIO_AVAILABLE and not self.local_preview and not getattr(self, 'desktop_mode', False)
            self.button_controller = ButtonController(Button if use_gpio else None, self.on_switch_pressed, self.perform_shutdown)
        self.button_controller.configure(monitor.config['buttons'], self.switches)
        self.gpio_buttons = self.button_controller.devices

    def update_gpio_settings(self):
        if not getattr(self, '_gpio_reconfigure_pending', False):return
        self._gpio_reconfigure_pending = False
        self._init_gpio()
        for row in self.button_controller.rows:
            if not any(s['id']==row['id'] for s in self.switches):
                self.switches.append(dict(row,app_id='',color=[155,171,178]))
        self.cfg['switches'] = self.switches
        self.save_walkbox_config()

    def save_walkbox_config(self):
        self.cfg["walkable_trapezoid"] = self.trap
        self.cfg["obstacles"] = self.obstacles
        self.cfg["props"] = self.props
        self.cfg["event_mappings"] = self.event_mappings
        self.cfg["apps"] = self.apps
        self.cfg["ui_font_scale"] = self.ui_font_scale
        self.cfg["on_screen_buttons"] = self.quick_keys_mode
        sync_scene(self.cfg)
        for p in _config_save_paths(self.local_preview):
            try:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(self.cfg, f, indent=2)
                print(f"Saved calibrated walkbox & obstacles to {p}")
            except Exception as e:
                print(f"[WARN] Could not save config to {p}: {e}")
        self.sprite_cache.clear()
        self.save_feedback_timer = 2.5

    def set_on_screen_buttons_mode(self, mode):
        valid = ("on_press", "always", "never")
        if mode not in valid:
            mode = "on_press"
        self.quick_keys_mode = mode
        self.cfg["on_screen_buttons"] = mode
        if mode == "always":
            self.show_quick_keys = True
            self.keys_pinned = True
            self.keys_dismiss_timer = 0.0
        elif mode == "never":
            self.show_quick_keys = False
            self.keys_pinned = False
            self.keys_dismiss_timer = 0.0
        else:
            self.keys_pinned = False
            self.show_quick_keys = False
            self.keys_dismiss_timer = 0.0

    def is_in_obstacle(self, x, y):
        return any(point_in_polygon((x, y), obstacle_points(obs)) for obs in self.obstacles)

    def floor_navigation(self):
        signature = json.dumps([self.trap, self.obstacles], sort_keys=True)
        if getattr(self, '_floor_signature', None) != signature:
            self._floor_signature = signature
            self._floor_navigation = FloorNavigation(self.trap, self.obstacles)
            self._route_goal = None
        return self._floor_navigation

    def clamp_to_walkable(self, x, y):
        nearest = self.floor_navigation().nearest((float(x), float(y)))
        return nearest if nearest is not None else (self.char_x, self.char_y)

    def pick_random_wander_point(self):
        rand_x = float(self.width // 2)
        rand_y = float((self.trap["y_min"] + self.trap["y_max"]) // 2)
        for _ in range(16):
            rand_y = random.uniform(self.trap["y_min"] + 15, self.trap["y_max"] - 15)
            t = (rand_y - self.trap["y_min"]) / max(1.0, (self.trap["y_max"] - self.trap["y_min"]))
            x_min = self.trap["back_x_min"] + t * (self.trap["front_x_min"] - self.trap["back_x_min"]) + 25
            x_max = self.trap["back_x_max"] + t * (self.trap["front_x_max"] - self.trap["back_x_max"]) - 25
            if x_max > x_min:
                rand_x = random.uniform(x_min, x_max)
            if not self.is_in_obstacle(rand_x, rand_y):
                return (rand_x, rand_y)
        return self.clamp_to_walkable(rand_x, rand_y)

    def rest_role_ready(self, role):
        sequences = getattr(self, 'character_sequences', {})
        sequence = sequences.get(role)
        return bool(sequence and all(sequence.get(key) in sequences for key in ('entry_transition', 'exit_transition')))

    def idle_role_allowed(self, role):
        if role == 'sleeping':
            return False
        if ('idle_side' if role == 'idle' else role) in self.mapped_animation_roles():
            return False
        sequence = getattr(self, 'character_sequences', {}).get('idle_side' if role == 'idle' else role)
        if not sequence or sequence.get('transition_only') or not sequence.get('idle_eligible', role.startswith('idle')):
            return False
        if sequence.get('allowed_scenes') and scene_id(self.cfg) not in sequence['allowed_scenes']:
            return False
        return not (sequence.get('entry_transition') or sequence.get('exit_transition')) or self.rest_role_ready(role)

    def choose_idle_spots(self):
        choices = []
        for spot in self.cfg.get('interaction_spots', []):
            roles = list(dict.fromkeys([spot.get('animation')] + spot.get('animations', [])))
            for role in roles:
                if role and self.idle_role_allowed(role):
                    rule = self.cfg.get('pose_rules', {}).get(role, {})
                    if 'valid_spots' in rule and spot.get('id') not in rule['valid_spots']:
                        continue
                    choices.append((spot, role))
        return choices

    def choose_standby_spots(self):
        candidates = []
        for role, sequence in self.character_sequences.items():
            if sequence.get('transition_only') or not sequence.get('standby_eligible', role in ('sleeping','sitting_rest','seated_back','deck_chair_rest')):
                continue
            if (sequence.get('entry_transition') or sequence.get('exit_transition')) and not self.rest_role_ready(role):
                continue
            if sequence.get('allowed_scenes') and scene_id(self.cfg) not in sequence['allowed_scenes']:
                continue
            rule = self.cfg.get('pose_rules', {}).get(role, {})
            for spot in self.cfg.get('interaction_spots', []):
                if role not in [spot.get('animation')] + spot.get('animations', []):
                    continue
                if 'valid_spots' in rule and spot.get('id') not in rule['valid_spots']:
                    continue
                nav = self.floor_navigation()
                if nav.free((spot['x'], spot['y'])) and nav.route((self.char_x, self.char_y), (spot['x'], spot['y'])):
                    candidates.append((spot, role))
        return candidates

    def integration_mapping_status(self):
        """Read-only validation using the same floor and scene routes as playback."""
        probe = DeskPalApp.__new__(DeskPalApp)
        probe.cfg = copy.deepcopy(self.cfg)
        probe.char_x, probe.char_y = self.char_x, self.char_y
        sequences = dict(self.character_sequences)
        routes, result = {}, {}
        for app in probe.cfg.get('apps', []):
            statuses = result.setdefault(app['id'], {})
            for action in app.get('actions', []):
                signature = [action.get(k) for k in ('scene','target_scene','animation','spot_id','target_mode','x','y')]
                status = {'signature': signature, 'ok': False, 'placement_count': 0}
                statuses[action['id']] = status
                sid = scene_id(probe.cfg) if action.get('target_mode') == 'current' else action.get('scene') or action.get('target_scene') or scene_id(probe.cfg)
                status['scene'] = sid
                try:
                    room = probe.cfg.get('scenes', {}).get(sid)
                    if not room:
                        raise ValueError('Scene is missing')
                    if room.get('enabled', True) is False:
                        raise ValueError('Scene is disabled')
                    if sid not in routes:
                        try:
                            if sid == scene_id(probe.cfg):
                                start = (probe.char_x, probe.char_y)
                            else:
                                steps = probe.scene_travel_route(sid)
                                landing = portal(probe.cfg, steps[-1]['to'])
                                start = (landing.get('inside_x', landing['x']), landing.get('inside_y', landing['y']+45))
                            routes[sid] = (FloorNavigation(room['walkable_trapezoid'], room.get('obstacles', [])), start)
                        except ValueError:
                            routes[sid] = None
                    if routes[sid] is None:
                        raise ValueError('No walkable scene connection from the character')
                    nav, start = routes[sid]
                    cfg = dict(probe.cfg, **room, active_scene=sid)
                    resolved = resolve_action_placement(cfg, action, sequences,
                        current=start,
                        reachable=lambda spot: nav.free((spot['x'],spot['y'])) and bool(nav.route(start,(spot['x'],spot['y']))))
                    role = resolved.get('animation', 'idle')
                    sequence = sequences.get('idle_side' if role == 'idle' else role)
                    if not sequence:
                        raise ValueError('Character animation is missing')
                    if sequence.get('allowed_scenes') and sid not in sequence['allowed_scenes']:
                        raise ValueError('Animation is not allowed in this scene')
                    spot = next((s for s in room.get('interaction_spots', []) if s.get('id') == resolved.get('spot_id')), None)
                    if resolved.get('spot_id') and not spot:
                        raise ValueError('Saved placement is missing')
                    point = (spot['x'],spot['y']) if spot else (resolved.get('x',start[0]),resolved.get('y',start[1]))
                    if action.get('target_mode') != 'current' and not nav.free(point):
                        raise ValueError('Placement is outside the floor or inside a block')
                    if action.get('target_mode') != 'current' and not nav.route(start,point):
                        raise ValueError('No walkable route to the placement')
                    status.update(ok=True, placement_count=1, reason='Reachable from the character')
                except (ValueError, KeyError, IndexError, TypeError) as error:
                    status['reason'] = str(error)
        return result

    def mapped_animation_roles(self):
        """Configured application reactions are reserved, even when suppressed."""
        roles = set()
        actions = [action for app in self.cfg.get('apps', []) for action in app.get('actions', [])]
        actions += self.cfg.get('event_mappings', [])
        for action in actions:
            mode = action.get('target_mode', 'specific')
            if mode == 'current':
                continue
            if mode not in ('any', 'location'):
                role = action.get('animation')
                if role:
                    roles.add('idle_side' if role == 'idle' else role)
                continue
            for sid, scene in self.cfg.get('scenes', {}).items():
                destination = action.get('scene') or action.get('target_scene')
                if destination and destination != sid:
                    continue
                for spot in scene.get('interaction_spots', []):
                    if mode == 'location' and spot.get('id') != action.get('spot_id'):
                        continue
                    for role in [spot.get('animation')] + spot.get('animations', []):
                        if role:
                            roles.add('idle_side' if role == 'idle' else role)
        return roles

    def cycle_choices(self):
        """Stable world order; eligibility is kept separate from reachability."""
        choices = []
        mapped = self.mapped_animation_roles()
        for sid, scene in self.cfg.get('scenes', {}).items():
            if scene.get('enabled', True) is False:
                continue
            for spot in scene.get('interaction_spots', []):
                for role in dict.fromkeys([spot.get('animation')] + spot.get('animations', [])):
                    sequence = self.character_sequences.get(role, {})
                    if not sequence or sequence.get('transition_only'):
                        continue
                    if sequence.get('allowed_scenes') and sid not in sequence['allowed_scenes']:
                        continue
                    if (sequence.get('entry_transition') or sequence.get('exit_transition')) and not self.rest_role_ready(role):
                        continue
                    rule = scene.get('pose_rules', {}).get(role, {})
                    if 'valid_spots' in rule and spot.get('id') not in rule['valid_spots']:
                        continue
                    idle = sequence.get('idle_eligible', role.startswith('idle')) and role != 'sleeping' and ('idle_side' if role == 'idle' else role) not in mapped
                    sleep = sequence.get('standby_eligible', role in ('sleeping','sitting_rest','seated_back','deck_chair_rest'))
                    if idle or sleep:
                        choices.append((sid, spot, role, bool(idle), bool(sleep)))
        return choices

    def cycle_choice_reachable(self, choice):
        sid, spot, role, idle, sleep = choice
        point = (spot['x'], spot['y']) if spot else None
        if sid == scene_id(self.cfg):
            return point is None or (self.floor_navigation().free(point) and bool(self.floor_navigation().route((self.char_x,self.char_y), point)))
        try:
            route = self.scene_travel_route(sid)
            arrival = portal(self.cfg, route[-1]['to'])
            start = (arrival.get('inside_x',arrival['x']), arrival.get('inside_y',arrival['y']+45))
            scene = self.cfg['scenes'][sid]
            nav = FloorNavigation(scene['walkable_trapezoid'], scene.get('obstacles', []))
            return point is None or (nav.free(point) and bool(nav.route(start, point)))
        except (ValueError, KeyError, IndexError):
            return False

    def next_cycle_choice(self, sleeping=False):
        choices = self.cycle_choices()
        if choices:
            start = getattr(self, '_idle_world_cursor', 0) % len(choices)
            for offset in range(len(choices)):
                index = (start + offset) % len(choices)
                choice = choices[index]
                if choice[4 if sleeping else 3] and self.cycle_choice_reachable(choice):
                    self._idle_world_cursor = (index + 1) % len(choices)
                    return choice
        return None

    def apply_cycle_choice(self, choice, sleeping=False):
        if choice is None:
            self.gesture_role = None
            self.target_playback_override = None
            self.target_animation = None
            self.target_spot_id = None
            self.target_x, self.target_y = self.char_x, self.char_y
            self.idle_waiting = not sleeping
            self.wander_timer = random.uniform(6.0, 12.0)
            self.audit_activity('standby_unavailable' if sleeping else 'idle_unavailable', reason='No reachable eligible saved placement')
            return
        sid, spot, role, idle, sleep = choice
        self.gesture_role = None
        self.target_playback_override = None
        self.idle_waiting = not sleeping
        self.wander_timer = random.uniform(4.0, 8.0)
        if sid != scene_id(self.cfg):
            self.pending_idle_destination = (choice, sleeping)
            self.request_scene_travel(sid, standby=sleeping)
        else:
            self.target_animation = role
            self.target_spot_id = spot.get('id') if spot else None
            self.target_facing_left = (str(spot.get('facing', 'right')).lower() == 'left') if spot else None
            self.target_x, self.target_y = (spot['x'], spot['y']) if spot else (self.char_x, self.char_y)
        self.audit_activity('standby_selected' if sleeping else 'idle_selected', animation=role, spot_id=spot.get('id') if spot else None, destination_scene=sid, wait_until_event=not sleeping)

    def select_next_idle(self):
        self.apply_cycle_choice(self.next_cycle_choice())

    def begin_rest_transition(self, role, phase):
        sequence = self.character_sequences.get(role, {})
        transition_role = sequence.get(phase + '_transition')
        transition = self.character_sequences.get(transition_role)
        if not transition:
            return False
        if (phase == 'exit' and self.target_animation == role
                and getattr(self, 'target_spot_id', None) == getattr(self, 'active_rest_spot_id', None)
                and math.dist((self.char_x, self.char_y), (self.target_x, self.target_y)) < .01):
            self.target_animation = 'idle'  # Retire the old rest goal before its get-up completes.
        spot_id = getattr(self, 'active_rest_spot_id', None) if phase == 'exit' else getattr(self, 'target_spot_id', None)
        self.rest_transition = dict(role=transition_role, rest_role=role, phase=phase, started=time.monotonic(), spot_id=spot_id)
        self.current_anim = transition_role
        self.gesture_role, self.gesture_started = transition_role, self.rest_transition['started']
        self.audit_activity('rest_transition_started', animation=transition_role, rest_animation=role, phase=phase, spot_id=spot_id)
        return True

    def update_rest_transition(self):
        transition = getattr(self, 'rest_transition', None)
        if not transition:
            return False
        sequence = self.character_sequences[transition['role']]
        if (time.monotonic()-transition['started']) * sequence['fps'] < len(sequence['frames']):
            return True
        self.rest_transition = None
        self.audit_activity('rest_transition_completed', animation=transition['role'], rest_animation=transition['rest_role'], phase=transition['phase'], spot_id=transition.get('spot_id'))
        if transition['phase'] == 'entry':
            self.active_rest_role = transition['rest_role']
            self.active_rest_spot_id = transition.get('spot_id')
            self.current_anim = transition['rest_role']
            self.gesture_role, self.gesture_started = self.current_anim, time.monotonic()
        else:
            self.active_rest_role = None
            self.active_rest_spot_id = None
            self.current_anim = 'idle'
            self.gesture_role = None
            self.idle_started = time.monotonic()
            if getattr(self, 'pending_standby_choice', None) and self.is_sleeping:
                choice = self.pending_standby_choice
                self.pending_standby_choice = None
                self.apply_cycle_choice(choice, sleeping=True)
        return False

    def _morning_state_path(self):
        return os.path.join(os.path.dirname(get_active_config_path()), 'morning_greeting_state.json')

    def enter_standby(self, source='manual'):
        from morning_greeting import policy_for
        from scene_lighting import local_now
        try:
            policy_for(self).slept(local_now(self.cfg.get('lighting', {})))
        except (OSError, AttributeError) as error:
            self.audit_activity('morning_greeting_storage_error', error=str(error))
        if source == 'manual' and hasattr(self, 'light_sleep_policy'):
            self.light_sleep_policy.manual(time.monotonic())
        from interactive_props import close_tv
        close_tv(self, 'sleep')
        self.idle_waiting = False
        self.standby_settled_at = None
        queue = getattr(self, 'activity_queue', None)
        if queue:
            queue.defer_for_standby(self)
        self.pending_post_travel_action = None
        self.scene_journey = []
        self.journey_arriving = False
        self.is_sleeping = True
        self.active_popup_modal = None
        self.pending_popup_modal = None
        self.target_playback_override = None
        self.pending_idle_destination = None
        active_rest = getattr(self, 'active_rest_role', None)
        curr_scene = scene_id(self.cfg) if hasattr(self, 'cfg') and 'scenes' in getattr(self, 'cfg', {}) else None
        if active_rest:
            spot = next((s for s in self.cfg.get('interaction_spots', []) if s.get('id') == getattr(self, 'active_rest_spot_id', None)), None)
            choice = (curr_scene, spot or {'id': getattr(self, 'active_rest_spot_id', None), 'x': self.char_x, 'y': self.char_y}, active_rest, False, True)
        elif hasattr(self, 'cycle_choices') and hasattr(self, 'cycle_choice_reachable'):
            choices = self.cycle_choices()
            curr_choices = [c for c in choices if c[0] == curr_scene and c[4] and self.cycle_choice_reachable(c)]
            if curr_choices:
                start = getattr(self, '_idle_world_cursor', 0) % len(curr_choices)
                choice = curr_choices[start]
            else:
                choice = self.next_cycle_choice(sleeping=True)
        else:
            choice = self.next_cycle_choice(sleeping=True)
        self.standby_choice = choice
        self.pending_standby_choice = None
        if getattr(self, 'rest_transition', None) and self.rest_transition['phase'] == 'exit':
            self.pending_standby_choice = choice
        else:
            self.apply_cycle_choice(choice, sleeping=True)
        self.status_msg = 'Settling down. Tap the screen or press a switch to wake.'

    def wake_from_standby(self, source='manual'):
        if source == 'manual' and hasattr(self, 'light_sleep_policy'):
            self.light_sleep_policy.manual(time.monotonic())
        power = getattr(self, 'display_power', None)
        if power and not power.set_sleeping(False):
            self.status_msg = 'Could not wake display: ' + str(power.error)
            return
        queue = getattr(self, 'activity_queue', None)
        if queue:
            queue.resume_from_standby(self)
        if getattr(self, 'pending_idle_destination', None):
            self.pending_idle_destination = None
            self.scene_journey = []
            self.journey_arriving = False
        self.standby_settled_at = None
        self.is_sleeping = False
        self.pending_standby_choice = None
        self.standby_choice = None
        self.target_x, self.target_y = self.char_x, self.char_y
        self.target_animation = 'idle'
        self.target_spot_id = None
        self.target_playback_override = None
        self.wander_timer = 2.0
        self.status_msg = 'Waking up...'
        if getattr(self, 'active_rest_role', None):
            self.begin_rest_transition(self.active_rest_role, 'exit')
        self.audit_activity('woken', animation=getattr(self, 'active_rest_role', None), spot_id=getattr(self, 'active_rest_spot_id', None))

    def stand_and_face_user(self):
        """Immediately wake if asleep, stand up from any resting/inspecting pose, cancel wandering, and face the user."""
        if getattr(self, 'is_sleeping', False):
            self.wake_from_standby(source='voice')
        if getattr(self, 'active_rest_role', None):
            if not self.begin_rest_transition(self.active_rest_role, 'exit'):
                self.active_rest_role = None
                self.active_rest_spot_id = None
                self.current_anim = 'idle'
                self.gesture_role = None
        elif getattr(self, 'rest_transition', None):
            pass
        else:
            if self.current_anim not in ('idle', 'walk'):
                self.current_anim = 'idle'
                self.gesture_role = None
        self.idle_waiting = False
        self.is_inspecting = False
        self.target_animation = 'idle'
        self.target_spot_id = None
        self.target_playback_override = None
        self.target_x, self.target_y = self.char_x, self.char_y
        self._route_goal = None
        self.target_facing_left = False
        self.facing_left = False
        self.motion_direction = 'side'

    def dismiss_active_modal(self):
        """Dismiss any active/pending popup modal and restore normal idle wandering."""
        dismissed = bool(getattr(self, 'active_popup_modal', None) or getattr(self, 'pending_popup_modal', None))
        self.active_popup_modal = None
        self.pending_popup_modal = None
        self.active_slider_dragging = False
        self.popup_slider_rect = None
        self.popup_slider_data = None
        queue = getattr(self, 'activity_queue', None)
        if queue:
            queue.dismiss_popup(self)
        spk = getattr(self, 'speech_output', None)
        if spk and hasattr(spk, 'stop_playback'):
            spk.stop_playback()
        if not (queue and getattr(queue, 'active', None)):
            if (getattr(self, 'current_anim', None) == 'wave_hello'
                    or getattr(self, 'target_animation', None) == 'wave_hello'
                    or getattr(self, 'gesture_role', None) == 'wave_hello'):
                self.current_anim = 'idle'
                self.target_animation = None
                self.gesture_role = None
            self.idle_waiting = False
            if getattr(self, 'wander_timer', 0) > 2.0:
                self.wander_timer = 1.5
        return dismissed

    def on_switch_pressed(self, sw_id):
        if threading.get_ident() != getattr(self, '_display_thread', threading.get_ident()):
            self._switch_inputs.put(sw_id)
            return
        self._handle_switch_pressed(sw_id)

    def process_switch_inputs(self):
        inputs = getattr(self, '_switch_inputs', None)
        if inputs is not None:
            while not inputs.empty():
                self._handle_switch_pressed(inputs.get_nowait())

    def _handle_switch_pressed(self, sw_id):
        self.audit_activity('switch_pressed', switch_id=sw_id)
        self.switch_press_times[sw_id] = time.time()
        if getattr(self, 'active_game_overlay', None):
            if self.active_game_overlay.handle_switch(self, sw_id):
                return
        if getattr(self, 'tv_viewer', None):
            from interactive_props import tv_switch
            if tv_switch(self, sw_id):
                return
        queue = getattr(self, 'activity_queue', None)
        switch = next((s for s in self.switches if s['id'] == sw_id), {})
        if not self.is_sleeping and switch.get('app_id') and queue and queue.acknowledge_attention(self, switch['app_id']):
            return
        
        # If a popup modal was active, check if user pressed the SAME switch to dismiss it,
        # or a DIFFERENT switch to transition to the new app.
        current_modal = self.active_popup_modal
        if current_modal:
            modal_title = (current_modal.get("title") or current_modal.get("app_name") or "").lower()
            sw = next((s for s in self.switches if s["id"] == sw_id), None)
            sw_name = (sw.get("name") or "").lower() if sw else ""
            self.dismiss_active_modal()
            # If pressing the exact same switch that opened the modal, treat as toggle dismiss
            if sw_name and (sw_name in modal_title or modal_title in sw_name):
                return

        if self.is_sleeping:
            power = getattr(self, 'display_power', None)
            display_off = getattr(power, 'is_off', False)
            if sw_id == 1 and not display_off:
                self.standby_settled_at = time.monotonic() - 1.0
                return
            self.wake_from_standby()
            return

        if self.quick_keys_mode == "on_press":
            self.show_quick_keys = True
            self.keys_dismiss_timer = 2.5
        elif self.quick_keys_mode == "always":
            self.show_quick_keys = True
            self.keys_dismiss_timer = 0.0
        elif self.quick_keys_mode == "never":
            self.show_quick_keys = False
            self.keys_dismiss_timer = 0.0
        self.is_inspecting = False

        if sw_id == 1:
            self.enter_standby()
        elif sw_id == 6:
            self.show_shutdown_modal = True
        else:
            # Data-driven switch routing for external apps (SW 2..5)
            sw = next((s for s in self.switches if s["id"] == sw_id), None)
            if sw:
                app_id = sw.get("app_id")
                tele = self.app_telemetry.get(app_id, {})
                from integration_state import button_summary_for
                cached_summary = button_summary_for(tele, sw.get("name", app_id or "this application"))
                ticker = tele.get("ticker", [])

                # 1. Check structured apps actions
                app_cfg = next((a for a in self.apps if a["id"] == app_id or a.get("switch_id") == sw_id), None)
                if app_cfg:
                    # Match primary action, switch-mapped action, status_check, or first action
                    actions = app_cfg.get("actions", [])
                    act = next((a for a in actions if a.get("is_primary") or a.get("switch_id") == sw_id), None)
                    if not act:
                        act = next((a for a in actions if a.get("event") in ["status_check", f"sw_{sw_id}"] or a.get("id") in ["status_check", f"sw_{sw_id}"]), None)
                    if not act and actions:
                        act = actions[0]
                    if act:
                        col = tuple(app_cfg.get("color", sw.get("color", [0, 229, 255])))
                        self.queue_action(act, app_cfg.get("name", sw["name"]), col, cached_summary, ticker, source_event='button', priority=True)
                        return

                # Unconfigured buttons still get a priority, dismissible summary.
                self.queue_action({'animation':'idle', 'x':self.char_x, 'y':self.char_y,
                    'display_mode':'popup_modal', 'speech':'{summary}'}, sw['name'],
                    tuple(sw.get('color', [0,229,255])), cached_summary, ticker,
                    source_event='button', priority=True)

    def walk_from_touch(self, pos, prop=False):
        """Move idle characters without relocating a queued action or its pose."""
        queue = getattr(self, 'activity_queue', None)
        if queue and queue.active:
            self.audit_activity('touch_walk_ignored', reason='application_action_active')
            return
        nav = self.floor_navigation()
        goal = self.clamp_to_walkable(*pos)
        if not nav.free(goal) or not nav.route((self.char_x, self.char_y), goal):
            self.audit_activity('touch_walk_ignored', reason='outside_or_unreachable_floor', requested_point=list(pos))
            return
        self.scene_journey = []
        self.journey_arriving = self.journey_exiting = False
        self.pending_idle_destination = None
        self.pending_post_travel_action = None
        self.target_x, self.target_y = goal
        self._route_goal = None
        self.target_animation = 'idle'
        self.target_spot_id = None
        self.target_playback_override = None
        self.target_facing_left = None
        self.idle_waiting = False
        self.wander_timer = 8.0
        self.is_inspecting = False
        self.audit_activity('touch_walk_requested', destination=list(goal))

    def _map_event_pos(self, pos):
        if getattr(self, 'desktop_mode', False) and hasattr(self, 'desktop_helper'):
            return self.desktop_helper.map_input_pos(pos, (self.win_width, self.win_height))
        return pos

    def handle_prop_app_action(self, prop, app_id, action_id=None):
        """Dispatches an application action when an interactive prop is tapped."""
        app_entry = None
        for app in self.cfg.get('integrations', []):
            if app.get('id') == app_id:
                app_entry = app
                break
        app_name = (app_entry.get('name') if app_entry else app_id) or "App"
        action_cfg = None
        if app_entry and action_id:
            for act in app_entry.get('actions', []):
                if act.get('id') == action_id or act.get('event') == action_id:
                    action_cfg = act
                    break
        if not action_cfg:
            action_cfg = {'id': action_id or 'tap', 'event': action_id or 'tap', 'target_mode': 'current'}
        prop_label = prop.get('label') or prop.get('id', 'Prop')
        self.status_msg = f"{prop_label}: Triggered {app_name}"
        try:
            self.trigger_action(action_cfg, app_name=app_name)
        except Exception as e:
            print(f"[PROP_ACTION] Error triggering {app_name}.{action_id}: {e}")

    def handle_prop_game_script(self, prop):
        """Launches an interactive mini-game or game script overlay."""
        game_id = prop.get('game_id') or 'breakout'
        bezel_type = prop.get('bezel') or 'crt_monitor'
        try:
            from games.overlay import GameOverlay
            self.active_game_overlay = GameOverlay(self, game_id=game_id, bezel_type=bezel_type)
            prop_label = prop.get('label') or prop.get('id', 'Game')
            self.status_msg = f"Started {prop_label} ({game_id})"
        except Exception as e:
            print(f"[GAME_OVERLAY] Error launching {game_id}: {e}")
            self.status_msg = f"Error launching {game_id}"

    def handle_prop_trigger_animation(self, prop):
        """Triggers an in-scene animation burst on this prop."""
        anim_id = prop.get('tap_animation') or prop.get('animation_id')
        if anim_id and anim_id in self.cfg.get('prop_animations', {}):
            prop['animation_id'] = anim_id
            prop['last_tap_time'] = time.monotonic()
        prop_label = prop.get('label') or prop.get('id', 'Prop')
        self.status_msg = f"Activated {prop_label}"

    def handle_touch_down(self, pos):
        if getattr(self, 'is_sleeping', False):
            self.wake_from_standby()
            return
        if getattr(self, '_game_exit_cooldown', 0) > time.monotonic():
            return
        if getattr(self, 'active_game_overlay', None):
            self.active_game_overlay.handle_touch_down(self, pos)
            return
        if getattr(self, 'tv_viewer', None):
            from interactive_props import tv_touch
            tv_touch(self, pos)
            return
        queue = getattr(self, 'activity_queue', None)
        if not self.is_sleeping and not self.active_popup_modal and getattr(self, 'character_touch_rect', pygame.Rect(0, 0, 0, 0)).collidepoint(pos):
            if queue and queue.acknowledge_attention(self):
                return
        if not self.active_popup_modal and getattr(self, 'integration_attention', None) and getattr(self, 'character_touch_rect', pygame.Rect(0, 0, 0, 0)).collidepoint(pos):
            messages = list(self.integration_attention.values())
            for app_id in list(self.integration_attention.keys()):
                if not hasattr(self, 'attention_seen'):
                    self.attention_seen = {}
                self.attention_seen[app_id] = 'acknowledged'
                if hasattr(self, 'activity_queue') and self.activity_queue:
                    self.activity_queue.purge_app_alerts(self, app_id)
            self.integration_attention.clear()
            self.active_popup_modal = {'title': 'Applications need attention', 'summary': '\n'.join(messages), 'ticker': [], 'color': (255, 190, 100), 'timestamp': time.strftime('%I:%M %p')}
            return
        if not self.is_sleeping and not self.active_popup_modal and getattr(self, 'character_touch_rect', pygame.Rect(0, 0, 0, 0)).collidepoint(pos):
            from voice_sentry import sentry_for
            if sentry_for(self).trigger_poke(self):
                return
        if self.active_popup_modal:
            # Check touch slider rail first
            if getattr(self, 'popup_slider_rect', None) and self.popup_slider_rect.collidepoint(pos):
                self.active_slider_dragging = True
                info = getattr(self, 'popup_slider_data', None)
                if info:
                    rail_x = info['rail_x']
                    rail_w = info['rail_w']
                    s = info['slider']
                    pct = max(0.0, min(1.0, (pos[0] - rail_x) / float(rail_w)))
                    raw_val = s['min'] + pct * (s['max'] - s['min'])
                    step = s.get('step', 5)
                    stepped_val = int(round(raw_val / step) * step)
                    s['value'] = max(s['min'], min(s['max'], stepped_val))
                return

            for direction, rect in getattr(self, 'popup_page_buttons', []):
                if rect.collidepoint(pos):
                    self.active_popup_modal['page'] = self.active_popup_modal.get('page', 0) + direction
                    return

            # If modal had an active slider, commit its value on dismiss
            slider = self.active_popup_modal.get('slider')
            if slider and slider.get('callback_url'):
                val = slider.get('value', 45)
                def _post_slider(url, minutes):
                    try:
                        req = urllib.request.Request(
                            url,
                            data=json.dumps({"minutes": minutes}).encode("utf-8"),
                            headers={"Content-Type": "application/json"}
                        )
                        urllib.request.urlopen(req, timeout=1.5)
                    except Exception as e:
                        print(f"[Slider] Callback error: {e}")
                threading.Thread(target=_post_slider, args=(slider['callback_url'], val), daemon=True).start()

            self.dismiss_active_modal()
            return
        if self.is_sleeping:
            self.wake_from_standby()
            return

        if self.show_shutdown_modal:
            if self.modal_cancel_rect.collidepoint(pos):
                self.show_shutdown_modal = False
            elif self.modal_shutdown_rect.collidepoint(pos):
                self.perform_shutdown()
            return

        if not self.edit_mode:
            if self.btn_exit_rect.collidepoint(pos):
                self.running = False
                return
            if pos[1] <= 68:
                self.top_swipe_start = pos
                return
            if self.top_controls_open and pos[1] > 136:
                self.top_controls_open = False
                return

        if not self.edit_mode and getattr(self, 'character_touch_rect', pygame.Rect(0, 0, 0, 0)).collidepoint(pos):
            return  # A character tap without an alert must not become a floor destination.

        # Top Buttons (Normal Mode)
        if not self.edit_mode:
            if self.btn_exit_rect.collidepoint(pos):
                self.running = False
                return

            if self.top_controls_open and self.btn_edit_rect.collidepoint(pos):
                self.top_controls_open = False
                self.edit_mode = True
                self.active_handle = None
                self.active_obstacle_idx = None
                self.is_resizing_obstacle = False
                return

            if self.top_controls_open and self.btn_font_rect.collidepoint(pos):
                cycle = {"standard": "large", "large": "extra_large", "extra_large": "standard"}
                next_scale = cycle.get(self.ui_font_scale, "large")
                self._init_fonts(next_scale)
                self.save_walkbox_config()
                self.status_msg = f"Text scale set to {next_scale.upper()}"
                return

            if self.top_controls_open and self.btn_keys_rect.collidepoint(pos):
                cycle = {"on_press": "always", "always": "never", "never": "on_press"}
                next_mode = cycle.get(self.quick_keys_mode, "on_press")
                self.set_on_screen_buttons_mode(next_mode)
                self.save_walkbox_config()
                mode_labels = {"always": "ALWAYS SHOW", "never": "ALWAYS HIDE", "on_press": "SHOW ON PRESS (AUTO-DISMISS)"}
                self.status_msg = f"On-screen buttons: {mode_labels.get(next_mode)}"
                return

            if self.top_controls_open:
                return  # The controls panel must not send floor taps through it.

            # Interactive props tap handling (screens, app actions, game scripts, animation triggers)
            from interactive_props import tv_hit, tv_channels, open_tv, prop_hit
            night_val = getattr(self, 'lighting_night_amount', 0)
            for prop in reversed(self.props):
                if prop_hit(prop, pos, night_val):
                    interaction = prop.get('interaction', 'none')
                    if interaction in ('tv', 'overlay_popup'):
                        if tv_channels(self.cfg, prop):
                            open_tv(self, prop)
                            return
                    elif interaction == 'app_action':
                        self.handle_prop_app_action(prop, prop.get('app_id'), prop.get('action_id'))
                        return
                    elif interaction == 'game_script':
                        self.handle_prop_game_script(prop)
                        return
                    elif interaction == 'trigger_animation':
                        self.handle_prop_trigger_animation(prop)
                        return
                    elif interaction == 'none':
                        self.walk_from_touch((prop["x"], prop["y"]), prop=True)
                        self.status_msg = f"Inspecting {prop.get('label') or prop.get('id', 'Prop')}..."
                        return

            # Normal mode: touch props fallback (approximate bounding box if not caught by prop_hit)
            for prop in self.props:
                prop_rect = pygame.Rect(prop["x"] - 60, prop["y"] - 60, 120, 120)
                if prop_rect.collidepoint(pos):
                    self.walk_from_touch((prop["x"], prop["y"]), prop=True)
                    self.status_msg = f"Inspecting {prop.get('label') or prop.get('id', 'Prop')}..."
                    return

            # Bottom switch keys
            if self.show_quick_keys:
                tile_w = (self.width - 80) // 6
                for i, sw in enumerate(self.switches):
                    rect = pygame.Rect(40 + i * tile_w, self.height - 110, tile_w - 12, 80)
                    if rect.collidepoint(pos):
                        self.on_switch_pressed(sw["id"])
                        return

            # Floor tap -> walk there
            self.walk_from_touch(pos)
            return

        # === Editor Mode Touch Controls ===
        if self.ed_done_rect.collidepoint(pos):
            # [DONE] button -> exits back to normal mode
            self.edit_mode = False
            self.active_handle = None
            self.active_obstacle_idx = None
            self.is_resizing_obstacle = False
            return

        if self.ed_save_rect.collidepoint(pos):
            self.save_walkbox_config()
            return

        # Toggle Hide / Show Character in Editor
        if self.ed_toggle_char_rect.collidepoint(pos):
            self.editor_hide_char = not self.editor_hide_char
            return

        # Scale adjustments
        if self.ed_back_minus.collidepoint(pos):
            self.trap["scale_at_y_min"] = max(100, self.trap["scale_at_y_min"] - 10)
            self.sprite_cache.clear()
            return
        if self.ed_back_plus.collidepoint(pos):
            self.trap["scale_at_y_min"] = min(400, self.trap["scale_at_y_min"] + 10)
            self.sprite_cache.clear()
            return
        if self.ed_front_minus.collidepoint(pos):
            self.trap["scale_at_y_max"] = max(150, self.trap["scale_at_y_max"] - 10)
            self.sprite_cache.clear()
            return
        if self.ed_front_plus.collidepoint(pos):
            self.trap["scale_at_y_max"] = min(550, self.trap["scale_at_y_max"] + 10)
            self.sprite_cache.clear()
            return

        # Add / Delete Obstacle Buttons
        if self.ed_add_block_rect.collidepoint(pos):
            new_id = f"block_{len(self.obstacles) + 1}"
            self.obstacles.append({
                "id": new_id,
                "x": self.width // 2 - 65,
                "y": self.trap["y_min"] + 30,
                "w": 130,
                "h": 65,
                "label": f"Block {len(self.obstacles) + 1}"
            })
            self.active_obstacle_idx = len(self.obstacles) - 1
            obs = self.obstacles[-1]
            x, y, w, h = (obs[k] for k in ('x', 'y', 'w', 'h'))
            obs['points'] = [[x+20, y], [x+w-20, y], [x+w, y+h], [x, y+h]]
            return

        if self.ed_del_block_rect.collidepoint(pos):
            if self.active_obstacle_idx is not None and 0 <= self.active_obstacle_idx < len(self.obstacles):
                self.obstacles.pop(self.active_obstacle_idx)
                self.active_obstacle_idx = None
                self.is_resizing_obstacle = False
            return

        # Discrete W / H adjustments for selected block
        if self.active_obstacle_idx is not None and 0 <= self.active_obstacle_idx < len(self.obstacles):
            obs = self.obstacles[self.active_obstacle_idx]
            if self.ed_w_minus.collidepoint(pos):
                set_obstacle_bounds(obs, w=max(35, obs["w"] - 15))
                return
            if self.ed_w_plus.collidepoint(pos):
                set_obstacle_bounds(obs, w=min(800, obs["w"] + 15))
                return
            if self.ed_h_minus.collidepoint(pos):
                set_obstacle_bounds(obs, h=max(25, obs["h"] - 15))
                return
            if self.ed_h_plus.collidepoint(pos):
                set_obstacle_bounds(obs, h=min(500, obs["h"] + 15))
                return

        # Check if touched corner resize handle of currently active obstacle (35x35 target)
        if self.active_obstacle_idx is not None and 0 <= self.active_obstacle_idx < len(self.obstacles):
            obs = self.obstacles[self.active_obstacle_idx]
            br_rect = pygame.Rect(obs["x"] + obs["w"] - 25, obs["y"] + obs["h"] - 25, 35, 35)
            if br_rect.collidepoint(pos):
                self.is_resizing_obstacle = True
                return

        # Check if touched body of any obstacle
        for idx, obs in enumerate(self.obstacles):
            orect = pygame.Rect(obs["x"], obs["y"], obs["w"], obs["h"])
            if point_in_polygon(pos, obstacle_points(obs)):
                self.active_obstacle_idx = idx
                self.active_handle = None
                self.is_resizing_obstacle = False
                self.drag_offset_x = pos[0] - obs["x"]
                self.drag_offset_y = pos[1] - obs["y"]
                return

        # Check if clicked any of the 4 corner walkbox handles
        handles = [
            ("BL", self.trap["back_x_min"], self.trap["y_min"]),
            ("BR", self.trap["back_x_max"], self.trap["y_min"]),
            ("FR", self.trap["front_x_max"], self.trap["y_max"]),
            ("FL", self.trap["front_x_min"], self.trap["y_max"])
        ]
        if self.trap.get("points"):
            handles = [(f"P{i+1}", x, y) for i, (x, y) in enumerate(self.trap["points"])]
        for h_id, hx, hy in handles:
            rect = pygame.Rect(hx - 35, hy - 35, 70, 70)
            if rect.collidepoint(pos):
                self.active_handle = h_id
                self.active_obstacle_idx = None
                self.is_resizing_obstacle = False
                return

        if self.active_handle:
            self.update_handle_position(self.active_handle, pos[0], pos[1])

    def handle_touch_motion(self, pos):
        if getattr(self, 'active_game_overlay', None):
            self.active_game_overlay.handle_touch_motion(self, pos)
            return
        if getattr(self, 'active_slider_dragging', False):
            info = getattr(self, 'popup_slider_data', None)
            if info:
                rail_x = info['rail_x']
                rail_w = info['rail_w']
                s = info['slider']
                pct = max(0.0, min(1.0, (pos[0] - rail_x) / float(rail_w)))
                raw_val = s['min'] + pct * (s['max'] - s['min'])
                step = s.get('step', 5)
                stepped_val = int(round(raw_val / step) * step)
                s['value'] = max(s['min'], min(s['max'], stepped_val))
            return

        if not self.edit_mode:
            if self.top_swipe_start is not None:
                dx = pos[0] - self.top_swipe_start[0]
                dy = pos[1] - self.top_swipe_start[1]
                if dy >= 35 and dy > abs(dx):
                    self.top_controls_open = True
            return

        if self.is_resizing_obstacle and self.active_obstacle_idx is not None and 0 <= self.active_obstacle_idx < len(self.obstacles):
            obs = self.obstacles[self.active_obstacle_idx]
            set_obstacle_bounds(obs, w=max(35, min(800, pos[0] - obs["x"])), h=max(25, min(500, pos[1] - obs["y"])))
            return

        if self.active_handle:
            self.update_handle_position(self.active_handle, pos[0], pos[1])
        elif self.active_obstacle_idx is not None and 0 <= self.active_obstacle_idx < len(self.obstacles):
            obs = self.obstacles[self.active_obstacle_idx]
            # UNRESTRICTED: anywhere across the screen
            set_obstacle_bounds(obs, x=max(0, min(self.width - obs["w"], pos[0] - self.drag_offset_x)), y=max(0, min(self.height - obs["h"], pos[1] - self.drag_offset_y)))

    def handle_touch_up(self):
        if getattr(self, 'active_game_overlay', None):
            self.active_game_overlay.handle_touch_up(self, None)
        self.active_slider_dragging = False
        self.top_swipe_start = None
        self.active_handle = None
        self.is_resizing_obstacle = False

    def update_handle_position(self, handle_id, x, y):
        if handle_id.startswith('P') and self.trap.get('points'):
            points = [list(p) for p in self.trap['points']]
            points[int(handle_id[1:])-1] = [int(x), int(y)]
            points = [list(p) for p in clip_floor_to_screen(points)]
            if valid_floor_points(points):
                self.trap['points'] = points
            return
        x = max(50, min(self.width - 50, x))
        y = max(200, min(self.height - 20, y))

        if handle_id == "BL":
            self.trap["back_x_min"] = int(min(x, self.trap["back_x_max"] - 60))
            self.trap["y_min"] = int(min(y, self.trap["y_max"] - 60))
        elif handle_id == "BR":
            self.trap["back_x_max"] = int(max(x, self.trap["back_x_min"] + 60))
            self.trap["y_min"] = int(min(y, self.trap["y_max"] - 60))
        elif handle_id == "FL":
            self.trap["front_x_min"] = int(min(x, self.trap["front_x_max"] - 60))
            self.trap["y_max"] = int(max(y, self.trap["y_min"] + 60))
        elif handle_id == "FR":
            self.trap["front_x_max"] = int(max(x, self.trap["front_x_min"] + 60))
            self.trap["y_max"] = int(max(y, self.trap["y_min"] + 60))

    def perform_shutdown(self):
        if self.local_preview:
            self.show_shutdown_modal = False
            self.status_msg = 'Shutdown is disabled in local preview'
            return
        if getattr(self, 'desktop_mode', False):
            print("Closing Desk-Pal Desktop Companion...")
            self.running = False
            return
        print("Executing safe shutdown...")
        self.screen.fill((0, 0, 0))
        txt = self.font_lg.render("Shutting down cleanly...", True, self.palette["text"])
        self.screen.blit(txt, (self.width // 2 - txt.get_width() // 2, self.height // 2))
        pygame.display.flip()
        time.sleep(1.0)
        try:
            subprocess.run(["sudo", "shutdown", "-h", "now"])
        except Exception:
            pass
        self.running = False

    def get_perspective_sprite(self, sprite_name, y_pos, facing_left):
        if self.cfg.get("active_character") and sprite_name not in self.raw_sprites:
            sprite_name = "idle"
        target_h = int(floor_perspective_height(self.trap, y_pos))
        reference_height = getattr(self, 'sprite_metrics', {}).get(sprite_name, {}).get('reference_height')
        if reference_height:
            target_h *= self.raw_sprites[sprite_name].get_height() / reference_height
        cached_h = max(4, int(target_h // 4) * 4)

        cache_key = (sprite_name, cached_h, facing_left)
        if cache_key in self.sprite_cache:
            return self.sprite_cache[cache_key]

        if sprite_name not in self.raw_sprites:
            return None

        raw = self.raw_sprites[sprite_name]
        aspect = raw.get_width() / raw.get_height()
        target_w = int(cached_h * aspect)
        scaled = pygame.transform.smoothscale(raw, (target_w, cached_h))
        if facing_left:
            scaled = pygame.transform.flip(scaled, True, False)

        self.sprite_cache[cache_key] = scaled
        return scaled

    def update_autonomous_movement(self, dt):
        if self.edit_mode:
            return
        transitioning = bool(getattr(self, 'rest_transition', None))
        if self.update_rest_transition() or transitioning:
            return  # Hand completed transitions back to the queue before choosing another pose.
        resting = getattr(self, 'active_rest_role', None)
        leaving = math.dist((self.char_x,self.char_y),(self.target_x,self.target_y)) > .01 or self.target_animation != resting
        if resting and leaving and self.begin_rest_transition(resting, 'exit'):
            return

        nav = self.floor_navigation()
        if not nav.free((self.char_x, self.char_y)):
            point = nav.nearest((self.char_x, self.char_y))
            if point is None:
                self.status_msg = 'No walkable floor remains — adjust the blocks'
                return
            self.char_x, self.char_y = point
            self._route_goal = None
        goal = (self.target_x, self.target_y)
        if getattr(self, '_route_goal', None) != goal:
            goal = nav.nearest(goal)
            self._route = nav.route((self.char_x, self.char_y), goal) if goal else []
            if not self._route:
                goal = (self.char_x, self.char_y)
                self.target_animation = 'idle'
                self.pending_popup_modal = None
                self.wander_timer = min(self.wander_timer, 2.0)
            self.target_x, self.target_y = goal
            self._route_goal = goal
        while self._route and math.dist((self.char_x, self.char_y), self._route[0]) < 0.01:
            self._route.pop(0)
        waypoint = self._route[0] if self._route else (self.target_x, self.target_y)

        dx = waypoint[0] - self.char_x
        dy = waypoint[1] - self.char_y
        dist = (dx**2 + dy**2)**0.5

        if dist > 0.01:
            direction = ('down' if dy > 0 else 'up') if abs(dy) > abs(dx)*1.2 else 'side'
            if direction != getattr(self, 'motion_direction', 'side'):
                self.anim_frame, self.anim_timer = 0, 0.0
            self.motion_direction = direction
            self.idle_started = time.monotonic()
            if direction == 'side':
                self.facing_left = (dx < 0)
            self.current_anim = "walk"
            self.gesture_role = None
            self.is_inspecting = False
            
            step = min(dist, 150.0 * max(0.0, min(dt, 0.1)))
            next_point = (self.char_x + dx / dist * step, self.char_y + dy / dist * step)
            if nav.clear((self.char_x, self.char_y), next_point):
                self.char_x, self.char_y = next_point
            else:
                self._route_goal = None
                return

            self.anim_timer += dt
            interval = 1.0 / self.current_walk_sequence()["fps"]
            steps = int(self.anim_timer / interval)
            self.anim_timer -= steps * interval
            self.anim_frame += steps
        else:
            self.char_x = self.target_x
            self.char_y = self.target_y

            if (getattr(self, 'scene_journey', None) or getattr(self, 'journey_arriving', False)) and self.advance_scene_journey():
                return

            # If arriving at an action target, orient to the configured facing direction
            if self.target_facing_left is not None:
                self.facing_left = self.target_facing_left
                self.motion_direction = "side"

            if (self.target_animation in ('sitting_rest', 'sleeping') or getattr(self, 'character_sequences', {}).get(self.target_animation, {}).get('entry_transition')) and getattr(self, 'active_rest_role', None) != self.target_animation:
                if self.rest_role_ready(self.target_animation):
                    self.begin_rest_transition(self.target_animation, 'entry')
                    return
                self.target_animation = 'idle'  # A rest pose without transitions is not safe to enter.
            if self.target_animation:
                self.current_anim = self.target_animation
                self.is_inspecting = (self.current_anim == "inspect")
            else:
                if self.current_anim == "walk":
                    self.current_anim = "idle"

            # Open popup modal upon arrival if pending (unless waiting for attention)
            if self.pending_popup_modal:
                queue = getattr(self, 'activity_queue', None)
                active_action = queue.active[0] if (queue and queue.active) else {}
                if not active_action.get('_attention_waiting'):
                    self.active_popup_modal = self.pending_popup_modal
                    self.pending_popup_modal = None
                    self.wander_timer = 20.0  # Hold station while modal is displayed
                    speech = getattr(self, 'pending_arrival_speech', None)
                    if speech:
                        self.pending_arrival_speech = None
                        speech_text = speech[:450].strip()
                        bubble_dur = max(6.0, min(16.0, len(speech_text) * 0.08 + 2.0))
                        self.voice_thought_bubble = {
                            'text': speech_text,
                            'timestamp': time.monotonic(),
                            'expires_at': time.monotonic() + bubble_dur
                        }
                        spk = getattr(self, 'speech_output', None)
                        if not spk:
                            try:
                                from speech_output import output_for
                                spk = output_for(self)
                            except Exception:
                                pass
                        if spk and hasattr(spk, 'speak'):
                            cfg_path = getattr(self, 'ai_settings_path', None) or 'config/ai_settings.json'
                            hw = getattr(self, 'hardware_monitor', None)
                            spk_cfg = hw.config.get('speaker', {}) if hw else {'enabled': True}
                            try:
                                spk.speak(speech, cfg_path, spk_cfg, source='arrival_speech')
                            except Exception as err:
                                print(f"[DeskPal] Could not speak arrival speech: {err}")

            if getattr(self, 'is_sleeping', False):
                if getattr(self, 'rest_transition', None):
                    self.standby_settled_at = None
                    return
                choice = getattr(self, 'standby_choice', None)
                needs_travel = False
                if choice:
                    target_spot = choice[1]
                    target_spot_id = target_spot.get('id') if isinstance(target_spot, dict) else None
                    if scene_id(self.cfg) != choice[0]:
                        needs_travel = True
                    elif getattr(self, 'active_rest_role', None) != choice[2]:
                        if target_spot_id and getattr(self, 'target_spot_id', None) != target_spot_id:
                            needs_travel = True
                        elif math.dist((self.char_x, self.char_y), (self.target_x, self.target_y)) > 1.0:
                            needs_travel = True

                if needs_travel:
                    self.standby_settled_at = None
                    if not getattr(self, 'pending_idle_destination', None) and not getattr(self, 'scene_journey', None):
                        reachable = self.cycle_choice_reachable(choice) if hasattr(self, 'cycle_choice_reachable') else True
                        if choice and reachable:
                            self.apply_cycle_choice(choice, sleeping=True)
                        else:
                            curr_scene = scene_id(self.cfg) if hasattr(self, 'cfg') and 'scenes' in getattr(self, 'cfg', {}) else None
                            choices = [c for c in self.cycle_choices() if c[0] == curr_scene and c[4] and (self.cycle_choice_reachable(c) if hasattr(self, 'cycle_choice_reachable') else True)] if hasattr(self, 'cycle_choices') else []
                            if choices:
                                self.standby_choice = choices[0]
                                self.apply_cycle_choice(choices[0], sleeping=True)
                            else:
                                self.standby_choice = (curr_scene, None, 'sleeping' if self.rest_role_ready('sleeping') else 'idle', False, True)
                                self.target_animation = self.standby_choice[2]
                                self.current_anim = self.standby_choice[2]
                    return
                if getattr(self, 'standby_settled_at', None) is None:
                    self.standby_settled_at = time.monotonic()
                power = getattr(self, 'display_power', None)
                if power and not power.is_off and time.monotonic() - self.standby_settled_at >= 0.75:
                    if not power.set_sleeping(True):
                        self.status_msg = 'Display power-off failed: ' + str(power.error)
                        self.standby_settled_at = time.monotonic() + 5  # Avoid retrying each frame.
                    else:
                        self.audit_activity('display_powered_off', animation=self.current_anim, spot_id=getattr(self, 'target_spot_id', None))
                return  # Inputs remain active while the panel is powered down.
            if self.current_anim == 'idle' and not getattr(getattr(self, 'activity_queue', None), 'active', None) and not getattr(self, 'idle_waiting', False):
                if not self.active_popup_modal and not getattr(self, 'scene_journey', None) and self.wander_timer > 60.0:
                    self.wander_timer = random.uniform(3.0, 6.0)
                if self.wander_timer <= 0:
                    self.select_next_idle()
                    return
            if getattr(self, 'idle_waiting', False) and not getattr(getattr(self, 'activity_queue', None), 'active', None):
                return  # Loop, or hold the final finite frame, until an event interrupts.
            sequence = self.action_sequence(self.current_anim)
            if sequence and self.current_anim != 'walk':
                if getattr(self, 'gesture_role', None) != self.current_anim:
                    self.gesture_role, self.gesture_started = self.current_anim, time.monotonic()
                limit = self.sequence_tick_limit(sequence)
                if math.isfinite(limit):
                    elapsed = time.monotonic() - self.gesture_started
                    if elapsed * sequence['fps'] < limit:
                        return  # Finish the requested plays before choosing another action.
                    self.target_animation = None
                    self.current_anim = 'idle'
                    self.is_inspecting = False
                    self.gesture_role = None
                    self.idle_started = time.monotonic()
                    self.wander_timer = min(getattr(self, 'wander_timer', 4.0), random.uniform(3.0, 6.0))
                else:
                    self.wander_timer -= dt
            else:
                self.wander_timer -= dt
            if getattr(getattr(self, 'activity_queue', None), 'active', None):
                return
            if self.wander_timer <= 0:
                self.select_next_idle()


    def draw_typing_screens(self):
        """Placement-bound screen activity; never runs while travelling or asleep."""
        from prop_runtime import prop_time_visible
        if (self.current_anim != 'typing' or getattr(self, 'is_sleeping', False)
                or math.hypot(self.target_x-self.char_x, self.target_y-self.char_y) > 1):
            return
        spot = next((s for s in self.cfg.get('interaction_spots', [])
                     if s.get('id') == getattr(self, 'target_spot_id', None)), None)
        if not spot or math.hypot(spot['x']-self.char_x, spot['y']-self.char_y) > 18:
            return
        for prop in self.props:
            if not prop_time_visible(prop, getattr(self, 'lighting_night_amount', 0)):
                continue
            if prop.get('enabled', True) is False or prop.get('typing_spot_id') != spot['id']:
                continue
            quad = prop.get('screen_quad', [])
            if len(quad) != 4:
                continue
            def point(u, v):
                a,b,c,d = quad
                return tuple(round((1-v)*((1-u)*a[i]+u*b[i])+v*((1-u)*d[i]+u*c[i])) for i in (0,1))
            phase = int(time.monotonic()*5)
            for row in range(6):
                v = .16 + row*.12
                length = .2 + ((row*7+phase//6)%9)*.06
                pygame.draw.line(self.screen, (113, 190, 134), point(.12,v), point(min(.87,.12+length),v), 1)
            if phase%4 < 2:
                pygame.draw.line(self.screen, (169, 220, 161), point(.14,.88), point(.24,.88), 2)

    def foreground_sprite(self, sprite, draw_x, draw_y):
        transition = getattr(self, 'rest_transition', None) or {}
        spot_id = transition.get('spot_id') or getattr(self, 'active_rest_spot_id', None) or getattr(self, 'target_spot_id', None)
        width, height = sprite.get_size()
        role = getattr(self, 'current_anim', '')
        spot = next((s for s in self.cfg.get('interaction_spots', []) if s.get('id') == spot_id), {}) if hasattr(self, 'cfg') else {}
        vector = spot.get('vector_offsets', {}).get(self.cfg.get('active_character'), {}).get(role) if hasattr(self, 'cfg') else None
        flip = getattr(self, 'facing_left', False)
        outlines = foreground_outlines(self.obstacles, self.char_x, self.char_y, role, spot_id, (draw_x, draw_y, width, height, flip), vector)
        outlines = [p for p in outlines if max(v[0] for v in p) >= draw_x and min(v[0] for v in p) <= draw_x+width
                    and max(v[1] for v in p) >= draw_y and min(v[1] for v in p) <= draw_y+height]
        if not outlines:
            return sprite
        # Clear only character pixels covered by foreground artwork. Do not redraw the
        # background, which would erase other overlays or apply daylight twice.
        mask = pygame.Surface((width,height), pygame.SRCALPHA)
        mask.fill((255,255,255,255))
        for points in outlines:
            pygame.draw.polygon(mask,(0,0,0,0),[(round(x-draw_x),round(y-draw_y)) for x,y in points])
        result = sprite.copy()
        result.blit(mask,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
        return result

    def draw_editor_overlay(self):
        p_bl = (self.trap["back_x_min"], self.trap["y_min"])
        p_br = (self.trap["back_x_max"], self.trap["y_min"])
        p_fr = (self.trap["front_x_max"], self.trap["y_max"])
        p_fl = (self.trap["front_x_min"], self.trap["y_max"])

        floor = self.floor_navigation().floor
        # Fill semi-transparent floor polygon
        poly_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        pygame.draw.polygon(poly_surf, (0, 200, 255, 55), floor)
        pygame.draw.polygon(poly_surf, (0, 255, 255, 220), floor, 3)
        self.screen.blit(poly_surf, (0, 0))

        # Draw Obstacles (Red zones)
        for idx, obs in enumerate(self.obstacles):
            is_sel = (self.active_obstacle_idx == idx)
            obs_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            pygame.draw.polygon(obs_surf, (217, 87, 99, 110 if is_sel else 70), obstacle_points(obs))
            self.screen.blit(obs_surf, (0, 0))
            
            border_col = (255, 220, 0) if is_sel else self.palette["red"]
            pygame.draw.polygon(self.screen, border_col, obstacle_points(obs), 3 if is_sel else 2)
            
            lbl = self.font_sm.render(obs.get("label", f"Block {idx+1}"), True, (255, 255, 255))
            self.screen.blit(lbl, (obs["x"] + 8, obs["y"] + 8))

            if is_sel:
                # Bottom-right yellow corner handle for resizing
                handle_rect = (obs["x"] + obs["w"] - 14, obs["y"] + obs["h"] - 14, 14, 14)
                pygame.draw.rect(self.screen, (255, 220, 0), handle_rect, border_radius=2)
                pygame.draw.rect(self.screen, (20, 20, 30), handle_rect, 1)

        # Corner Handles
        handles = [("BL", p_bl), ("BR", p_br), ("FR", p_fr), ("FL", p_fl)]
        if self.trap.get("points"):
            handles = [(f"P{i+1}", (int(x), int(y))) for i, (x,y) in enumerate(floor)]
        for hid, (hx, hy) in handles:
            is_sel = (self.active_handle == hid)
            h_col = (255, 220, 0) if is_sel else (0, 255, 255)
            pygame.draw.circle(self.screen, h_col, (hx, hy), 22 if is_sel else 16)
            pygame.draw.circle(self.screen, (20, 20, 30), (hx, hy), 22 if is_sel else 16, 3)
            lbl = self.font_sm.render(hid, True, (20, 20, 30))
            self.screen.blit(lbl, (hx - lbl.get_width() // 2, hy - lbl.get_height() // 2))

        # Preview Silhouettes at back and front (unless hidden)
        if not self.editor_hide_char:
            back_preview = self.get_perspective_sprite("idle", self.trap["y_min"], False)
            if back_preview:
                bx = (self.trap["back_x_min"] + self.trap["back_x_max"]) // 2
                by = self.trap["y_min"] - back_preview.get_height()
                self.screen.blit(back_preview, (bx - back_preview.get_width() // 2, by))

            front_preview = self.get_perspective_sprite("idle", self.trap["y_max"], False)
            if front_preview:
                fx = (self.trap["front_x_min"] + self.trap["front_x_max"]) // 2
                fy = self.trap["y_max"] - front_preview.get_height()
                self.screen.blit(front_preview, (fx - front_preview.get_width() // 2, fy))

        # Editor Top Tool Bar
        ed_bar = pygame.Surface((self.width, 70), pygame.SRCALPHA)
        ed_bar.fill((15, 15, 25, 245))
        self.screen.blit(ed_bar, (0, 0))
        pygame.draw.line(self.screen, (0, 255, 255), (0, 70), (self.width, 70), 2)

        # [DONE] Button
        pygame.draw.rect(self.screen, (0, 180, 210), self.ed_done_rect, border_radius=8)
        d_lbl = self.font_md.render("DONE", True, (20, 20, 30))
        self.screen.blit(d_lbl, (self.ed_done_rect.centerx - d_lbl.get_width() // 2, self.ed_done_rect.centery - d_lbl.get_height() // 2))

        # [SAVE] Button
        save_col = self.palette["green"] if self.save_feedback_timer <= 0 else (255, 220, 0)
        pygame.draw.rect(self.screen, save_col, self.ed_save_rect, border_radius=8)
        s_lbl = self.font_md.render("SAVED!" if self.save_feedback_timer > 0 else "SAVE", True, (20, 20, 30))
        self.screen.blit(s_lbl, (self.ed_save_rect.centerx - s_lbl.get_width() // 2, self.ed_save_rect.centery - s_lbl.get_height() // 2))

        # Back Scale controls
        pygame.draw.rect(self.screen, self.palette["surface_light"], self.ed_back_minus, border_radius=6)
        self.screen.blit(self.font_md.render("-", True, self.palette["text"]), (self.ed_back_minus.x + 11, self.ed_back_minus.y + 6))
        b_txt = self.font_sm.render(f"B:{self.trap['scale_at_y_min']}px", True, (0, 255, 255))
        self.screen.blit(b_txt, (self.ed_back_minus.right + 4, 26))
        pygame.draw.rect(self.screen, self.palette["surface_light"], self.ed_back_plus, border_radius=6)
        self.screen.blit(self.font_md.render("+", True, self.palette["text"]), (self.ed_back_plus.x + 9, self.ed_back_plus.y + 6))

        # Front Scale controls
        pygame.draw.rect(self.screen, self.palette["surface_light"], self.ed_front_minus, border_radius=6)
        self.screen.blit(self.font_md.render("-", True, self.palette["text"]), (self.ed_front_minus.x + 11, self.ed_front_minus.y + 6))
        f_txt = self.font_sm.render(f"F:{self.trap['scale_at_y_max']}px", True, (255, 220, 0))
        self.screen.blit(f_txt, (self.ed_front_minus.right + 4, 26))
        pygame.draw.rect(self.screen, self.palette["surface_light"], self.ed_front_plus, border_radius=6)
        self.screen.blit(self.font_md.render("+", True, self.palette["text"]), (self.ed_front_plus.x + 9, self.ed_front_plus.y + 6))

        # [HIDE/SHOW CHAR]
        char_btn_col = self.palette["surface_light"] if not self.editor_hide_char else self.palette["accent"]
        char_txt_col = self.palette["text"] if not self.editor_hide_char else (20, 20, 30)
        pygame.draw.rect(self.screen, char_btn_col, self.ed_toggle_char_rect, border_radius=8)
        char_lbl = self.font_sm.render("HIDE CHAR" if not self.editor_hide_char else "SHOW CHAR", True, char_txt_col)
        self.screen.blit(char_lbl, (self.ed_toggle_char_rect.centerx - char_lbl.get_width() // 2, self.ed_toggle_char_rect.centery - char_lbl.get_height() // 2))

        # [+ BLOCK] & [DEL BLOCK]
        pygame.draw.rect(self.screen, self.palette["surface_light"], self.ed_add_block_rect, border_radius=8)
        ab_lbl = self.font_sm.render("+ BLOCK", True, self.palette["accent"])
        self.screen.blit(ab_lbl, (self.ed_add_block_rect.centerx - ab_lbl.get_width() // 2, self.ed_add_block_rect.centery - ab_lbl.get_height() // 2))

        if self.active_obstacle_idx is not None:
            pygame.draw.rect(self.screen, self.palette["red"], self.ed_del_block_rect, border_radius=8)
            db_lbl = self.font_sm.render("DEL BLOCK", True, self.palette["text"])
            self.screen.blit(db_lbl, (self.ed_del_block_rect.centerx - db_lbl.get_width() // 2, self.ed_del_block_rect.centery - db_lbl.get_height() // 2))

            # Selected block W/H controls
            obs = self.obstacles[self.active_obstacle_idx]
            pygame.draw.rect(self.screen, self.palette["surface_light"], self.ed_w_minus, border_radius=4)
            self.screen.blit(self.font_sm.render("-", True, self.palette["text"]), (self.ed_w_minus.x + 9, self.ed_w_minus.y + 8))
            w_txt = self.font_sm.render(f"W:{obs['w']}", True, (255, 220, 0))
            self.screen.blit(w_txt, (self.ed_w_minus.right + 4, 26))
            pygame.draw.rect(self.screen, self.palette["surface_light"], self.ed_w_plus, border_radius=4)
            self.screen.blit(self.font_sm.render("+", True, self.palette["text"]), (self.ed_w_plus.x + 8, self.ed_w_plus.y + 8))

            pygame.draw.rect(self.screen, self.palette["surface_light"], self.ed_h_minus, border_radius=4)
            self.screen.blit(self.font_sm.render("-", True, self.palette["text"]), (self.ed_h_minus.x + 9, self.ed_h_minus.y + 8))
            h_txt = self.font_sm.render(f"H:{obs['h']}", True, (255, 220, 0))
            self.screen.blit(h_txt, (self.ed_h_minus.right + 4, 26))
            pygame.draw.rect(self.screen, self.palette["surface_light"], self.ed_h_plus, border_radius=4)
            self.screen.blit(self.font_sm.render("+", True, self.palette["text"]), (self.ed_h_plus.x + 8, self.ed_h_plus.y + 8))

        # Instructions Banner at bottom
        inst_surf = pygame.Surface((self.width, 36), pygame.SRCALPHA)
        inst_surf.fill((15, 15, 25, 235))
        self.screen.blit(inst_surf, (0, self.height - 36))
        inst_txt = self.font_sm.render(f"EDITOR: Drag handles/blocks. Drag yellow corner to resize. Web Studio: {self.studio_url}", True, (200, 240, 255))
        self.screen.blit(inst_txt, (self.width // 2 - inst_txt.get_width() // 2, self.height - 28))

    def draw(self):
        if getattr(self, "display_power", None) and self.display_power.is_off:
            return


        # Shared solar cycle for every scene, using local timezone and configured location.
        lighting = lighting_state(self.cfg.get('lighting', {}))
        night = lighting['night']
        self.lighting_night_amount = night
        if self.bg_day:
            self.screen.blit(self.bg_day, (0, 0))
        else:
            self.screen.fill(self.palette["background"])
        night_background = getattr(self, 'lighting_night', None)
        if night_background is not None and night > 0:
            night_background.set_alpha(round(255*night))
            self.screen.blit(night_background, (0, 0))
        # Study-specific stars/windows must never appear over another scene.
        if scene_id(self.cfg) == 'cozy_study' and night >= .95 and self.bg_night:
            # Dynamic twinkling stars across the night sky in the arched window
            t = time.time()
            stars = [
                (485, 125), (520, 85), (575, 75), (630, 80), (690, 95), (725, 130),
                (505, 155), (550, 130), (610, 120), (665, 135), (710, 160),
                (535, 175), (590, 165), (645, 160), (685, 180)
            ]
            for i, (sx, sy) in enumerate(stars):
                twinkle = int(160 + 85 * math.sin(t * 2.8 + i * 1.9))
                pygame.draw.circle(self.screen, (225, 235, 255, twinkle), (sx, sy), 1 if i % 2 == 0 else 2)

            # Warm glowing amber lit windows in the distant night city buildings!
            pygame.draw.rect(self.screen, (255, 215, 110), (495, 245, 5, 7))
            pygame.draw.rect(self.screen, (255, 215, 110), (550, 230, 6, 8))
            pygame.draw.rect(self.screen, (255, 200, 90),  (615, 255, 5, 7))
            pygame.draw.rect(self.screen, (255, 220, 100), (670, 240, 6, 8))
            pygame.draw.rect(self.screen, (255, 205, 95),  (705, 250, 5, 7))

        if scene_id(self.cfg) == 'cozy_study' and night > 0:
            tint = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            tint.fill((12, 16, 38, round(55*night)))
            self.screen.blit(tint, (0, 0))
        if lighting['twilight'] > 0:
            tint = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            tint.fill((215, 110, 70, round(40*lighting['twilight'])))
            self.screen.blit(tint, (0, 0))

        if self.edit_mode:
            self.draw_editor_overlay()
            if getattr(self, 'desktop_mode', False) and hasattr(self, 'desktop_helper'):
                self.desktop_helper.render(self.screen, self.window, getattr(self.display_power, 'is_off', False), getattr(self, 'font_sm', None))
            pygame.display.flip()
            return

        # Draw Active Prop Overlays (Pulsing rings, digital LCD badges, alert icons, CRT scanlines, sticky notes)
        now = time.time()
        expired_pids = []
        for pid, ov in list(self.active_prop_overlays.items()):
            if now - ov["start_time"] > ov.get("duration", 20.0):
                expired_pids.append(pid)
                continue

            prop = next((p for p in self.props if p.get("id") == pid), None)
            if not prop:
                continue

            px, py = prop["x"], prop["y"]
            col = tuple(ov.get("color", (0, 229, 255)))
            effect = ov.get("effect", "pulse_beacon")
            text = ov.get("text", "")
            elapsed = now - ov["start_time"]

            if effect in ["pulse_beacon", "glow_pulse"]:
                pulse_phase = (elapsed * 3.5) % 1.0
                r1 = int(14 + pulse_phase * 32)
                a1 = max(10, int(220 * (1.0 - pulse_phase)))
                ring_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
                pygame.draw.circle(ring_surf, (*col, a1), (px, py), r1, 3)
                pygame.draw.circle(ring_surf, (*col, 200), (px, py), 9)
                self.screen.blit(ring_surf, (0, 0))

            elif effect in ["value_badge", "price_badge", "badge"]:
                osc = int(180 + 75 * math.sin(now * 5.0))
                tag_str = f"[ {text} ]" if not text.startswith("[") else text
                txt_surf = self.font_md.render(tag_str, True, (255, 255, 255))
                pad_w = 14
                bw = txt_surf.get_width() + pad_w * 2
                bh = 34
                bx = max(10, min(self.width - bw - 10, px - bw // 2))
                by = max(80, py - 48)

                badge_bg = pygame.Surface((bw, bh), pygame.SRCALPHA)
                badge_bg.fill((16, 14, 28, 235))
                self.screen.blit(badge_bg, (bx, by))
                pygame.draw.rect(self.screen, (*col, osc), (bx, by, bw, bh), 2, border_radius=6)
                self.screen.blit(txt_surf, (bx + pad_w, by + 5))

                # Little retro indicator pin pointing down to prop
                pygame.draw.polygon(self.screen, col, [(px, py - 10), (px - 5, by + bh), (px + 5, by + bh)])

            elif effect == "alert_icon":
                bob = int(math.sin(now * 5.0) * 5)
                ax, ay = px, py - 42 + bob
                badge_surf = pygame.Surface((32, 32), pygame.SRCALPHA)
                pygame.draw.circle(badge_surf, (217, 87, 99, 240), (16, 16), 14)
                pygame.draw.circle(badge_surf, (255, 255, 255), (16, 16), 14, 2)
                self.screen.blit(badge_surf, (ax - 16, ay - 16))
                excl = self.font_md.render("!", True, (255, 255, 255))
                self.screen.blit(excl, (ax - excl.get_width() // 2, ay - excl.get_height() // 2))

            elif effect == "screen_glow":
                glow_surf = pygame.Surface((60, 44), pygame.SRCALPHA)
                glow_alpha = int(120 + 40 * math.sin(now * 8.0))
                glow_surf.fill((*col, glow_alpha))
                self.screen.blit(glow_surf, (px - 30, py - 38))
                for sy in range(py - 38, py + 6, 4):
                    pygame.draw.line(self.screen, (10, 20, 20, 180), (px - 30, sy), (px + 30, sy), 1)

            elif effect == "sticky_note":
                note_w, note_h = 75, 52
                nx, ny = px - note_w // 2, py - 55
                note_surf = pygame.Surface((note_w, note_h), pygame.SRCALPHA)
                note_surf.fill((255, 235, 120, 240))
                self.screen.blit(note_surf, (nx, ny))
                pygame.draw.rect(self.screen, (200, 170, 60), (nx, ny, note_w, note_h), 1)
                pygame.draw.circle(self.screen, (217, 87, 99), (nx + note_w // 2, ny + 4), 3)
                if text:
                    ntxt = self.font_sm.render(text[:10], True, (40, 30, 10))
                    self.screen.blit(ntxt, (nx + 6, ny + 16))

        for epid in expired_pids:
            self.active_prop_overlays.pop(epid, None)

        from prop_runtime import draw_props
        draw_props(self, False)
        self.draw_typing_screens()

        # Normal Mode: Character Movement & Drawing
        dx = self.target_x - self.char_x
        dy = self.target_y - self.char_y
        is_moving = (dx**2 + dy**2)**0.5 > 0.01

        bob_offset = 0
        active_sprite_name = None
        flip = self.facing_left
        transition = getattr(self, 'rest_transition', None)
        if getattr(self, 'speech_reaction', None):
            from speech_reaction import frame
            name = frame(self.speech_reaction)
            flip = False
            sprite_surf = self.get_perspective_sprite(name, self.char_y, flip)
            active_sprite_name = name
        elif getattr(self, 'sensor_reaction', None):
            from sensor_reaction import frame
            name = frame(self.sensor_reaction)
            flip = self.sensor_reaction['facing_left']
            sprite_surf = self.get_perspective_sprite(name, self.char_y, flip)
            active_sprite_name = name
        elif transition:
            sequence = self.character_sequences[transition['role']]
            tick = int((time.monotonic()-transition['started'])*sequence['fps'])
            name = sequence['frames'][min(tick,len(sequence['frames'])-1)]
            sprite_surf = self.get_perspective_sprite(name,self.char_y,self.facing_left)
            active_sprite_name = name
        elif getattr(self, 'active_rest_role', None):
            name = self.gesture_sprite_name(self.active_rest_role)
            sprite_surf = self.get_perspective_sprite(name,self.char_y,self.facing_left)
            active_sprite_name = name
        elif is_moving:
            self.gesture_role = None
            walk_name = self.walking_sprite_name()
            flip = self.facing_left and (getattr(self, 'motion_direction', 'side') == 'side' or
                    'walk_' + self.motion_direction not in getattr(self, 'character_sequences', {}))
            sprite_surf = self.get_perspective_sprite(walk_name, self.char_y, flip)
        elif self.current_anim not in ('idle', 'walk') and self.current_anim in getattr(self, 'character_sequences', {}):
            gesture_name = self.gesture_sprite_name(self.current_anim)
            flip = self.facing_left
            sprite_surf = self.get_perspective_sprite(gesture_name, self.char_y, flip)
            active_sprite_name = gesture_name
        elif self.current_anim == 'idle' or self.current_anim not in self.raw_sprites:
            if self.current_anim != 'idle':
                self.gesture_role = None
            idle_name = self.idle_sprite_name()
            flip = self.facing_left and (getattr(self, 'motion_direction', 'side') == 'side' or
                    'idle_' + self.motion_direction not in getattr(self, 'character_sequences', {}))
            sprite_surf = self.get_perspective_sprite(idle_name, self.char_y, flip)
        elif self.current_anim in self.raw_sprites:
            sprite_surf = self.get_perspective_sprite(self.current_anim, self.char_y, self.facing_left)
        elif self.is_inspecting:
            sprite_surf = self.get_perspective_sprite("inspect", self.char_y, self.facing_left)
        else:
            sprite_surf = self.get_perspective_sprite("idle", self.char_y, self.facing_left)

        if sprite_surf:
            anchor = getattr(self, 'sprite_metrics', {}).get(active_sprite_name, {}).get('anchor_x', 0.5)
            if flip:
                anchor = 1-anchor
            draw_x = int(self.char_x - sprite_surf.get_width() * anchor)
            draw_y = int(self.char_y - sprite_surf.get_height() + bob_offset)
            self.character_touch_rect = pygame.Rect(draw_x, draw_y, sprite_surf.get_width(), sprite_surf.get_height())
            self.screen.blit(self.foreground_sprite(sprite_surf, draw_x, draw_y), (draw_x, draw_y))

            # Floating z Z Z particles when sleeping
            if self.current_anim == "sleeping" and not getattr(self, 'speech_reaction', None):
                t = time.time()
                from sleep_effects import particle_origin
                head_x, head_y = particle_origin(draw_x, draw_y, sprite_surf.get_width(), sprite_surf.get_height(),
                    getattr(self, 'sprite_metrics', {}).get(active_sprite_name, {}).get('head_anchor'), flip,
                    getattr(self, 'sprite_metrics', {}).get(active_sprite_name, {}).get('head_radius', .1))
                for i in range(3):
                    p_offset = (t * 24 + i * 20) % 65
                    p_x = int(head_x + math.sin(t * 2.5 + i) * 10)
                    p_y = int(head_y - p_offset)
                    p_alpha = max(20, int(255 * (1.0 - p_offset / 65)))
                    letter = ["z", "Z", "Z"][i]
                    z_surf = (self.font_sm if i == 0 else (self.font_md if i == 1 else self.font_lg)).render(letter, True, (160, 195, 255))
                    z_surf.set_alpha(p_alpha)
                    self.screen.blit(z_surf, (p_x, p_y))

            active = getattr(getattr(self, 'activity_queue', None), 'active', None)
            queue = getattr(self, 'activity_queue', None)
            activity_visible = bool(active and queue.arrived is not None and not self.is_sleeping
                and not getattr(self, 'scene_journey', None) and not getattr(self, 'journey_arriving', False)
                and not getattr(self, 'rest_transition', None) and self.current_anim != 'walk')
            show_label = activity_visible and not getattr(self, 'sensor_reaction', None) and not active[0].get('hide_label') and not (active[0].get('display_mode') in ('thought_bubble', 'popup_modal')
                and active[0].get('message_label_mode') == 'message_only')
            if show_label:
                source = active[0].get('source_event') or active[0].get('event') or active[0].get('label') or 'Activity'
                label = str(active[1]) + ' - ' + str(source).replace('_', ' ').capitalize()
                while self.font_md.size(label)[0] > self.width-80 and len(label) > 4:
                    label = label[:-4] + '...'
                text = self.font_md.render(label, True, self.palette['text'])
                width = text.get_width()+24
                x = max(20, min(self.width-width-20, int(self.char_x-width/2)))
                has_message = self.status_msg and time.monotonic() < getattr(self, 'speech_until', 0)
                y = max(80, draw_y-(112 if has_message else 60))
                background = pygame.Surface((width, 44), pygame.SRCALPHA)
                background.fill((24, 20, 37, 235))
                self.screen.blit(background, (x, y))
                pygame.draw.rect(self.screen, active[2], (x, y, width, 44), 2, border_radius=8)
                self.screen.blit(text, (x+12, y+(44-text.get_height())//2))

            if (not active or (activity_visible and active[0].get('display_mode') == 'thought_bubble')) and self.status_msg and time.monotonic() < getattr(self, "speech_until", 0):
                msg_text = str(self.status_msg)
                max_text_w = min(680, self.width - 80)
                lines = []
                for p in msg_text.split("\n"):
                    words = p.split()
                    cur = ""
                    for w in words:
                        test = f"{cur} {w}".strip()
                        if self.font_md.size(test)[0] <= max_text_w:
                            cur = test
                        else:
                            if cur: lines.append(cur)
                            cur = w
                    if cur: lines.append(cur)
                if not lines: lines = [""]

                line_h = max(26, self.font_md.get_linesize())
                pad_y = 12
                bubble_h = max(52, len(lines) * line_h + pad_y * 2)
                longest = max(self.font_md.size(l)[0] for l in lines)
                bubble_w = max(220, min(self.width - 60, longest + 44))
                bubble_x = max(20, min(self.width - bubble_w - 20, int(self.char_x - bubble_w // 2)))
                bubble_y = max(76, draw_y - bubble_h - 14)

                bubble_surf = pygame.Surface((bubble_w, bubble_h), pygame.SRCALPHA)
                bubble_surf.fill((24, 20, 37, 235))
                self.screen.blit(bubble_surf, (bubble_x, bubble_y))
                pygame.draw.rect(self.screen, self.palette["accent"], (bubble_x, bubble_y, bubble_w, bubble_h), 2, border_radius=12)

                for idx, line in enumerate(lines):
                    line_surf = self.font_md.render(line, True, self.palette["text"])
                    self.screen.blit(line_surf, (bubble_x + bubble_w // 2 - line_surf.get_width() // 2, bubble_y + pad_y + idx * line_h))

            v_bubble = getattr(self, 'voice_thought_bubble', None)
            if v_bubble and time.monotonic() < v_bubble.get('expires_at', 0):
                v_text = str(v_bubble.get('text', ''))
                is_listening = getattr(self, 'voice_listening', False)
                max_content_w = min(740, self.width - 60)
                extra_pad_x = 52 if is_listening else 36
                max_text_w = max_content_w - extra_pad_x

                lines = []
                for p in v_text.split("\n"):
                    words = p.split()
                    cur = ""
                    for w in words:
                        test = f"{cur} {w}".strip()
                        if self.font_md.size(test)[0] <= max_text_w:
                            cur = test
                        else:
                            if cur: lines.append(cur)
                            cur = w
                    if cur: lines.append(cur)
                if not lines: lines = [""]

                line_h = max(26, self.font_md.get_linesize())
                pad_y = 12
                bubble_h = max(52, len(lines) * line_h + pad_y * 2)
                longest = max(self.font_md.size(l)[0] for l in lines)
                bubble_w = max(220, min(max_content_w, longest + extra_pad_x))
                bubble_x = max(20, min(self.width - bubble_w - 20, int(self.char_x - bubble_w // 2)))
                bubble_y = max(76, draw_y - bubble_h - 14)

                bubble_surf = pygame.Surface((bubble_w, bubble_h), pygame.SRCALPHA)
                bubble_surf.fill((28, 22, 45, 240))
                self.screen.blit(bubble_surf, (bubble_x, bubble_y))

                border_color = (255, 80, 80) if is_listening else self.palette.get("accent", (140, 100, 255))
                pygame.draw.rect(self.screen, border_color, (bubble_x, bubble_y, bubble_w, bubble_h), 2, border_radius=12)

                if is_listening:
                    pulse = int(128 + 127 * math.sin(time.monotonic() * 8))
                    pygame.draw.circle(self.screen, (255, pulse, pulse), (bubble_x + 18, bubble_y + pad_y + line_h // 2), 6)
                    txt_x = bubble_x + 34
                else:
                    txt_x = bubble_x + 18

                for idx, line in enumerate(lines):
                    v_surf = self.font_md.render(line, True, (255, 255, 255))
                    self.screen.blit(v_surf, (txt_x, bubble_y + pad_y + idx * line_h))

        draw_props(self, True)

        # Scene artwork fills the display; header text has no opaque backing.
        scene = self.cfg.get('scenes', {}).get(scene_id(self.cfg), {})
        header_colors = scene.get('header_colors', {})
        def header_color(key, fallback):
            value = header_colors.get(key, fallback) if isinstance(header_colors, dict) else fallback
            try:
                return pygame.Color(value) if isinstance(value, str) and len(value) == 7 and value.startswith('#') else pygame.Color(fallback)
            except ValueError:
                return pygame.Color(fallback)
        header_text_color = header_color('night' if night >= .5 else 'day', '#ffffff')
        def header_text(text, font, pos):
            # A small contrasting outline keeps text legible over detailed artwork.
            luminance = sum(header_text_color[:3]) / 3
            outline = (12, 12, 20) if luminance > 128 else (245, 245, 255)
            shadow = font.render(text, True, outline)
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                self.screen.blit(shadow, (pos[0]+dx, pos[1]+dy))
            self.screen.blit(font.render(text, True, header_text_color), pos)

        # Pull-down controls; the scene remains visible underneath.
        if self.top_controls_open:
            panel = pygame.Surface((self.width, 68), pygame.SRCALPHA)
            panel.fill((24, 20, 37, 240))
            self.screen.blit(panel, (0, 68))
            pygame.draw.line(self.screen, self.palette["border"], (0, 136), (self.width, 136), 2)
            # Top-Left [KEYS] Toggle
            if self.quick_keys_mode == "always":
                btn_col = self.palette["accent"]
                keys_text = "KEYS: ON"
            elif self.quick_keys_mode == "never":
                btn_col = (50, 45, 65)
                keys_text = "KEYS: OFF"
            else:
                btn_col = self.palette["surface_light"]
                keys_text = "KEYS: AUTO"
            pygame.draw.rect(self.screen, btn_col, self.btn_keys_rect, border_radius=8)
            pygame.draw.rect(self.screen, self.palette["border"], self.btn_keys_rect, 2, border_radius=8)
            keys_lbl = self.font_sm.render(keys_text, True, self.palette["text"])
            self.screen.blit(keys_lbl, (self.btn_keys_rect.centerx - keys_lbl.get_width() // 2,
                                        self.btn_keys_rect.centery - keys_lbl.get_height() // 2))

            # [EDIT] Button
            pygame.draw.rect(self.screen, self.palette["surface_light"], self.btn_edit_rect, border_radius=8)
            pygame.draw.rect(self.screen, self.palette["border"], self.btn_edit_rect, 2, border_radius=8)
            edit_lbl = self.font_sm.render("EDIT", True, (0, 255, 255))
            self.screen.blit(edit_lbl, (self.btn_edit_rect.centerx - edit_lbl.get_width() // 2,
                                        self.btn_edit_rect.centery - edit_lbl.get_height() // 2))

            # [TEXT SIZE] Button (Cycles STD -> L -> XL)
            pygame.draw.rect(self.screen, self.palette["surface_light"], self.btn_font_rect, border_radius=8)
            pygame.draw.rect(self.screen, (255, 220, 0), self.btn_font_rect, 2, border_radius=8)
            tag_scale = "XL" if self.ui_font_scale == "extra_large" else ("L" if self.ui_font_scale == "large" else "STD")
            font_btn_lbl = self.font_sm.render(f"TEXT: {tag_scale}", True, (255, 220, 0))
            self.screen.blit(font_btn_lbl, (self.btn_font_rect.centerx - font_btn_lbl.get_width() // 2,
                                            self.btn_font_rect.centery - font_btn_lbl.get_height() // 2))

        title = self.font_lg.render("DESK-PAL", True, header_text_color)
        header_text("DESK-PAL", self.font_lg, (16, 14))

        # Voice activity indicator next to DESK-PAL title
        is_wake = getattr(self, 'wake_word_active', False)
        is_voice_active = is_wake or getattr(self, 'voice_listening', False) or (hasattr(self, 'voice_sentry') and self.voice_sentry and self.voice_sentry.state in ('listening', 'transcribing'))
        is_hearing = getattr(self, 'voice_hearing', False)

        dot_x = 16 + title.get_width() + 16
        dot_y = 14 + title.get_height() // 2

        if is_voice_active:
            pulse = (math.sin(time.time() * 8) + 1) * 0.5
            radius = int(5 + pulse * 2)
            glow_surf = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (46, 204, 113, int(60 + pulse * 100)), (radius * 2, radius * 2), radius * 2)
            self.screen.blit(glow_surf, (dot_x - radius * 2, dot_y - radius * 2))
            pygame.draw.circle(self.screen, (46, 230, 113), (dot_x, dot_y), radius)

            # Prominently show "HEY PAL" text badge
            hey_lbl = self.font_sm.render("HEY PAL", True, (46, 230, 113))
            bw = hey_lbl.get_width() + 14
            bh = hey_lbl.get_height() + 6
            bx = dot_x + 14
            by = dot_y - bh // 2
            badge_bg = pygame.Surface((bw, bh), pygame.SRCALPHA)
            badge_bg.fill((16, 40, 26, 220))
            self.screen.blit(badge_bg, (bx, by))
            pygame.draw.rect(self.screen, (46, 230, 113), (bx, by, bw, bh), 1, border_radius=6)
            self.screen.blit(hey_lbl, (bx + 7, by + 3))

        elif is_hearing:
            # Immediate feedback while speaking before wake verification completes
            pulse = (math.sin(time.time() * 12) + 1) * 0.5
            radius = int(4 + pulse * 2)
            pygame.draw.circle(self.screen, (0, 229, 255), (dot_x, dot_y), radius)
            hear_lbl = self.font_sm.render("...", True, (0, 229, 255))
            self.screen.blit(hear_lbl, (dot_x + 10, dot_y - hear_lbl.get_height() // 2))
        if self.top_controls_open:
            studio_url = self.font_sm.render(f"Studio: {self.studio_url}", True, self.palette["green"])
            self.screen.blit(studio_url, (358, 92))

        curr_time = time.strftime("%I:%M %p")
        header_text(curr_time, self.font_md, (self.width - 240, 20))
        pygame.draw.rect(self.screen, header_text_color, self.btn_exit_rect, 2, border_radius=8)
        exit_lbl = self.font_md.render("EXIT", True, header_text_color)
        header_text("EXIT", self.font_md, (self.btn_exit_rect.centerx - exit_lbl.get_width() // 2,
                                             self.btn_exit_rect.centery - exit_lbl.get_height() // 2))

        # Bottom Hardware Switches Bar (if toggled)
        if self.show_quick_keys:
            tile_w = (self.width - 80) // 6
            now = time.time()
            for i, sw in enumerate(self.switches):
                rect = pygame.Rect(40 + i * tile_w, self.height - 110, tile_w - 12, 80)
                is_active = (now - self.switch_press_times[sw["id"]] < 0.6)
                bg_col = self.palette["surface_light"] if is_active else self.palette["surface"]
                border_col = tuple(sw["color"]) if is_active else self.palette["border"]
                
                pygame.draw.rect(self.screen, bg_col, rect, border_radius=10)
                pygame.draw.rect(self.screen, border_col, rect, 2 if not is_active else 4, border_radius=10)

                lbl_key = self.font_sm.render(f"SW {sw['id']}", True, tuple(sw["color"]))
                lbl_name = self.font_md.render(sw["name"], True, self.palette["text"])
                lbl_pin = self.font_sm.render(f"P{sw['pin']}", True, self.palette["text_dim"])

                self.screen.blit(lbl_key, (rect.x + 10, rect.y + 8))
                self.screen.blit(lbl_pin, (rect.right - lbl_pin.get_width() - 10, rect.y + 8))
                self.screen.blit(lbl_name, (rect.centerx - lbl_name.get_width() // 2, rect.y + 38))

        # Retro SCUMM Popup Modal Card
        modal = self.active_popup_modal
        if modal and modal.get('expires_at') and time.monotonic() > modal['expires_at']:
            self.active_popup_modal = None
            modal = None

        if modal and not self.show_shutdown_modal:
            dim_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            dim_surf.fill((10, 8, 20, 185))
            self.screen.blit(dim_surf, (0, 0))

            is_wellness = (modal.get('layout') == 'wellness' or modal.get('wellness') is not None)
            dash = parse_dashboard_modal(modal) if modal.get('layout') != 'classic' and not is_wellness else {'layout': 'classic'}
            is_morning = (dash.get('layout') == 'morning' or modal.get('layout') == 'morning' or 'MORNING' in str(modal.get('title', '')).upper() or modal.get('is_morning_greeting')) and not is_wellness
            is_dash = (dash.get('layout') == 'dashboard') and not is_morning

            card_w = min(1040, self.width - 40) if is_morning else min(960, self.width - 80)
            card_h = 520 if is_morning else (460 if is_wellness else (440 if is_dash else min(540, self.height - 90)))
            card_x = self.width // 2 - card_w // 2
            card_y = self.height // 2 - card_h // 2
            m_col = (255, 175, 40) if is_morning else tuple(modal.get("color", (0, 229, 255)))

            bg_col = self.palette.get("background", (24, 20, 37))
            surf_col = self.palette.get("surface", (38, 43, 68))
            border_col = self.palette.get("border", (90, 105, 136))
            card_radius = self.cfg.get("card_style", {}).get("border_radius", 14)

            card_bg = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
            card_bg.fill((bg_col[0], bg_col[1], bg_col[2], 252))
            self.screen.blit(card_bg, (card_x, card_y))
            pygame.draw.rect(self.screen, m_col, (card_x, card_y, card_w, card_h), 3, border_radius=card_radius)
            pygame.draw.rect(self.screen, border_col, (card_x + 5, card_y + 5, card_w - 10, card_h - 10), 1, border_radius=max(6, card_radius - 4))

            header_h = 56 if is_morning else 52
            h_surf = pygame.Surface((card_w - 10, header_h), pygame.SRCALPHA)
            h_surf.fill((surf_col[0], surf_col[1], surf_col[2], 240))
            self.screen.blit(h_surf, (card_x + 5, card_y + 5))
            pygame.draw.line(self.screen, m_col, (card_x + 5, card_y + header_h + 5), (card_x + card_w - 5, card_y + header_h + 5), 2)

            raw_title = modal.get("title", "STATUS")
            if " - " in raw_title:
                raw_title = raw_title.split(" - ")[0].strip()
            title_txt = self.font_lg.render(raw_title, True, m_col)
            self.screen.blit(title_txt, (card_x + 24, card_y + 12))

            if is_wellness:
                # Specialized Graphic Wellness & Hydration Card (30/70 layout)
                body_y = card_y + 66
                body_w = card_w - 48
                gap = 18
                pw_hyd = int((body_w - gap) * 0.30)
                pw_str = (body_w - gap) - pw_hyd
                ph = 252
                p1_x = card_x + 24
                p2_x = p1_x + pw_hyd + gap

                # --- Panel 1: Hydration (30%) ---
                p1_rect = pygame.Rect(p1_x, body_y, pw_hyd, ph)
                pygame.draw.rect(self.screen, self.palette["surface"], p1_rect, border_radius=12)
                pygame.draw.rect(self.screen, (56, 189, 248), p1_rect, 1, border_radius=12)

                # Header Pill Badge
                b1_txt = self.font_sm.render("HYDRATION", True, (255, 255, 255))
                b1_w = b1_txt.get_width() + 24
                b1_rect = pygame.Rect(p1_x + pw_hyd // 2 - b1_w // 2, body_y + 12, b1_w, 26)
                pygame.draw.rect(self.screen, (20, 60, 95), b1_rect, border_radius=13)
                pygame.draw.rect(self.screen, (56, 189, 248), b1_rect, 1, border_radius=13)
                self.screen.blit(b1_txt, (b1_rect.centerx - b1_txt.get_width() // 2, b1_rect.centery - b1_txt.get_height() // 2))

                # Hydration Graphic (Water Glass by itself, centered)
                glass_img = self.get_wellness_sprite('glass')
                if glass_img:
                    gw, gh = glass_img.get_width(), glass_img.get_height()
                    self.screen.blit(glass_img, (p1_x + pw_hyd // 2 - gw // 2, body_y + 50))

                # Hydration Label (Prominent font_md, easily readable)
                h_lbl = self.font_md.render("Drink Water", True, (255, 255, 255))
                self.screen.blit(h_lbl, (p1_x + pw_hyd // 2 - h_lbl.get_width() // 2, body_y + 196))

                # --- Panel 2: Movement & Rest Eyes (70%) ---
                p2_rect = pygame.Rect(p2_x, body_y, pw_str, ph)
                pygame.draw.rect(self.screen, self.palette["surface"], p2_rect, border_radius=12)
                pygame.draw.rect(self.screen, (106, 215, 60), p2_rect, 1, border_radius=12)

                # Header Pill Badge
                b2_txt = self.font_sm.render("STRETCH & REST", True, (255, 255, 255))
                b2_w = b2_txt.get_width() + 24
                b2_rect = pygame.Rect(p2_x + 20, body_y + 12, b2_w, 26)
                pygame.draw.rect(self.screen, (25, 65, 35), b2_rect, border_radius=13)
                pygame.draw.rect(self.screen, (106, 215, 60), b2_rect, 1, border_radius=13)
                self.screen.blit(b2_txt, (b2_rect.centerx - b2_txt.get_width() // 2, b2_rect.centery - b2_txt.get_height() // 2))

                # Animated Stretch Sprite (Cycles breathing stretch frames)
                stretch_img = self.get_wellness_stretch_frame()
                if stretch_img:
                    self.screen.blit(stretch_img, (p2_x + 24, body_y + 52))

                # Actions & Metric Advice (All fonts >= font_md for arm's length reading)
                tx = p2_x + 148
                m_title = self.font_lg.render("Stand Up & Move", True, (255, 255, 255))
                self.screen.blit(m_title, (tx, body_y + 52))

                m_sub = self.font_md.render("Roll shoulders & stretch arms", True, (180, 200, 220))
                self.screen.blit(m_sub, (tx, body_y + 100))

                eye_title = self.font_md.render("20-20-20 Rule (Metric):", True, (56, 189, 248))
                self.screen.blit(eye_title, (tx, body_y + 148))

            elif is_morning:
                # Specialized Dual-Panel Good Morning & Daily Briefing Card
                body_y = card_y + 68
                body_w = card_w - 48
                gap = 20
                pw_weather = int((body_w - gap) * 0.44)
                pw_info = (body_w - gap) - pw_weather
                ph = 380
                p1_x = card_x + 24
                p2_x = p1_x + pw_weather + gap

                # Retrieve weather progression & telemetry
                prog = modal.get('progression')
                weather_tele = self.app_telemetry.get('deskpal_weather', {})
                w_data = weather_tele.get('data', {}) if isinstance(weather_tele, dict) else {}
                if not prog:
                    prog = w_data.get('progression')
                if not prog:
                    prog = {
                        'is_steady': False,
                        'day': {'condition': 'sunny', 'label': 'Sunny', 'temp': 26, 'humidity': 60, 'icon': 'weather_sun'},
                        'night': {'condition': 'clear_night', 'label': 'Clear Night', 'temp': 18, 'humidity': 75, 'icon': 'weather_moon'},
                        'steady': {'condition': 'sunny', 'label': 'Sunny', 'sub': 'All Day & Night', 'temp_min': 18, 'temp_max': 26, 'humidity': 65, 'icon': 'weather_sun'}
                    }

                # Date Pill in Header Top Right (font_md)
                date_str = dash.get('date_str') or modal.get('date_str') or time.strftime("%A, %d %b")
                date_txt = self.font_md.render(date_str, True, (255, 255, 255))
                d_pad_x, d_pad_y = 18, 6
                d_w = date_txt.get_width() + d_pad_x * 2
                d_h = date_txt.get_height() + d_pad_y * 2
                d_x = card_x + card_w - d_w - 20
                d_y = card_y + 10
                pygame.draw.rect(self.screen, (30, 75, 110), (d_x, d_y, d_w, d_h), border_radius=d_h // 2)
                pygame.draw.rect(self.screen, (56, 189, 248), (d_x, d_y, d_w, d_h), 1, border_radius=d_h // 2)
                self.screen.blit(date_txt, (d_x + d_pad_x, d_y + d_pad_y))

                # --- Panel 1: Weather & Sky Progression ---
                p1_rect = pygame.Rect(p1_x, body_y, pw_weather, ph)
                pygame.draw.rect(self.screen, (28, 24, 46), p1_rect, border_radius=12)
                pygame.draw.rect(self.screen, (255, 175, 40), p1_rect, 1, border_radius=12)

                max_panel_text_w = pw_weather - 28

                if prog.get('is_steady'):
                    st = prog.get('steady', {})
                    icon = self.get_weather_sprite(st.get('icon', 'weather_cloudy'), (96, 96))
                    if icon:
                        self.screen.blit(icon, (p1_x + pw_weather // 2 - 48, body_y + 16))

                    # Condition label in font_lg (no subtitle)
                    raw_cond = str(st.get('label', 'Steady Conditions')).replace(' Throughout', '')
                    cond_font = self.font_lg if self.font_lg.size(raw_cond)[0] <= max_panel_text_w else self.font_md
                    cond_txt = cond_font.render(raw_cond, True, (56, 189, 248))
                    self.screen.blit(cond_txt, (p1_x + pw_weather // 2 - cond_txt.get_width() // 2, body_y + 120))

                    # Temperature range in font_hero
                    t_str = f"{st.get('temp_min', 20)}° – {st.get('temp_max', 28)}°C"
                    temp_font = self.font_hero if self.font_hero.size(t_str)[0] <= max_panel_text_w else self.font_lg
                    temp_txt = temp_font.render(t_str, True, (255, 255, 255))
                    self.screen.blit(temp_txt, (p1_x + pw_weather // 2 - temp_txt.get_width() // 2, body_y + 172))
                else:
                    # Shifting Day to Night (2 pictures)
                    sub_w = (pw_weather - 40) // 2
                    day_x = p1_x + 16
                    night_x = p1_x + pw_weather - sub_w - 16

                    day = prog.get('day', {})
                    s_icon = self.get_weather_sprite(day.get('icon', 'weather_sun'), (80, 80))
                    if s_icon:
                        self.screen.blit(s_icon, (day_x + sub_w // 2 - 40, body_y + 16))
                    d_lbl = self.font_md.render("DAYTIME", True, (255, 200, 60))
                    self.screen.blit(d_lbl, (day_x + sub_w // 2 - d_lbl.get_width() // 2, body_y + 104))

                    d_t_str = f"{day.get('temp', 26)}°C"
                    d_t_font = self.font_hero if self.font_hero.size(d_t_str)[0] <= sub_w else self.font_lg
                    d_temp = d_t_font.render(d_t_str, True, (255, 255, 255))
                    self.screen.blit(d_temp, (day_x + sub_w // 2 - d_temp.get_width() // 2, body_y + 138))

                    d_cond_str = str(day.get('label', 'Sunny'))
                    d_cond = self.font_md.render(d_cond_str, True, (210, 225, 240))
                    self.screen.blit(d_cond, (day_x + sub_w // 2 - d_cond.get_width() // 2, body_y + 208))

                    arrow_cx = p1_x + pw_weather // 2
                    arrow_cy = body_y + 58
                    pygame.draw.line(self.screen, (255, 185, 50), (arrow_cx - 16, arrow_cy), (arrow_cx + 8, arrow_cy), 5)
                    pygame.draw.polygon(self.screen, (255, 185, 50), [
                        (arrow_cx + 8, arrow_cy - 10),
                        (arrow_cx + 20, arrow_cy),
                        (arrow_cx + 8, arrow_cy + 10)
                    ])

                    night = prog.get('night', {})
                    m_icon = self.get_weather_sprite(night.get('icon', 'weather_moon'), (80, 80))
                    if m_icon:
                        self.screen.blit(m_icon, (night_x + sub_w // 2 - 40, body_y + 16))
                    n_lbl = self.font_md.render("OVERNIGHT", True, (140, 200, 255))
                    self.screen.blit(n_lbl, (night_x + sub_w // 2 - n_lbl.get_width() // 2, body_y + 104))

                    n_t_str = f"{night.get('temp', 18)}°C"
                    n_t_font = self.font_hero if self.font_hero.size(n_t_str)[0] <= sub_w else self.font_lg
                    n_temp = n_t_font.render(n_t_str, True, (255, 255, 255))
                    self.screen.blit(n_temp, (night_x + sub_w // 2 - n_temp.get_width() // 2, body_y + 138))

                    n_cond_str = str(night.get('label', 'Clear'))
                    n_cond = self.font_md.render(n_cond_str, True, (210, 225, 240))
                    self.screen.blit(n_cond, (night_x + sub_w // 2 - n_cond.get_width() // 2, body_y + 208))

                # --- WEATHER BADGES (Humidity, Rain, UV in prominent font_lg) ---
                import re
                summary_txt = str(modal.get('summary', ''))
                
                # Humidity
                hum_val = None
                if prog.get('is_steady'):
                    hum_val = prog.get('steady', {}).get('humidity')
                else:
                    hum_val = prog.get('day', {}).get('humidity') or prog.get('night', {}).get('humidity')
                if hum_val is None and isinstance(w_data, dict):
                    hum_val = w_data.get('relative_humidity_2m_max') or w_data.get('relative_humidity_2m')
                if hum_val is None:
                    hm = re.search(r'Humidity\s*(\d+)%', summary_txt, re.IGNORECASE)
                    if hm:
                        try: hum_val = float(hm.group(1))
                        except Exception: pass

                rain_chance = prog.get('rain_chance') if isinstance(prog, dict) else None
                if rain_chance is None and isinstance(w_data, dict):
                    rain_chance = w_data.get('precipitation_probability_max')
                if rain_chance is None:
                    rm = re.search(r'Rain\s*(\d+)%', summary_txt, re.IGNORECASE)
                    if rm:
                        try: rain_chance = float(rm.group(1))
                        except Exception: pass

                uv = prog.get('uv') if isinstance(prog, dict) else None
                if uv is None and isinstance(w_data, dict):
                    uv = w_data.get('uv_index_max')
                if uv is None:
                    um = re.search(r'UV\s*([\d\.]+)', summary_txt, re.IGNORECASE)
                    if um:
                        try: uv = float(um.group(1))
                        except Exception: pass

                wind = prog.get('wind') if isinstance(prog, dict) else None
                if wind is None and isinstance(w_data, dict):
                    wind = w_data.get('wind_speed_10m_max')
                if wind is None:
                    wm = re.search(r'Wind up to\s*([\d\.]+)', summary_txt, re.IGNORECASE)
                    if wm:
                        try: wind = float(wm.group(1))
                        except Exception: pass

                badges = []
                if hum_val is not None:
                    badges.append((f"Humidity: {int(hum_val)}%", (56, 189, 248), (20, 50, 80)))
                if rain_chance is not None and rain_chance >= 40:
                    badges.append((f"Rain: {int(rain_chance)}%", (52, 152, 219), (20, 50, 80)))
                if uv is not None and uv >= 6.0:
                    badges.append((f"UV: {uv:.1f}", (243, 156, 18), (80, 50, 15)))
                elif wind is not None and wind >= 25.0:
                    badges.append((f"Wind: {wind:.0f} km/h", (230, 126, 34), (80, 45, 15)))

                badge_font = self.font_lg
                b_h = 46
                b_radius = 23

                if len(badges) == 1:
                    text, border_col, bg_col = badges[0]
                    bw = badge_font.size(text)[0] + 32
                    rect = pygame.Rect(p1_x + pw_weather // 2 - bw // 2, body_y + ph - 64, bw, b_h)
                    pygame.draw.rect(self.screen, bg_col, rect, border_radius=b_radius)
                    pygame.draw.rect(self.screen, border_col, rect, 2, border_radius=b_radius)
                    t_surf = badge_font.render(text, True, (255, 255, 255))
                    self.screen.blit(t_surf, (rect.centerx - t_surf.get_width() // 2, rect.centery - t_surf.get_height() // 2))
                elif len(badges) == 2:
                    tot_w = sum(badge_font.size(b[0])[0] + 28 for b in badges) + 12
                    if tot_w <= pw_weather - 16:
                        bx = p1_x + pw_weather // 2 - tot_w // 2
                        for text, border_col, bg_col in badges:
                            bw = badge_font.size(text)[0] + 28
                            rect = pygame.Rect(bx, body_y + ph - 64, bw, b_h)
                            pygame.draw.rect(self.screen, bg_col, rect, border_radius=b_radius)
                            pygame.draw.rect(self.screen, border_col, rect, 2, border_radius=b_radius)
                            t_surf = badge_font.render(text, True, (255, 255, 255))
                            self.screen.blit(t_surf, (rect.centerx - t_surf.get_width() // 2, rect.centery - t_surf.get_height() // 2))
                            bx += bw + 12
                    else:
                        for idx, (text, border_col, bg_col) in enumerate(badges):
                            bw = badge_font.size(text)[0] + 32
                            by = body_y + ph - 110 + idx * 54
                            rect = pygame.Rect(p1_x + pw_weather // 2 - bw // 2, by, bw, b_h)
                            pygame.draw.rect(self.screen, bg_col, rect, border_radius=b_radius)
                            pygame.draw.rect(self.screen, border_col, rect, 2, border_radius=b_radius)
                            t_surf = badge_font.render(text, True, (255, 255, 255))
                            self.screen.blit(t_surf, (rect.centerx - t_surf.get_width() // 2, rect.centery - t_surf.get_height() // 2))
                else:
                    # 3 Badges: Row 1 Humidity, Row 2 Rain & UV
                    b_text, border_col, bg_col = badges[0]
                    bw = badge_font.size(b_text)[0] + 32
                    rect = pygame.Rect(p1_x + pw_weather // 2 - bw // 2, body_y + ph - 110, bw, b_h)
                    pygame.draw.rect(self.screen, bg_col, rect, border_radius=b_radius)
                    pygame.draw.rect(self.screen, border_col, rect, 2, border_radius=b_radius)
                    t_surf = badge_font.render(b_text, True, (255, 255, 255))
                    self.screen.blit(t_surf, (rect.centerx - t_surf.get_width() // 2, rect.centery - t_surf.get_height() // 2))

                    r2 = badges[1:]
                    tot_w2 = sum(badge_font.size(b[0])[0] + 28 for b in r2) + (len(r2) - 1) * 12
                    bx2 = p1_x + pw_weather // 2 - tot_w2 // 2
                    for text, border_col, bg_col in r2:
                        bw2 = badge_font.size(text)[0] + 28
                        rect2 = pygame.Rect(bx2, body_y + ph - 56, bw2, b_h)
                        pygame.draw.rect(self.screen, bg_col, rect2, border_radius=b_radius)
                        pygame.draw.rect(self.screen, border_col, rect2, 2, border_radius=b_radius)
                        t_surf2 = badge_font.render(text, True, (255, 255, 255))
                        self.screen.blit(t_surf2, (rect2.centerx - t_surf2.get_width() // 2, rect2.centery - t_surf2.get_height() // 2))
                        bx2 += bw2 + 12

                # --- PANEL 2: HERO FUEL CARD (TOP) + ROUTINE / WELLNESS BAR (BOTTOM) ---
                p2_rect = pygame.Rect(p2_x, body_y, pw_info, ph)
                pygame.draw.rect(self.screen, (28, 24, 46), p2_rect, border_radius=12)
                pygame.draw.rect(self.screen, (56, 189, 248), p2_rect, 1, border_radius=12)

                # Fetch fuel telemetry
                fuel_tele = self.app_telemetry.get('fuel_tracker', {})
                f_data = fuel_tele.get('data', {}) if isinstance(fuel_tele, dict) else {}
                cheapest_station = f_data.get('cheapest_station', {}) if isinstance(f_data, dict) else {}

                # Price extraction
                price_val = f_data.get('price') if isinstance(f_data, dict) else None
                if price_val is None:
                    pm = re.search(r'([\d\.]+)\s*(?:¢/L|c/L|\ufffd/L)', summary_txt)
                    if pm:
                        try: price_val = float(pm.group(1))
                        except Exception: pass
                price_str = f"{price_val:.1f}¢/L" if price_val is not None else "Awaiting Price"

                # Recommendation & Badge
                rec = str(f_data.get('recommendation', 'BUY_NOW')).upper() if isinstance(f_data, dict) else ''
                if not rec:
                    if 'BUY NOW' in summary_txt.upper(): rec = 'BUY_NOW'
                    elif 'HOLD OFF' in summary_txt.upper(): rec = 'HOLD_OFF'
                badge_txt = "BUY NOW" if "BUY" in rec else ("HOLD OFF" if "HOLD" in rec else "MONITOR")
                badge_bg = (46, 204, 113) if "BUY" in badge_txt else ((231, 76, 60) if "HOLD" in badge_txt else (52, 152, 219))

                # Station Name & Distance (No address)
                st_name = cheapest_station.get('name') or f_data.get('station')
                if not st_name:
                    sm = re.search(r'cheapest option is (.+?)\s+at', summary_txt, re.IGNORECASE)
                    if sm: st_name = sm.group(1).strip()
                    else: st_name = "Local Fuel Station"

                st_dist = cheapest_station.get('distance_km')

                # Savings extraction (No area average text)
                avg_cents = f_data.get('cluster_stats', {}).get('average_price_cents') if isinstance(f_data, dict) else None
                diff_cents = None
                if avg_cents and price_val and avg_cents > price_val:
                    diff_cents = avg_cents - price_val

                # 1. Top Section: Hero Fuel Card (~240px height)
                fuel_h = 240
                f_rect = pygame.Rect(p2_x + 12, body_y + 12, pw_info - 24, fuel_h)
                pygame.draw.rect(self.screen, (34, 30, 54), f_rect, border_radius=10)
                pygame.draw.rect(self.screen, (46, 204, 113), f_rect, 1, border_radius=10)
                pygame.draw.rect(self.screen, (46, 204, 113), (f_rect.x, f_rect.y, 6, fuel_h), border_top_left_radius=10, border_bottom_left_radius=10)

                fuel_type_lbl = str(f_data.get('fuel_type') or 'U98').upper()
                f_pill = self.font_md.render(f"FUEL WATCH · {fuel_type_lbl}", True, (255, 255, 255))
                f_pill_rect = pygame.Rect(f_rect.x + 16, f_rect.y + 12, f_pill.get_width() + 20, 32)
                pygame.draw.rect(self.screen, (20, 60, 40), f_pill_rect, border_radius=16)
                pygame.draw.rect(self.screen, (46, 204, 113), f_pill_rect, 1, border_radius=16)
                self.screen.blit(f_pill, (f_pill_rect.centerx - f_pill.get_width() // 2, f_pill_rect.centery - f_pill.get_height() // 2))

                b_badge = self.font_md.render(badge_txt, True, (255, 255, 255))
                b_rect = pygame.Rect(f_rect.right - b_badge.get_width() - 28, f_rect.y + 12, b_badge.get_width() + 22, 32)
                pygame.draw.rect(self.screen, badge_bg, b_rect, border_radius=16)
                self.screen.blit(b_badge, (b_rect.centerx - b_badge.get_width() // 2, b_rect.centery - b_badge.get_height() // 2))

                # Hero Fuel Price in font_hero + Price Saving text directly after
                p_font = self.font_hero
                if p_font.size(price_str)[0] > f_rect.width - 32:
                    p_font = self.font_lg
                hero_price = p_font.render(price_str, True, (255, 255, 255))
                self.screen.blit(hero_price, (f_rect.x + 16, f_rect.y + 52))

                if diff_cents and diff_cents > 0:
                    save_lbl = f"(Save {diff_cents:.1f}¢/L)"
                    save_surf = self.font_md.render(save_lbl, True, (46, 204, 113))
                    save_x = f_rect.x + 16 + hero_price.get_width() + 16
                    save_y = f_rect.y + 52 + hero_price.get_height() - save_surf.get_height() - 10
                    if save_x + save_surf.get_width() <= f_rect.right - 14:
                        self.screen.blit(save_surf, (save_x, save_y))
                    else:
                        self.screen.blit(save_surf, (f_rect.x + 18, f_rect.y + 52 + hero_price.get_height() - 2))

                # Station Name in font_lg
                st_font = self.font_lg
                while st_font.size(st_name)[0] > f_rect.width - 32 and len(st_name) > 4:
                    st_name = st_name[:-4] + "..."
                st_name_surf = st_font.render(st_name, True, (130, 220, 255))
                self.screen.blit(st_name_surf, (f_rect.x + 16, f_rect.y + 138))

                # Distance in font_md (without address)
                if st_dist is not None:
                    dist_str = f"{st_dist:.1f} km away"
                    dist_surf = self.font_md.render(dist_str, True, (210, 230, 255))
                    self.screen.blit(dist_surf, (f_rect.x + 16, f_rect.y + 188))

                # 2. Bottom Section: Schedule & Routine Bar (~106px height)
                sched_y = f_rect.bottom + 10
                sched_h = ph - fuel_h - 22
                s_rect = pygame.Rect(p2_x + 12, sched_y, pw_info - 24, sched_h)
                pygame.draw.rect(self.screen, (34, 30, 54), s_rect, border_radius=8)
                pygame.draw.rect(self.screen, (155, 89, 182), s_rect, 1, border_radius=8)
                pygame.draw.rect(self.screen, (155, 89, 182), (s_rect.x, s_rect.y, 6, sched_h), border_top_left_radius=8, border_bottom_left_radius=8)

                cal_tele = self.app_telemetry.get('calendar', {})
                cal_data = cal_tele.get('data') or cal_tele.get('received_events', {}).get('heartbeat', {}).get('data', {})
                if cal_data and cal_data.get('configured'):
                    sched_val_str = cal_data.get('line1') or cal_data.get('agenda_text') or "Today: Nothing on"
                    if cal_data.get('line2'):
                        sched_line2_str = cal_data['line2']
                    elif cal_data.get('next_event') and cal_data['next_event'].get('summary'):
                        ne = cal_data['next_event']
                        time_lbl = ne.get('time_str') or ne.get('time', '')
                        sched_line2_str = f"Next: {time_lbl} · {ne.get('summary')}".strip()
                    else:
                        sched_line2_str = "This Week: Nothing scheduled"
                else:
                    sched_val_str = "Routine Window: 09:00 – 17:00"
                    radar_present = getattr(self, 'radar_nearby_present', False)
                    sched_line2_str = "Radar: Present · Desk-Pal Active" if radar_present else "Radar: Standby · Desk-Pal Ready"

                while self.font_md.size(sched_val_str)[0] > s_rect.width - 28 and len(sched_val_str) > 4:
                    sched_val_str = sched_val_str[:-4] + "..."
                sched_val = self.font_md.render(sched_val_str, True, (255, 255, 255))
                self.screen.blit(sched_val, (s_rect.x + 16, s_rect.y + 16))

                while self.font_md.size(sched_line2_str)[0] > s_rect.width - 28 and len(sched_line2_str) > 4:
                    sched_line2_str = sched_line2_str[:-4] + "..."
                radar_status = self.font_md.render(sched_line2_str, True, (130, 220, 255))
                self.screen.blit(radar_status, (s_rect.x + 16, s_rect.y + 60))

            elif is_dash:
                # Large 5-Inch Screen Dashboard Card (Optimized 1280x720)
                hero_val = dash.get('hero_value', '')
                hero_surf = self.font_hero.render(hero_val, True, (255, 255, 255))
                self.screen.blit(hero_surf, (card_x + 36, card_y + 68))

                badge = dash.get('badge')
                if badge:
                    badge_col = dash.get('badge_color', m_col)
                    badge_surf = self.font_badge.render(badge, True, (255, 255, 255))
                    b_pad_x = 18
                    b_pad_y = 8
                    b_w = badge_surf.get_width() + b_pad_x * 2
                    b_h = badge_surf.get_height() + b_pad_y * 2
                    b_x = card_x + 36 + hero_surf.get_width() + 20
                    b_y = card_y + 68 + max(0, (hero_surf.get_height() - b_h) // 2)
                    if b_x + b_w > card_x + card_w - 24:
                        b_x = card_x + card_w - b_w - 24
                    pygame.draw.rect(self.screen, badge_col, (b_x, b_y, b_w, b_h), border_radius=b_h // 2)
                    pygame.draw.rect(self.screen, (255, 255, 255), (b_x, b_y, b_w, b_h), 1, border_radius=b_h // 2)
                    self.screen.blit(badge_surf, (b_x + b_pad_x, b_y + b_pad_y))

                subhead = dash.get('hero_subhead', '')
                if subhead:
                    sub_surf = self.font_md.render(subhead, True, self.palette['text_dim'])
                    self.screen.blit(sub_surf, (card_x + 38, card_y + 68 + hero_surf.get_height() + 6))

                tiles = dash.get('tiles', [])[:4]
                if tiles:
                    n_tiles = len(tiles)
                    gap = 14
                    t_row_y = card_y + 196
                    t_w = (card_w - 72 - (n_tiles - 1) * gap) // n_tiles
                    t_h = 120
                    for idx, tile in enumerate(tiles):
                        tx = card_x + 36 + idx * (t_w + gap)
                        t_rect = pygame.Rect(tx, t_row_y, t_w, t_h)
                        pygame.draw.rect(self.screen, self.palette['surface'], t_rect, border_radius=10)
                        pygame.draw.rect(self.screen, self.palette['border'], t_rect, 1, border_radius=10)

                        lbl = str(tile.get('label', '')).upper()
                        lbl_surf = self.font_tile_label.render(lbl, True, self.palette['text_dim'])
                        self.screen.blit(lbl_surf, (tx + 16, t_row_y + 16))

                        val = str(tile.get('value', ''))
                        val_surf = self.font_tile_val.render(val, True, self.palette['text'])
                        self.screen.blit(val_surf, (tx + 16, t_row_y + 50))

            else:
                # Classic Multiline Paragraph Text Card
                raw_summary = modal.get("summary", "")
                lines = []
                for par in raw_summary.split("\n"):
                    words = par.split()
                    curr_line = ""
                    for w in words:
                        test_line = f"{curr_line} {w}".strip()
                        if self.font_lg.size(test_line)[0] < (card_w - 60):
                            curr_line = test_line
                        else:
                            if curr_line:
                                lines.append(curr_line)
                            curr_line = w
                    if curr_line:
                        lines.append(curr_line)

                sy = card_y + 80
                line_height = max(40, self.font_lg.get_linesize() + 4)
                page_size = max(1, (card_h - (220 if modal.get('slider') else 150)) // line_height)
                page_count = max(1, math.ceil(len(lines) / page_size))
                page = max(0, min(page_count - 1, modal.get('page', 0)))
                modal['page'] = page
                self.popup_page_buttons = []
                for line in lines[page * page_size:(page + 1) * page_size]:
                    col = self.palette["text"]
                    line_u = line.upper()
                    if "GOOD TIME TO BUY" in line_u or "BUY NOW" in line_u or "AWAITING SHIPMENT" in line_u or "ACTIVE ORDERS" in line_u:
                        col = (106, 215, 60)
                    elif "WAIT TO BUY" in line_u or "HOLD OFF" in line_u or "WARNING" in line_u or "OFFLINE" in line_u or "ERROR" in line_u:
                        col = (255, 110, 110)
                    elif line.startswith("Cheapest:") or "ETSY:" in line_u or "BIG CARTEL:" in line_u or "DEAL:" in line_u or "DROPPED" in line_u:
                        col = (245, 185, 75)
                    elif line.startswith("Average:") or "TREND:" in line_u:
                        col = (100, 200, 255)
                    line_surf = self.font_lg.render(line, True, col)
                    self.screen.blit(line_surf, (card_x + 28, sy))
                    sy += line_height

                if page_count > 1:
                    for direction, label, bx in [(-1, 'Previous', card_x + 20), (1, 'Next', card_x + card_w - 150)]:
                        enabled = page > 0 if direction < 0 else page < page_count - 1
                        rect = pygame.Rect(bx, card_y + card_h - 52, 130, 40)
                        self.popup_page_buttons.append((direction, rect))
                        pygame.draw.rect(self.screen, self.palette["surface_light"] if enabled else self.palette["surface"], rect, border_radius=6)
                        pygame.draw.rect(self.screen, (90, 105, 136), rect, 1, border_radius=6)
                        btn_txt = self.font_md.render(label, True, self.palette["text"] if enabled else self.palette["text_dim"])
                        self.screen.blit(btn_txt, (rect.centerx - btn_txt.get_width() // 2, rect.centery - btn_txt.get_height() // 2))

            # Shared Touch Slider Rail (Supported across Graphic Wellness, Dashboards, and Classic Alerts)
            if modal.get('slider'):
                s = modal['slider']
                min_v = int(s.get('min', 15))
                max_v = int(s.get('max', 120))
                cur_v = int(s.get('value', 45))
                unit = s.get('unit', 'min')
                lbl = s.get('label', 'Next reminder in').upper()

                rail_w = min(680, card_w - 120)
                rail_x = card_x + (card_w - rail_w) // 2
                rail_y = card_y + card_h - 105
                rail_h = 12

                self.popup_slider_rect = pygame.Rect(rail_x - 30, rail_y - 25, rail_w + 60, rail_h + 50)
                self.popup_slider_data = {'rail_x': rail_x, 'rail_w': rail_w, 'slider': s}

                val_txt = f"{lbl}: {cur_v} {unit.upper()}"
                val_surf = self.font_md.render(val_txt, True, m_col)
                self.screen.blit(val_surf, (rail_x + rail_w // 2 - val_surf.get_width() // 2, rail_y - 28))

                min_surf = self.font_md.render(f"{min_v}{unit[0]}", True, self.palette["text_dim"])
                max_surf = self.font_md.render(f"{max_v}{unit[0]}", True, self.palette["text_dim"])
                self.screen.blit(min_surf, (rail_x - min_surf.get_width() - 14, rail_y - 6))
                self.screen.blit(max_surf, (rail_x + rail_w + 14, rail_y - 6))

                pygame.draw.rect(self.screen, self.palette["surface"], (rail_x, rail_y, rail_w, rail_h), border_radius=6)
                pygame.draw.rect(self.screen, (90, 105, 136), (rail_x, rail_y, rail_w, rail_h), 1, border_radius=6)

                pct = max(0.0, min(1.0, (cur_v - min_v) / float(max_v - min_v)))
                fill_w = int(rail_w * pct)
                if fill_w > 0:
                    pygame.draw.rect(self.screen, m_col, (rail_x, rail_y, fill_w, rail_h), border_radius=6)

                thumb_x = rail_x + fill_w
                thumb_y = rail_y + rail_h // 2
                pygame.draw.circle(self.screen, (255, 255, 255), (thumb_x, thumb_y), 16)
                pygame.draw.circle(self.screen, m_col, (thumb_x, thumb_y), 13)
                pygame.draw.circle(self.screen, (38, 43, 68), (thumb_x, thumb_y), 5)

            # Dismiss Action Button
            dismiss_rect = pygame.Rect(card_x + card_w // 2 - 200, card_y + card_h - 48, 400, 36)
            pygame.draw.rect(self.screen, self.palette["surface_light"], dismiss_rect, border_radius=8)
            pygame.draw.rect(self.screen, m_col, dismiss_rect, 1, border_radius=8)
            dis_label = f"[ DISMISS ({page + 1}/{page_count}) ]" if (not is_wellness and not is_dash and 'page_count' in locals() and page_count > 1) else "[ TAP SCREEN TO DISMISS ]"
            dis_txt = self.font_md.render(dis_label, True, self.palette["text"])
            self.screen.blit(dis_txt, (dismiss_rect.centerx - dis_txt.get_width() // 2, dismiss_rect.centery - dis_txt.get_height() // 2))

        # Safe Shutdown Modal
        if self.show_shutdown_modal:
            dim = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 180))
            self.screen.blit(dim, (0, 0))

            modal_rect = pygame.Rect(self.width // 2 - 270, self.height // 2 - 140, 540, 280)
            pygame.draw.rect(self.screen, self.palette["surface"], modal_rect, border_radius=16)
            pygame.draw.rect(self.screen, self.palette["red"], modal_rect, 3, border_radius=16)

            title_txt = "EXIT DESK-PAL?" if getattr(self, 'desktop_mode', False) else "SAFE SHUTDOWN?"
            sub_txt = "Exit companion application?" if getattr(self, 'desktop_mode', False) else "Safely turn off Raspberry Pi system?"
            pwr_txt = "EXIT" if getattr(self, 'desktop_mode', False) else "POWER OFF"
            title_m = self.font_lg.render(title_txt, True, self.palette["red"])
            sub_m = self.font_md.render(sub_txt, True, self.palette["text"])
            self.screen.blit(title_m, (modal_rect.centerx - title_m.get_width() // 2, modal_rect.y + 30))
            self.screen.blit(sub_m, (modal_rect.centerx - sub_m.get_width() // 2, modal_rect.y + 85))

            pygame.draw.rect(self.screen, self.palette["surface_light"], self.modal_cancel_rect, border_radius=10)
            pygame.draw.rect(self.screen, self.palette["border"], self.modal_cancel_rect, 2, border_radius=10)
            c_txt = self.font_md.render("CANCEL", True, self.palette["text"])
            self.screen.blit(c_txt, (self.modal_cancel_rect.centerx - c_txt.get_width() // 2,
                                     self.modal_cancel_rect.centery - c_txt.get_height() // 2))

            pygame.draw.rect(self.screen, self.palette["red"], self.modal_shutdown_rect, border_radius=10)
            s_txt = self.font_md.render(pwr_txt, True, self.palette["text"])
            self.screen.blit(s_txt, (self.modal_shutdown_rect.centerx - s_txt.get_width() // 2,
                                     self.modal_shutdown_rect.centery - s_txt.get_height() // 2))

        if getattr(self, 'active_game_overlay', None) and not self.is_sleeping:
            self.active_game_overlay.draw(self)
        elif getattr(self, 'tv_viewer', None) and not self.is_sleeping:
            self.tv_viewer.draw(self)
        if getattr(self, 'desktop_mode', False) and hasattr(self, 'desktop_helper'):
            self.desktop_helper.render(self.screen, self.window, getattr(self.display_power, 'is_off', False), getattr(self, 'font_sm', None))
        pygame.display.flip()

    def update_light_sleep(self):
        from optional_hardware import monitor_for, LightSleepPolicy
        monitor = monitor_for(self, os.path.join(os.path.dirname(get_active_config_path()), 'hardware_settings.json'))
        if not hasattr(self, 'light_sleep_policy'):
            self.light_sleep_policy = LightSleepPolicy()
        # Never block the display thread on I2C or device inventory commands.
        if not monitor.lock.acquire(blocking=False):
            return
        try:
            options = dict(monitor.config['light'])
            reading = dict(monitor.i2c['light'])
            imu = dict(monitor.i2c['imu'])
            mount = copy.deepcopy(monitor.config['imu'])
            radar = copy.deepcopy(monitor.radar)
            presence_range_m = monitor.config['radar'].get('presence_range_m', 2.0)
            radar['_monotonic_at'] = time.monotonic()-(time.time()-(radar.get('last_frame') or 0))
            calibrating = monitor.imu_capture.get('state') == 'recording' or monitor.radar_capture.get('state') in ('preparing','recording')
        finally:
            monitor.lock.release()
        blocked = bool(self.active_popup_modal or self.pending_popup_modal or getattr(self, 'show_shutdown_modal', False) or getattr(self, 'tv_viewer', None) or getattr(self, 'active_game_overlay', None))
        speech = getattr(self, 'speech_output', None)
        blocked = blocked or bool(speech and speech.snapshot().get('state') == 'playing')
        from light_schedule import evening_awake, bedtime_window
        from radar_awake import RadarAwakePolicy, sleep_inputs, presence_keeps_awake, presence_reading
        nearby_radar = presence_reading(radar, presence_range_m)
        self.radar_nearby_present = len(nearby_radar.get('targets', [])) > 0
        self.last_radar_nearby = nearby_radar
        mgr = getattr(self, 'attention_voice_manager', None)
        if mgr:
            mgr.tick(self, time.monotonic())
        sentry = getattr(self, 'voice_sentry', None)
        if sentry and hasattr(sentry, 'tick'):
            sentry.tick(self, time.monotonic())
        if not hasattr(self, 'radar_awake_policy'):
            self.radar_awake_policy = RadarAwakePolicy()
        presence_awake = self.radar_awake_policy.tick(options.get('presence_awake_enabled', False), nearby_radar,
            time.monotonic(), options.get('presence_absence_seconds', 30), calibrating)
        now = time.monotonic()
        night = bedtime_window(options, self.cfg.get('lighting', {}))
        presence_override = presence_keeps_awake(presence_awake, night, sleeping=self.is_sleeping)
        evening_override = evening_awake(options, self.cfg.get('lighting', {}))
        sleep_options, sleep_reading = sleep_inputs(options, reading, self.radar_awake_policy, presence_override, now,
            night=night, bedtime_priority=not presence_awake, sleeping=self.is_sleeping)
        action = self.light_sleep_policy.tick(sleep_options, sleep_reading, self.is_sleeping, now, blocked,
            presence_override or evening_override)
        self.sleep_policy_status = dict(sleeping=self.is_sleeping, bedtime=options['bedtime'],
            bedtime_active=night, radar_presence=presence_awake, radar_keeps_awake=presence_override,
            presence_range_m=presence_range_m, nearby_targets=len(nearby_radar['targets']),
            ignored_distant_targets=len(radar.get('targets', []))-len(nearby_radar['targets']),
            evening_keeps_awake=evening_override, popup_blocks_sleep=blocked,
            manual_wake_seconds_remaining=round(max(0, self.light_sleep_policy.awake_until-now), 1),
            light_sample_age_seconds=round(now-reading.get('at', 0), 1),
            pending=self.light_sleep_policy.pending, action=action,
            panel_off=bool(getattr(getattr(self, 'display_power', None), 'is_off', False)))
        if action == 'sleep':
            self.audit_activity('light_sleep', lux=reading.get('lux'), threshold=options['sleep_below_lux'])
            self.enter_standby(source='light')
        elif action == 'wake':
            self.audit_activity('light_wake', lux=reading.get('lux'))
            self.wake_from_standby(source='light')
        from sensor_events import SensorEvents, ensure_sensor_source
        if not hasattr(self, 'sensor_events'):
            self.sensor_events = SensorEvents()
        source = ensure_sensor_source(self.cfg)
        from morning_greeting import update as update_morning
        try:
            morning_sent = update_morning(self, nearby_radar, calibrating)
        except (OSError, ValueError) as error:
            morning_sent = False
            if not getattr(self, '_morning_error_reported', False):
                self.audit_activity('morning_greeting_error', error=str(error))
                self._morning_error_reported = True
        events = self.sensor_events.tick(source.get('sensor_settings', {}), mount, imu, nearby_radar, time.monotonic(), calibrating)
        for event in events:
            if morning_sent and event['event'] == 'person_returned':
                continue
            # Motion is ephemeral: do not replay a pile of old shakes after sleep.
            if self.is_sleeping or self.edit_mode:
                continue
            queue = self.activity_queue
            with queue.lock:
                if (queue.active and queue.active[0].get('_source_app_id') == source['id']) or any(a[0].get('_source_app_id') == source['id'] for a in queue.items):
                    continue
            self.receive_telemetry_event(dict(event, app_id=source['id'], occurrence=time.time(), summary=event['event'].replace('_',' ')))

    def run(self):
        while self.running:
            has_game = bool(getattr(self, 'active_game_overlay', None) and not self.is_sleeping)
            if self.is_sleeping:
                dt = self.clock.tick(10) / 1000.0
                time.sleep(0.04)
            else:
                dt = self.clock.tick(60 if has_game else 25) / 1000.0
                time.sleep(0.003)
            dt = min(0.1, dt)
            self.update_gpio_settings()
            self.process_switch_inputs()
            if self.preview_bridge:
                self.preview_bridge.tick_inputs(self)

            # Always check active_game_overlay live (it may have been closed by switch inputs)
            if getattr(self, 'active_game_overlay', None) and not self.is_sleeping:
                try:
                    self.active_game_overlay.update(self, dt)
                except Exception as e:
                    print(f"[GameOverlay] Update error: {e}")
                    self.active_game_overlay = None
            elif self.is_sleeping:
                self.update_light_sleep()
                self.update_autonomous_movement(dt)
            else:
                self.update_light_sleep()
                from weather_source import WeatherSource
                if not hasattr(self, 'weather_source'): self.weather_source = WeatherSource()
                self.weather_source.tick(self)
                from integration_poller import IntegrationPoller
                if not hasattr(self, 'integration_poller'): self.integration_poller = IntegrationPoller()
                self.integration_poller.tick(self)
                if getattr(self, 'backup_content_reload', False):
                    from activity_queue import ActivityQueue
                    from interactive_props import close_tv
                    close_tv(self, 'content_reload')
                    self.backup_content_reload = False
                    self.load_scene_backgrounds()
                    self._image_prop_cache = SurfaceCache()
                    self.active_prop_overlays = {}
                    self.activity_queue = ActivityQueue()
                    self.active_popup_modal = self.pending_popup_modal = None
                    self.active_rest_role = self.rest_transition = None
                    self.scene_journey = []
                    self.journey_arriving = False
                    self.char_x, self.char_y = self.clamp_to_walkable(self.char_x, self.char_y)
                    self.target_x, self.target_y = self.char_x, self.char_y
                    self.target_animation = self.current_anim = 'idle'
                    self.target_spot_id = None
                    self._route_goal = None
                    self.wander_timer = 0
                if self.save_feedback_timer > 0:
                    self.save_feedback_timer -= dt

                # Auto-dismiss temporary key OSD after 2.5 seconds if in on_press mode
                if self.show_quick_keys and self.quick_keys_mode == "on_press":
                    if self.keys_dismiss_timer > 0:
                        self.keys_dismiss_timer -= dt
                        if self.keys_dismiss_timer <= 0:
                            self.show_quick_keys = False

                destination = getattr(self, 'pending_scene_destination', None)
                if destination:
                    self.pending_scene_destination = None
                    try:
                        self.request_scene_travel(destination)
                        self.travel_error = None
                    except ValueError as e:
                        self.travel_error = str(e)
                        self.status_msg = str(e)
                if self.status_msg != getattr(self, '_last_speech', None):
                    self._last_speech = self.status_msg
                    self.speech_until = time.monotonic() + 8
                self.check_integration_health()
                update_notifications(self)
                from sensor_reaction import tick as tick_sensor_reaction
                from speech_reaction import tick as tick_speech_reaction
                if not tick_speech_reaction(self) and not tick_sensor_reaction(self):
                    self.activity_queue.tick(self)
                    self.update_autonomous_movement(dt)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.VIDEORESIZE:
                    if getattr(self, 'desktop_mode', False):
                        self.win_width = max(320, event.w)
                        self.win_height = max(180, event.h)
                        self.window = pygame.display.set_mode((self.win_width, self.win_height), pygame.RESIZABLE)
                elif event.type == pygame.KEYDOWN:
                    if self.is_sleeping:
                        self.wake_from_standby()
                        continue
                    if event.key == pygame.K_ESCAPE:
                        if getattr(self, 'active_game_overlay', None):
                            self.active_game_overlay.close(self)
                            self._game_exit_cooldown = time.monotonic() + 0.6
                            continue
                        elif getattr(self, 'tv_viewer', None):
                            from interactive_props import close_tv
                            close_tv(self)
                        elif self.edit_mode:
                            self.edit_mode = False
                        elif self.show_shutdown_modal:
                            self.show_shutdown_modal = False
                        else:
                            self.running = False
                    elif event.key == pygame.K_s:
                        cycle = {"on_press": "always", "always": "never", "never": "on_press"}
                        next_mode = cycle.get(self.quick_keys_mode, "on_press")
                        self.set_on_screen_buttons_mode(next_mode)
                        self.save_walkbox_config()
                        mode_labels = {"always": "ALWAYS SHOW", "never": "ALWAYS HIDE", "on_press": "SHOW ON PRESS"}
                        self.status_msg = f"On-screen buttons: {mode_labels.get(next_mode)}"
                    elif event.key == pygame.K_h:
                        self.top_controls_open = not self.top_controls_open
                    elif event.key in [pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6]:
                        self.on_switch_pressed(event.key - pygame.K_0)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if self.is_sleeping:
                        self.wake_from_standby()
                        continue
                    self.handle_touch_down(self._map_event_pos(event.pos))
                elif event.type == pygame.MOUSEMOTION:
                    if event.buttons[0]:
                        self.handle_touch_motion(self._map_event_pos(event.pos))
                elif event.type == pygame.MOUSEBUTTONUP:
                    self.handle_touch_up()

            self.draw()
            if self.preview_bridge:
                self.preview_bridge.publish(self.screen, self.display_power.is_off)

        self.connectivity_monitor.stop.set()
        if getattr(self, 'service_supervisor', None):
            self.service_supervisor.shutdown_all()
        pygame.quit()
        print("Desk-Pal exited cleanly.")


if __name__ == "__main__":
    from runtime_maintenance import install_runtime_logging
    import atexit
    try:
        atexit.register(install_runtime_logging(pi_path()))
    except OSError as error:
        print("[WARN] Runtime log unavailable:", error, file=sys.stderr)
    app = DeskPalApp()
    try:
        app.run()
    finally:
        if getattr(app, 'service_supervisor', None):
            app.service_supervisor.shutdown_all()
        app.display_power.set_sleeping(False)
