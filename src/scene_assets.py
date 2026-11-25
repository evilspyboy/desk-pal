"""Store user-uploaded scene backgrounds without accepting filesystem paths."""
import base64
import io
import re
import uuid
from pathlib import Path


def decode_image(payload):
    from PIL import Image
    encoded = payload.get('image_b64', '')
    if not isinstance(encoded, str) or len(encoded) > 17_000_000:
        raise ValueError('Choose a PNG or JPEG smaller than 12 MB')
    raw = base64.b64decode(encoded.split(',')[-1], validate=True)
    if len(raw) > 12_000_000:
        raise ValueError('Choose a PNG or JPEG smaller than 12 MB')
    with Image.open(io.BytesIO(raw)) as image:
        if image.format not in ('PNG', 'JPEG') or not 1 <= image.width*image.height <= 20_000_000:
            raise ValueError('Use a PNG or JPEG up to 20 megapixels')
        extension = 'png' if image.format == 'PNG' else 'jpg'
        image.verify()
    return raw, extension


def save_background(payload, assets_root):
    scene = payload.get('scene_id', '')
    if not isinstance(scene, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,79}', scene):
        raise ValueError('Invalid scene identifier')
    raw, extension = decode_image(payload)
    theme = payload.get('theme') or 'custom_' + scene
    if not isinstance(theme, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,79}', theme):
        raise ValueError('Invalid scene theme')
    variant = payload.get('variant', 'day')
    if variant not in ('day', 'night'):
        raise ValueError('Choose day or night background')
    folder = Path(assets_root) / 'themes' / theme
    folder.mkdir(parents=True, exist_ok=True)
    filename = 'background_' + uuid.uuid4().hex + '.' + extension
    (folder / filename).write_bytes(raw)
    return {'theme': theme, 'background_night' if variant == 'night' else 'background': filename}


def save_prop_frame(payload, assets_root):
    raw, extension = decode_image(payload)
    if extension != 'png':
        raise ValueError('Prop frames must be PNG images (transparent backgrounds supported)')
    folder = Path(assets_root) / 'props'
    folder.mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex + '.png'
    (folder / name).write_bytes(raw)
    return {'url': '/assets/props/' + name}


def save_character_reference(payload, assets_root):
    character = payload.get('character', '')
    if not isinstance(character, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', character):
        raise ValueError('Invalid character identifier')
    raw, extension = decode_image(payload)
    folder = Path(assets_root) / 'characters' / 'references'
    folder.mkdir(parents=True, exist_ok=True)
    name = character + '_' + uuid.uuid4().hex + '.' + extension
    (folder / name).write_bytes(raw)
    return {'name': character + ' reference', 'url': '/assets/characters/references/' + name}


def save_character_frame(payload, assets_root):
    character = payload.get('character', '')
    if not isinstance(character, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', character):
        raise ValueError('Invalid character identifier')
    raw, extension = decode_image(payload)
    if extension != 'png':
        raise ValueError('Animation frames must be PNG images')
    folder = Path(assets_root) / 'characters' / 'adventurer' / 'uploads' / character
    folder.mkdir(parents=True, exist_ok=True)
    label = re.sub(r'[^a-zA-Z0-9_-]', '_', str(payload.get('name', 'frame')))[:40] or 'frame'
    name = label + '_' + uuid.uuid4().hex[:12]
    (folder / (name + '.png')).write_bytes(raw)
    return {'name': name, 'url': '/assets/characters/adventurer/uploads/' + character + '/' + name + '.png'}
