import io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from piper_voices import VoiceLibrary,resolve,voice_id

CONFIG=json.dumps({'audio':{'sample_rate':22050},'phoneme_id_map':{'a':[1]},'num_speakers':1}).encode()
class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.library=VoiceLibrary(self.root,sys.executable)

    def test_pair_is_hidden_until_validated_and_never_replaced(self):
        self.library.upload('custom_voice','model',io.BytesIO(b'model'),5)
        self.assertEqual(self.library.snapshot()['voices'],[])
        with patch('piper_voices.subprocess.run',return_value=SimpleNamespace(returncode=0)):
            self.library.upload('custom_voice','config',io.BytesIO(CONFIG),len(CONFIG))
        self.assertEqual(self.library.snapshot()['voices'][0]['id'],'custom_voice')
        self.assertEqual(resolve('custom_voice',self.root).read_bytes(),b'model')
        with self.assertRaises(ValueError):self.library.upload('custom_voice','model',io.BytesIO(b'new'),3)
        self.assertEqual(resolve('custom_voice',self.root).read_bytes(),b'model')

    def test_invalid_config_and_interrupted_upload_are_removed(self):
        with self.assertRaises(ValueError):self.library.upload('short','model',io.BytesIO(b'x'),10)
        self.assertFalse((self.root/'.upload-short').exists())
        self.library.upload('bad','model',io.BytesIO(b'model'),5)
        with self.assertRaises(ValueError):self.library.upload('bad','config',io.BytesIO(b'{}'),2)
        self.assertFalse((self.root/'.upload-bad').exists())
        self.assertEqual(self.library.snapshot()['voices'],[])

    def test_missing_invalid_and_traversal_names(self):
        for name in ('../escape','-option','a/b','a\\b','',None):
            with self.assertRaises(ValueError):voice_id(name)
        with self.assertRaises(ValueError):resolve('missing',self.root)
        with self.assertRaises(ValueError):self.library.upload('missing','config',io.BytesIO(CONFIG),len(CONFIG))

    def test_backend_failure_does_not_install(self):
        self.library.upload('broken','model',io.BytesIO(b'model'),5)
        with patch('piper_voices.subprocess.run',return_value=SimpleNamespace(returncode=1,stderr='invalid ONNX')):
            with self.assertRaises(ValueError):self.library.upload('broken','config',io.BytesIO(CONFIG),len(CONFIG))
        self.assertFalse((self.root/'broken').exists())
        self.assertFalse((self.root/'.upload-broken').exists())

if __name__=='__main__':unittest.main()
