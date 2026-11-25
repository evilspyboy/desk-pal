"""Render the actual popup block headlessly; verify paging preserves every line."""
import ast
import math
import os
from pathlib import Path
import sys
import textwrap
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scratch/local_preview_deps'))
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame

SOURCE = (ROOT / 'src/deskpal_app.py').read_text(encoding='utf-8')
BLOCK = SOURCE[SOURCE.index('        # Retro SCUMM Popup Modal Card'):SOURCE.index('        # Safe Shutdown Modal')]
DRAW = compile(textwrap.dedent(BLOCK), '<production popup>', 'exec')
TREE = ast.parse(SOURCE)
CLASS = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == 'DeskPalApp')
TOUCH = next(node for node in CLASS.body if isinstance(node, ast.FunctionDef) and node.name == 'handle_touch_down')
SCOPE = {'pygame': pygame}
exec(compile(ast.Module(body=[TOUCH], type_ignores=[]), '<production touch>', 'exec'), SCOPE)


class Popups(unittest.TestCase):
    def test_pages_keep_large_text_readable_and_touch_does_not_dismiss(self):
        pygame.init()
        self.addCleanup(pygame.quit)
        app = SimpleNamespace(width=1280, height=720, screen=pygame.Surface((1280,720)),
            font_lg=pygame.font.Font(None,52), font_sm=pygame.font.Font(None,26),
            palette={'text':(255,255,255),'text_dim':(140,140,140),'surface_light':(50,50,60)},
            active_popup_modal={'title':'Travel','summary':'\n'.join('Deal %s: Destination $520 return, departs 7 December 2026' % i for i in range(12))},
            show_shutdown_modal=False, is_sleeping=False)
        scope = {'self':app, 'pygame':pygame, 'math':math}
        exec(DRAW, scope)
        expected = scope['lines']
        self.assertGreater(scope['page_count'], 1)
        seen = []
        while True:
            exec(DRAW, scope)
            page, size = scope['page'], scope['page_size']
            seen.extend(expected[page*size:(page+1)*size])
            self.assertLessEqual(scope['sy'], scope['card_y']+scope['card_h']-60)
            next_rect = next((rect for direction,rect in app.popup_page_buttons if direction == 1), None)
            if next_rect is None: break
            SCOPE['handle_touch_down'](app, next_rect.center)
            self.assertIsNotNone(app.active_popup_modal)
        self.assertEqual(seen, expected)
        previous = next(rect for direction,rect in app.popup_page_buttons if direction == -1)
        old = app.active_popup_modal['page']
        SCOPE['handle_touch_down'](app, previous.center)
        self.assertEqual(app.active_popup_modal['page'], old-1)
        SCOPE['handle_touch_down'](app, (640,510))
        self.assertIsNone(app.active_popup_modal)


if __name__ == '__main__': unittest.main()
