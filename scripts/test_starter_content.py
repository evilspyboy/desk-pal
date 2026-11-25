"""Verify the distributable starter is separate from personal applications."""
import json, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from backup_packages import unpack
from integration_packages import prepare

class StarterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _,cls.cfg,cls.files=unpack((ROOT/'examples/starter-content.zip').read_bytes())

    def test_personal_connections_and_buttons_are_absent(self):
        self.assertEqual(self.cfg['apps'],[])
        self.assertEqual(self.cfg['event_mappings'],[])
        self.assertTrue(all(s['app_id'] in ('','system_sleep','system_power') for s in self.cfg['switches']))
        text=json.dumps(self.cfg)
        for value in ('192.168.201.','bmcbf','fuel_tracker','travel_radar','store_monitor'):
            self.assertNotIn(value,text)

    def test_content_is_present(self):
        self.assertEqual(set(self.cfg['scenes']),{'cozy_study','video_store','resort_beach','apartment'})
        self.assertIn(self.cfg['active_character'],self.cfg['characters'])
        for sequence in self.cfg['characters'][self.cfg['active_character']]['animations'].values():
            self.assertIn(sequence,self.cfg['animation_sequences'])
        self.assertTrue(any(name.startswith('assets/themes/') for name in self.files))
        self.assertTrue(any(name.startswith('assets/characters/') for name in self.files))

    def test_example_import_does_not_replace_content(self):
        merged,app,missing,_,_=prepare((ROOT/'examples/integration.example.json').read_bytes(),self.cfg)
        self.assertEqual(missing,[])
        self.assertEqual(app['id'],'example_app')
        self.assertFalse(app['source_enabled'])
        self.assertEqual(app['switch_id'],0)
        self.assertEqual(merged['scenes'],self.cfg['scenes'])
        self.assertEqual(merged['animation_sequences'],self.cfg['animation_sequences'])

if __name__=='__main__':unittest.main()
