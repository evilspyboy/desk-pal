"""Desk-Pal Theme Management System.

Manages swappable visual themes (scenes, characters, animations, props, UI palette,
and card styling) without disrupting persistent companion services (Calendar, Fuel,
Weather, Flight Radar) or hardware calibrations.
"""

import copy
import io
import json
import os
import re
import shutil
import time
import zipfile

BUILTIN_THEMES = ('cozy_study', 'retro_apartment', 'resort_beach', 'video_store')

# Visual fields that belong exclusively to a theme (and must not touch apps or hardware)
THEME_VISUAL_FIELDS = (
    'palette',
    'card_style',
    'active_scene',
    'scenes',
    'scene_links',
    'scene_placements',
    'active_character',
    'characters',
    'animation_sequences',
    'prop_animations',
    'props',
    'interaction_spots',
    'walkable_trapezoid',
    'pose_rules',
    'obstacles',
)


def get_themes_dir():
    """Resolve directory where themes are stored."""
    if os.environ.get('DESKPAL_DATA_DIR'):
        path = os.path.join(os.path.abspath(os.environ['DESKPAL_DATA_DIR']), 'themes')
    elif os.path.isdir('/home/admin/themes'):
        path = '/home/admin/themes'
    else:
        # Local workspace fallback
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'themes'))
    os.makedirs(path, exist_ok=True)
    return path


def _validate_theme_id(theme_id):
    if not isinstance(theme_id, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,63}', theme_id):
        raise ValueError("Theme ID must use lowercase letters, numbers, hyphens, or underscores (2-64 chars).")


def get_theme_path(theme_id):
    """Return path to theme.json for a theme ID."""
    _validate_theme_id(theme_id)
    return os.path.join(get_themes_dir(), theme_id, 'theme.json')


def get_theme(theme_id):
    """Load and return the theme dictionary for theme_id."""
    path = get_theme_path(theme_id)
    if not os.path.isfile(path):
        # Check single file fallback: themes/<theme_id>.json
        alt_path = os.path.join(get_themes_dir(), f"{theme_id}.json")
        if os.path.isfile(alt_path):
            path = alt_path
        else:
            raise FileNotFoundError(f"Theme '{theme_id}' does not exist.")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_theme(theme_id, theme_data):
    """Save a theme dictionary to themes/<theme_id>/theme.json."""
    _validate_theme_id(theme_id)
    theme_data['id'] = theme_id
    theme_data['updated_at'] = int(time.time())
    folder = os.path.join(get_themes_dir(), theme_id)
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, 'theme.json')
    tmp_path = target + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(theme_data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, target)
    return theme_data


