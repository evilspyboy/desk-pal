import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from ai_connections import read,save,validate

class AiSettingsTests(unittest.TestCase):
    def test_private_profile_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'ai_settings.json';value=read(path)
            value['providers']['local']={'endpoint':'http://127.0.0.1:11434','model':'example'}
            value['chat_provider']='local';save(path,value)
            self.assertEqual(read(path),value)
            self.assertNotIn('enabled',value)
            save(path,{'tts':{'enabled':True}})
            save(path,{'chat_provider':'claude'})
            self.assertTrue(read(path)['tts']['enabled'])
            self.assertEqual(read(path)['providers']['local']['model'],'example')

    def test_invalid_endpoints_and_providers(self):
        for url in ['file:///test','https://user:secret@example.com','https://example.com/?key=secret','not-a-url']:
            with self.assertRaises(ValueError):validate({'providers':{'local':{'endpoint':url}}})
        with self.assertRaises(ValueError):validate({'tts_provider':'unknown'})

    def test_no_credentials_stored(self):
        value=validate({'providers':{'openai':{'model':'example','api_key':'secret'}}})
        self.assertNotIn('api_key',value['providers']['openai'])

    def test_speech_defaults_and_validation(self):
        value=validate({'tts':{'enabled':True,'model':'piper','voice':'en_US-lessac-low','keep_loaded':True}})
        self.assertTrue(value['tts']['keep_loaded']);self.assertEqual(value['tts']['model'],'piper')
        for tts in [{'voice':'../unknown'},{'speed':float('nan')},{'model':'wrong'},{'keep_loaded':1}]:
            with self.assertRaises(ValueError):validate({'tts':tts})

    def test_legacy_speech_migrates_without_losing_preferences(self):
        value=validate({'tts':{'enabled':True,'model':'kitten2','voice':'Bruno','keep_loaded':True},'chat_provider':'claude'})
        self.assertEqual(value['tts']['model'],'piper')
        self.assertEqual(value['tts']['voice'],'en_US-lessac-low')
        self.assertTrue(value['tts']['enabled']);self.assertTrue(value['tts']['keep_loaded'])
        self.assertEqual(value['chat_provider'],'claude')

    def test_on_device_profile_and_fallbacks(self):
        value = validate({
            'providers': {
                'on_device': {
                    'endpoint': '/custom/bin/llama-cli',
                    'model': '/custom/models/qwen.gguf'
                }
            },
            'chat_fallback_primary': 'local',
            'chat_fallback_secondary': 'on_device'
        })
        self.assertEqual(value['providers']['on_device']['endpoint'], '/custom/bin/llama-cli')
        self.assertEqual(value['providers']['on_device']['model'], '/custom/models/qwen.gguf')
        self.assertEqual(value['chat_fallback_primary'], 'local')
        self.assertEqual(value['chat_fallback_secondary'], 'on_device')
        self.assertEqual(value['chat_fallback_chain'], ['local', 'on_device'])

if __name__=='__main__':unittest.main()
