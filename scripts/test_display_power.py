from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from display_power import DisplayPower
class PowerTests(unittest.TestCase):
    def test_powerdown_wake_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);panel=root/'panel';panel.mkdir();(panel/'bl_power').write_text('0');(panel/'brightness').write_text('15')
            p=DisplayPower(root,root/'saved.json');self.assertTrue(p.set_sleeping(True));self.assertEqual((panel/'bl_power').read_text(),'4');self.assertTrue(p.is_off);self.assertEqual((panel/'brightness').read_text(),'0')
            p=DisplayPower(root,root/'saved.json');self.assertTrue(p.set_sleeping(False));self.assertEqual((panel/'bl_power').read_text(),'0');self.assertEqual((panel/'brightness').read_text(),'15')
    def test_unavailable_hardware(self):
        with tempfile.TemporaryDirectory() as directory:
            p=DisplayPower(directory);self.assertFalse(p.set_sleeping(True));self.assertFalse(p.is_off)
if __name__=='__main__':unittest.main()