def list_themes(active_theme_id=None):
    """Return a list of summary dicts for all available themes."""
    ensure_builtin_themes()
    themes_dir = get_themes_dir()
    results = []

    # Check directory entries
    if os.path.isdir(themes_dir):
        for entry in sorted(os.listdir(themes_dir)):
            full = os.path.join(themes_dir, entry)
            theme_file = None
            if os.path.isdir(full):
                candidate = os.path.join(full, 'theme.json')
                if os.path.isfile(candidate):
                    theme_file = candidate
            elif entry.endswith('.json'):
                theme_file = full

            if theme_file:
                try:
                    with open(theme_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    tid = data.get('id', entry if not entry.endswith('.json') else entry[:-5])
                    results.append({
                        'id': tid,
                        'name': data.get('name', tid.replace('_', ' ').title()),
                        'description': data.get('description', ''),
                        'version': data.get('version', '1.0'),
                        'author': data.get('author', 'Desk-Pal Community'),
                        'active_scene': data.get('active_scene', 'cozy_study'),
                        'active_character': data.get('active_character', 'adventurer_v1'),
                        'palette': data.get('palette', {}),
                        'card_style': data.get('card_style', {}),
                        'is_active': (tid == active_theme_id),
                        'is_builtin': (tid in BUILTIN_THEMES),
                        'updated_at': data.get('updated_at', 0)
                    })
                except Exception as e:
                    print(f"[WARN] Error reading theme '{entry}': {e}")

    # Sort builtins first, then custom themes
    results.sort(key=lambda t: (not t['is_builtin'], t['name'].lower()))
    return results


def create_theme_from_config(theme_id, name, description, cfg, card_style=None):
    """Extract all visual/aesthetic settings from cfg into a named theme profile."""
    _validate_theme_id(theme_id)
    theme_data = {
        'id': theme_id,
        'name': name or theme_id.replace('_', ' ').title(),
        'description': description or f"Custom theme created on {time.strftime('%Y-%m-%d %H:%M')}",
        'version': '1.0',
        'author': 'Desk-Pal Studio User',
        'created_at': int(time.time()),
        'updated_at': int(time.time()),
        'palette': copy.deepcopy(cfg.get('palette', {})),
        'card_style': copy.deepcopy(card_style or cfg.get('card_style', {
            'border_radius': 14,
            'accent_border': True,
            'header_tint': cfg.get('palette', {}).get('accent', [240, 160, 80])
        })),
        'active_scene': cfg.get('active_scene', 'cozy_study'),
        'active_character': cfg.get('active_character', 'adventurer_v1'),
        'scenes': copy.deepcopy(cfg.get('scenes', {})),
        'scene_links': copy.deepcopy(cfg.get('scene_links', [])),
        'scene_placements': copy.deepcopy(cfg.get('scene_placements', {})),
        'characters': copy.deepcopy(cfg.get('characters', {})),
        'animation_sequences': copy.deepcopy(cfg.get('animation_sequences', {})),
        'prop_animations': copy.deepcopy(cfg.get('prop_animations', {})),
        'props': copy.deepcopy(cfg.get('props', [])),
        'interaction_spots': copy.deepcopy(cfg.get('interaction_spots', [])),
        'walkable_trapezoid': copy.deepcopy(cfg.get('walkable_trapezoid', {})),
        'pose_rules': copy.deepcopy(cfg.get('pose_rules', {})),
        'obstacles': copy.deepcopy(cfg.get('obstacles', []))
    }
    return save_theme(theme_id, theme_data)


def duplicate_theme(source_id, new_id, new_name=None, description=None):
    """Clone an existing theme to a new ID with an updated name."""
    _validate_theme_id(new_id)
    source = get_theme(source_id)
    clone = copy.deepcopy(source)
    clone['id'] = new_id
    clone['name'] = new_name or f"{source.get('name', source_id)} (Copy)"
    clone['description'] = description or f"Duplicated from {source.get('name', source_id)}"
    clone['created_at'] = int(time.time())
    clone['updated_at'] = int(time.time())
    return save_theme(new_id, clone)


def delete_theme(theme_id, active_theme_id=None):
    """Delete a custom theme. Cannot delete the active theme or built-in defaults."""
    _validate_theme_id(theme_id)
    if theme_id in BUILTIN_THEMES:
        raise ValueError(f"Cannot delete built-in theme '{theme_id}'.")
    if active_theme_id and theme_id == active_theme_id:
        raise ValueError(f"Cannot delete the currently active theme '{theme_id}'. Switch themes first.")

    folder = os.path.join(get_themes_dir(), theme_id)
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    alt_file = os.path.join(get_themes_dir(), f"{theme_id}.json")
    if os.path.isfile(alt_file):
        os.remove(alt_file)
    return True


def apply_theme_to_config(theme_data_or_id, cfg):
    """
    Applies the visual theme data to a room configuration dictionary.
    Guarantees that apps, switches, sensor settings, and morning greeting stay intact.
    """
    if isinstance(theme_data_or_id, str):
        theme_data = get_theme(theme_data_or_id)
    else:
        theme_data = theme_data_or_id

    theme_id = theme_data.get('id', 'cozy_study')
    cfg['theme'] = theme_id

    # 1. Update UI Palette & Card Styling
    if 'palette' in theme_data:
        cfg['palette'] = copy.deepcopy(theme_data['palette'])
    if 'card_style' in theme_data:
        cfg['card_style'] = copy.deepcopy(theme_data['card_style'])

    # 2. Update Scenes, Links, and Placements
    if 'scenes' in theme_data and isinstance(theme_data['scenes'], dict):
        cfg.setdefault('scenes', {})
        for s_id, s_data in theme_data['scenes'].items():
            cfg['scenes'][s_id] = copy.deepcopy(s_data)
    if 'scene_links' in theme_data:
        cfg['scene_links'] = copy.deepcopy(theme_data['scene_links'])
    if 'scene_placements' in theme_data:
        cfg.setdefault('scene_placements', {})
        for s_id, p_data in theme_data['scene_placements'].items():
            cfg['scene_placements'][s_id] = copy.deepcopy(p_data)

    # 3. Update Characters and Animations
    if 'characters' in theme_data and isinstance(theme_data['characters'], dict):
        cfg.setdefault('characters', {})
        for c_id, c_data in theme_data['characters'].items():
            cfg['characters'][c_id] = copy.deepcopy(c_data)
    if 'active_character' in theme_data:
        cfg['active_character'] = theme_data['active_character']
    if 'animation_sequences' in theme_data and isinstance(theme_data['animation_sequences'], dict):
        cfg.setdefault('animation_sequences', {})
        for seq_id, seq_data in theme_data['animation_sequences'].items():
            cfg['animation_sequences'][seq_id] = copy.deepcopy(seq_data)
    if 'prop_animations' in theme_data and isinstance(theme_data['prop_animations'], dict):
        cfg.setdefault('prop_animations', {})
        for p_id, p_data in theme_data['prop_animations'].items():
            cfg['prop_animations'][p_id] = copy.deepcopy(p_data)

    # 4. Activate Destination Scene
    target_scene = theme_data.get('active_scene')
    if not target_scene or target_scene not in cfg.get('scenes', {}):
        target_scene = next(iter(cfg.get('scenes', {}).keys()), 'cozy_study')

    from scene_world import activate_scene
    activate_scene(cfg, target_scene)

    # Re-assert visual theme profile after scene activation
    cfg['theme_profile'] = theme_id
    cfg['theme'] = theme_id

    return cfg


def export_theme_zip(theme_id):
    """Package theme.json into a zip archive."""
    theme = get_theme(theme_id)
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        manifest = {
            'format': 'deskpal-theme',
            'version': 1,
            'id': theme_id,
            'name': theme.get('name', theme_id)
        }
        z.writestr('manifest.json', json.dumps(manifest, indent=2))
        z.writestr('theme.json', json.dumps(theme, indent=2))
    return out.getvalue()


def import_theme_zip(zip_bytes):
    """Import a theme from zip bytes, returning the saved theme dict."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        if 'theme.json' not in z.namelist():
            raise ValueError("Theme archive missing 'theme.json'")
        theme_raw = z.read('theme.json').decode('utf-8')
        theme_data = json.loads(theme_raw)

    theme_id = theme_data.get('id')
    if not theme_id:
        raise ValueError("Theme JSON missing required 'id' attribute.")
    _validate_theme_id(theme_id)
    return save_theme(theme_id, theme_data)


def ensure_builtin_themes():
    """Seed the default 4 themes if they do not yet exist on disk."""
    themes_dir = get_themes_dir()

    # Load baseline from room_config.json if available
    base_cfg = None
    for p in (
        os.path.join(os.path.dirname(__file__), '..', 'config', 'room_config.json'),
        '/home/admin/config/room_config.json',
        'config/room_config.json'
    ):
        if os.path.isfile(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    base_cfg = json.load(f)
                break
            except Exception:
                pass

    if not base_cfg:
        return

    # 1. Cozy Study
    cozy_path = os.path.join(themes_dir, 'cozy_study', 'theme.json')
    if not os.path.isfile(cozy_path):
        palette_cozy = {
            'background': [24, 20, 37],
            'surface': [38, 43, 68],
            'surface_light': [58, 68, 102],
            'border': [90, 105, 136],
            'accent': [240, 160, 80],
            'green': [106, 190, 48],
            'red': [217, 87, 99],
            'blue': [75, 105, 204],
            'text': [238, 238, 240],
            'text_dim': [139, 155, 180]
        }
        theme_cozy = {
            'id': 'cozy_study',
            'name': 'Cozy Study',
            'description': 'Classic oak & amber study with bookshelves, desk terminal, arched window, and warm pixel lighting.',
            'version': '1.0',
            'author': 'Desk-Pal Default',
            'created_at': int(time.time()),
            'updated_at': int(time.time()),
            'active_scene': 'cozy_study',
            'active_character': 'adventurer_v1',
            'palette': palette_cozy,
            'card_style': {
                'border_radius': 14,
                'accent_border': True,
                'header_tint': [240, 160, 80]
            },
            'scenes': copy.deepcopy(base_cfg.get('scenes', {})),
            'scene_links': copy.deepcopy(base_cfg.get('scene_links', [])),
            'scene_placements': copy.deepcopy(base_cfg.get('scene_placements', {})),
            'characters': copy.deepcopy(base_cfg.get('characters', {})),
            'animation_sequences': copy.deepcopy(base_cfg.get('animation_sequences', {})),
            'prop_animations': copy.deepcopy(base_cfg.get('prop_animations', {})),
            'props': copy.deepcopy(base_cfg.get('scenes', {}).get('cozy_study', {}).get('props', base_cfg.get('props', []))),
            'interaction_spots': copy.deepcopy(base_cfg.get('scenes', {}).get('cozy_study', {}).get('interaction_spots', base_cfg.get('interaction_spots', []))),
            'walkable_trapezoid': copy.deepcopy(base_cfg.get('scenes', {}).get('cozy_study', {}).get('walkable_trapezoid', base_cfg.get('walkable_trapezoid', {}))),
            'pose_rules': copy.deepcopy(base_cfg.get('scenes', {}).get('cozy_study', {}).get('pose_rules', base_cfg.get('pose_rules', {}))),
            'obstacles': copy.deepcopy(base_cfg.get('scenes', {}).get('cozy_study', {}).get('obstacles', base_cfg.get('obstacles', [])))
        }
        save_theme('cozy_study', theme_cozy)

    # 2. Retro Apartment
    apt_path = os.path.join(themes_dir, 'retro_apartment', 'theme.json')
    if not os.path.isfile(apt_path):
        palette_retro = {
            'background': [18, 16, 32],
            'surface': [32, 28, 54],
            'surface_light': [52, 44, 82],
            'border': [100, 75, 140],
            'accent': [255, 107, 181],   # Neon pink
            'green': [46, 213, 115],
            'red': [255, 71, 87],
            'blue': [0, 210, 211],      # Neon cyan
            'text': [245, 245, 255],
            'text_dim': [165, 155, 190]
        }
        theme_retro = {
            'id': 'retro_apartment',
            'name': 'Retro Apartment',
            'description': '90s collector apartment with CRT television, pop-culture ALF & Transformers easter eggs, and synthwave styling.',
            'version': '1.0',
            'author': 'Desk-Pal Default',
            'created_at': int(time.time()),
            'updated_at': int(time.time()),
            'active_scene': 'apartment',
            'active_character': 'adventurer_v1',
            'palette': palette_retro,
            'card_style': {
                'border_radius': 12,
                'accent_border': True,
                'header_tint': [255, 107, 181]
            },
            'scenes': copy.deepcopy(base_cfg.get('scenes', {})),
            'scene_links': copy.deepcopy(base_cfg.get('scene_links', [])),
            'scene_placements': copy.deepcopy(base_cfg.get('scene_placements', {})),
            'characters': copy.deepcopy(base_cfg.get('characters', {})),
            'animation_sequences': copy.deepcopy(base_cfg.get('animation_sequences', {})),
            'prop_animations': copy.deepcopy(base_cfg.get('prop_animations', {})),
            'props': copy.deepcopy(base_cfg.get('scenes', {}).get('apartment', {}).get('props', [])),
            'interaction_spots': copy.deepcopy(base_cfg.get('scenes', {}).get('apartment', {}).get('interaction_spots', [])),
            'walkable_trapezoid': copy.deepcopy(base_cfg.get('scenes', {}).get('apartment', {}).get('walkable_trapezoid', {})),
            'pose_rules': copy.deepcopy(base_cfg.get('scenes', {}).get('apartment', {}).get('pose_rules', {})),
            'obstacles': copy.deepcopy(base_cfg.get('scenes', {}).get('apartment', {}).get('obstacles', []))
        }
        save_theme('retro_apartment', theme_retro)

    # 3. Resort Beach
    beach_path = os.path.join(themes_dir, 'resort_beach', 'theme.json')
    if not os.path.isfile(beach_path):
        palette_beach = {
            'background': [16, 32, 48],
            'surface': [26, 56, 82],
            'surface_light': [42, 82, 118],
            'border': [62, 118, 158],
            'accent': [255, 190, 60],   # Sunlit gold
            'green': [50, 200, 150],   # Emerald seafoam
            'red': [245, 100, 95],
            'blue': [0, 180, 230],     # Turquoise ocean
            'text': [240, 250, 255],
            'text_dim': [140, 180, 205]
        }
        theme_beach = {
            'id': 'resort_beach',
            'name': 'Resort Beach',
            'description': 'Tropical beach resort with sunlit turquoise ocean ripples, tiki bar, and sea breeze.',
            'version': '1.0',
            'author': 'Desk-Pal Default',
            'created_at': int(time.time()),
            'updated_at': int(time.time()),
            'active_scene': 'resort_beach',
            'active_character': 'adventurer_v1',
            'palette': palette_beach,
            'card_style': {
                'border_radius': 16,
                'accent_border': True,
                'header_tint': [255, 190, 60]
            },
            'scenes': copy.deepcopy(base_cfg.get('scenes', {})),
            'scene_links': copy.deepcopy(base_cfg.get('scene_links', [])),
            'scene_placements': copy.deepcopy(base_cfg.get('scene_placements', {})),
            'characters': copy.deepcopy(base_cfg.get('characters', {})),
            'animation_sequences': copy.deepcopy(base_cfg.get('animation_sequences', {})),
            'prop_animations': copy.deepcopy(base_cfg.get('prop_animations', {})),
            'props': copy.deepcopy(base_cfg.get('scenes', {}).get('resort_beach', {}).get('props', [])),
            'interaction_spots': copy.deepcopy(base_cfg.get('scenes', {}).get('resort_beach', {}).get('interaction_spots', [])),
            'walkable_trapezoid': copy.deepcopy(base_cfg.get('scenes', {}).get('resort_beach', {}).get('walkable_trapezoid', {})),
            'pose_rules': copy.deepcopy(base_cfg.get('scenes', {}).get('resort_beach', {}).get('pose_rules', {})),
            'obstacles': copy.deepcopy(base_cfg.get('scenes', {}).get('resort_beach', {}).get('obstacles', []))
        }
        save_theme('resort_beach', theme_beach)

    # 4. Video Store
    video_path = os.path.join(themes_dir, 'video_store', 'theme.json')
    if not os.path.isfile(video_path):
        palette_video = {
            'background': [16, 20, 28],
            'surface': [28, 36, 50],
            'surface_light': [44, 56, 78],
            'border': [70, 90, 120],
            'accent': [255, 220, 40],   # VHS yellow
            'green': [70, 210, 120],
            'red': [240, 70, 70],
            'blue': [40, 120, 240],    # Royal blue
            'text': [245, 248, 255],
            'text_dim': [150, 165, 185]
        }
        theme_video = {
            'id': 'video_store',
            'name': 'Video Store',
            'description': 'Late 80s / early 90s VHS rental store with retro movie shelves, CRT counter, and nostalgic rental palette.',
            'version': '1.0',
            'author': 'Desk-Pal Default',
            'created_at': int(time.time()),
            'updated_at': int(time.time()),
            'active_scene': 'video_store',
            'active_character': 'adventurer_v1',
            'palette': palette_video,
            'card_style': {
                'border_radius': 10,
                'accent_border': True,
                'header_tint': [255, 220, 40]
            },
            'scenes': copy.deepcopy(base_cfg.get('scenes', {})),
            'scene_links': copy.deepcopy(base_cfg.get('scene_links', [])),
            'scene_placements': copy.deepcopy(base_cfg.get('scene_placements', {})),
            'characters': copy.deepcopy(base_cfg.get('characters', {})),
            'animation_sequences': copy.deepcopy(base_cfg.get('animation_sequences', {})),
            'prop_animations': copy.deepcopy(base_cfg.get('prop_animations', {})),
            'props': copy.deepcopy(base_cfg.get('scenes', {}).get('video_store', {}).get('props', [])),
            'interaction_spots': copy.deepcopy(base_cfg.get('scenes', {}).get('video_store', {}).get('interaction_spots', [])),
            'walkable_trapezoid': copy.deepcopy(base_cfg.get('scenes', {}).get('video_store', {}).get('walkable_trapezoid', {})),
            'pose_rules': copy.deepcopy(base_cfg.get('scenes', {}).get('video_store', {}).get('pose_rules', {})),
            'obstacles': copy.deepcopy(base_cfg.get('scenes', {}).get('video_store', {}).get('obstacles', []))
        }
        save_theme('video_store', theme_video)
