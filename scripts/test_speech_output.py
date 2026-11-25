import sys
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from speech_output import SpeechOutput

class SpeechTests(unittest.TestCase):
    def test_disabled_and_invalid_inputs_never_launch(self):
        output=SpeechOutput()
        with patch('speech_output.read',return_value={'tts':{'enabled':False}}),patch('speech_output.subprocess.Popen') as launch:
            for text in ['',None,'x'*501,'hello']:
                with self.assertRaises(ValueError):output.speak(text,'ignored',{'enabled':True})
            launch.assert_not_called()

    def test_hardware_speaker_must_be_enabled(self):
        with patch('speech_output.read',return_value={'tts':{'enabled':True}}):
            with self.assertRaises(ValueError):SpeechOutput().speak('hello','ignored',{'enabled':False})

    def test_snapshot_is_copy_and_idle_stop_is_safe(self):
        output=SpeechOutput();copy=output.snapshot();copy['state']='playing'
        self.assertEqual(output.snapshot()['state'],'idle');output.stop()

    def test_turning_retention_off_releases_idle_worker(self):
        output=SpeechOutput();output.synth=Mock();output.synth.poll.return_value=None
        with patch.object(output,'_terminate') as terminate:
            output.configure({'enabled':True,'keep_loaded':False})
            terminate.assert_called_once();self.assertIsNone(output.synth)

    def test_retention_off_during_request_defers_release(self):
        output=SpeechOutput();worker=Mock();output.synth=worker;output.status['state']='generating'
        with patch.object(output,'_terminate') as terminate:
            output.configure({'enabled':True,'keep_loaded':False})
            terminate.assert_not_called();self.assertIs(output.synth,worker)
            output.synth=None

    def test_changing_voice_releases_retained_idle_model(self):
        output=SpeechOutput();output.synth=Mock();output.synth_voice='voice_a'
        with patch.object(output,'_terminate') as terminate:
            output.configure({'enabled':True,'keep_loaded':True,'voice':'voice_b'})
            terminate.assert_called_once();self.assertIsNone(output.synth)

if __name__=='__main__':unittest.main()
