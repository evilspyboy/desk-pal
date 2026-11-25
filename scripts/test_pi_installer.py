import ast, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from install_pi import plan
ROOT=Path(__file__).resolve().parents[1]

class InstallerTests(unittest.TestCase):
    def test_generic_user_service(self):
        p=plan('/home/newuser')
        self.assertIn('/home/newuser/.local/share/deskpal/src/deskpal_app.py',p['unit'])
        self.assertNotIn('/home/admin',str(p))
        self.assertIn('import-environment DISPLAY WAYLAND_DISPLAY',p['launcher'])
        self.assertIn('DESKPAL_DATA_DIR=',p['unit'])
        self.assertNotIn('User=root',p['unit'])

    def test_unsafe_paths_are_rejected(self):
        for path in ('relative','/home/a b','/home/a;shutdown','/home/../etc'):
            with self.assertRaises(ValueError):plan(path)

    def test_explicit_root_controls_configuration_and_assets(self):
        tree=ast.parse((ROOT/'src/deskpal_app.py').read_text(encoding='utf-8'))
        selected=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('pi_path','get_active_config_path')]
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'DESKPAL_DATA_DIR':tmp}):
            namespace={'os':os,'CONFIG_PATH':str(Path(tmp)/'config/room_config.json')}
            exec(compile(ast.Module(body=selected,type_ignores=[]),'paths','exec'),namespace)
            self.assertEqual(namespace['pi_path']('assets'),str(Path(tmp)/'assets'))
            self.assertEqual(namespace['get_active_config_path'](),namespace['CONFIG_PATH'])

if __name__=='__main__':unittest.main()
