"""Headless regression checks; run on the Pi with pygame and the existing assets."""
import copy
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
try:
    import pygame
    candidates = [arg for arg in sys.argv[1:] if arg.endswith('.py') and not arg.startswith('-') and 'test_' not in arg]
    source = pathlib.Path(candidates[0]) if candidates else pathlib.Path(__file__).resolve().parents[1] / 'src/deskpal_app.py'
    spec = importlib.util.spec_from_file_location('deskpal_test_app', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
except ImportError:
    pygame = None
    module = None


class WalkingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if pygame is None or module is None:
            raise unittest.SkipTest("pygame is required for character walk tests")

    def setUp(self):
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        (self.root / 'walk').mkdir()
        tags = {}
        self.urls = []
        for i in range(4):
            url = f'/assets/characters/adventurer/walk/walk_{i}.png'
            self.urls.append(url)
            tags[url] = {'variant': 'adventurer_v1'}
            pygame.image.save(pygame.Surface((8, 12), pygame.SRCALPHA), str(self.root / 'walk' / f'walk_{i}.png'))
        (self.root / 'sprite_tags.json').write_text(json.dumps(tags))
        self.config_patch = patch.object(module, 'get_active_config_path', return_value=str(self.root/'room_config.json'))
        self.config_patch.start()
        self.app = module.DeskPalApp.__new__(module.DeskPalApp)
        self.app.char_dir = str(self.root)
        self.app.sprite_cache = {}
        self.app.raw_sprites = {}
        self.app.trap = dict(y_min=-100, y_max=200, back_x_min=-100, back_x_max=1200, front_x_min=-100, front_x_max=1200)
        self.app.obstacles = []
        self.cfg = {'active_character': 'adventurer_v1', 'characters': {'adventurer_v1': {'animations': {'walk': 'v1:walk'}}},
                    'animation_sequences': {'v1:walk': {'character': 'adventurer_v1', 'fps': 4, 'frames': [{'url': self.urls[i]} for i in [2, 0, 3, 1]]}}}
        self.app.cfg = copy.deepcopy(self.cfg)

    def tearDown(self):
        self.config_patch.stop()
        self.temp.cleanup()

    def test_order_subdirectories_speed_and_idle(self):
        self.app.configure_character(self.cfg)
        self.assertEqual(self.app.walk_frames, [self.urls[i] for i in [2, 0, 3, 1]])
        self.assertEqual(self.app.walk_fps, 4)
        self.assertIn('idle', self.app.raw_sprites)
        self.app.edit_mode = False
        self.app.char_x = self.app.char_y = 0
        self.app.target_x = 1000
        self.app.target_y = 0
        self.app.update_autonomous_movement(0.76)
        self.assertEqual(self.app.anim_frame, 3)
        self.assertAlmostEqual(self.app.anim_timer, 0.01)

    def test_ping_pong(self):
        self.cfg['animation_sequences']['v1:walk']['ping_pong'] = True
        self.app.configure_character(self.cfg)
        actual = []
        for i in range(8):
            self.app.anim_frame = i
            actual.append(self.app.walking_sprite_name())
        self.assertEqual(actual, [self.urls[i] for i in [2, 0, 3, 1, 3, 0, 2, 0]])

    def test_directional_roles_and_crop(self):
        bindings = self.cfg['characters']['adventurer_v1']['animations']
        for role in ['walk_up', 'walk_down', 'idle_side', 'idle_up', 'idle_down']:
            bindings[role] = role
            self.cfg['animation_sequences'][role] = dict(character='adventurer_v1', fps=4,
                frames=[dict(url=self.urls[1],crop=[1,1,6,10]),dict(url=self.urls[2],crop=[1,1,6,10])])
        self.app.configure_character(self.cfg)
        self.app.motion_direction = 'up'
        self.app.anim_frame = 0
        key = self.app.walking_sprite_name()
        self.assertTrue(key.startswith(self.urls[1]))
        self.assertEqual(self.app.raw_sprites[key].get_size(), (6,10))
        with patch.object(module.time, 'monotonic', return_value=self.app.idle_started+0.3):
            self.assertTrue(self.app.idle_sprite_name().startswith(self.urls[2]))
        self.app.motion_direction = 'side'
        self.assertEqual(self.app.walking_sprite_name(), self.urls[2])

    def test_mixed_character_rejected_without_replacing_walk(self):
        self.app.configure_character(self.cfg)
        original = list(self.app.walk_frames)
        bad = copy.deepcopy(self.cfg)
        bad['animation_sequences']['v1:walk']['character'] = 'adventurer_v2'
        with self.assertRaises(ValueError):
            self.app.apply_remote_config(bad)
        self.assertEqual(self.app.walk_frames, original)
        self.assertEqual(self.app.cfg, self.cfg)

    def test_gesture_binding_clock_and_physical_scale(self):
        self.cfg['characters']['adventurer_v1']['animations']['sleeping'] = 'sleep'
        self.cfg['animation_sequences']['sleep'] = dict(character='adventurer_v1', fps=4,
            frames=[dict(url=url, reference_height=24, anchor_x=0.35) for url in self.urls[:2]])
        self.app.configure_character(self.cfg)
        with patch.object(module.time, 'monotonic', return_value=10):
            first = self.app.gesture_sprite_name('sleeping')
        with patch.object(module.time, 'monotonic', return_value=10.3):
            second = self.app.gesture_sprite_name('sleeping')
        self.assertNotEqual(first, second)
        self.app.gesture_role = None
        with patch.object(module.time, 'monotonic', return_value=20):
            self.assertEqual(self.app.gesture_sprite_name('sleeping'), first)
        self.app.trap.update(scale_at_y_min=240, scale_at_y_max=240)
        sprite = self.app.get_perspective_sprite(first, 0, False)
        self.assertEqual(sprite.get_height(), 120)
        self.assertEqual(self.app.sprite_metrics[first]['anchor_x'], 0.35)
        bad = copy.deepcopy(self.cfg)
        bad['animation_sequences']['sleep']['frames'][0]['reference_height'] = 0
        with self.assertRaises(ValueError):
            self.app.configure_character(bad)

    def test_unknown_frame_and_invalid_fps_rejected(self):
        for value in [0, float('nan'), 100]:
            bad = copy.deepcopy(self.cfg)
            bad['animation_sequences']['v1:walk']['fps'] = value
            with self.assertRaises(ValueError):
                self.app.configure_character(bad)
        bad = copy.deepcopy(self.cfg)
        bad['animation_sequences']['v1:walk']['frames'][0]['url'] = '/assets/characters/adventurer/inspect.png'
        with self.assertRaises(ValueError):
            self.app.configure_character(bad)

    def test_config_save_retains_sequences_and_other_fields(self):
        self.app.configure_character(self.cfg)
        self.app.trap = {}
        self.app.obstacles = self.app.props = self.app.event_mappings = self.app.apps = []
        self.app.ui_font_scale = 'large'
        self.app.char_x = self.app.char_y = 0
        self.app.clamp_to_walkable = lambda x, y: (x, y)
        changed = copy.deepcopy(self.cfg)
        changed['reference_sprite'] = {'url': self.urls[0]}
        with patch.object(module, 'CONFIG_PATH', str(self.root/'room_config.json')), patch.object(module, 'DEFAULT_CONFIG_PATH_PI', str(self.root/'room_config.json')):
            self.app.apply_remote_config(changed)
        saved = json.loads((self.root/'room_config.json').read_text())
        self.assertEqual(saved['animation_sequences'], changed['animation_sequences'])
        self.assertEqual(saved['reference_sprite'], changed['reference_sprite'])
        self.app.configure_character(saved)
        self.assertEqual(self.app.walk_fps, 4)

    def test_action_uses_updated_linked_location(self):
        self.app.char_x = self.app.char_y = 0
        self.app.cfg['interaction_spots'] = [dict(id='desk', x=321, y=456)]
        with patch.object(self.app, 'clamp_to_walkable', side_effect=RuntimeError('stop after resolving target')) as clamp:
            with self.assertRaisesRegex(RuntimeError, 'stop after resolving target'):
                self.app.trigger_action(dict(spot_id='desk', x=1, y=2))
            clamp.assert_called_once_with(321, 456)


if __name__ == '__main__':
    unittest.main()
