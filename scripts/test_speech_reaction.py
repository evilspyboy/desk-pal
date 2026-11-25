import sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from speech_reaction import tick,frame

class SpeechReactionTests(unittest.TestCase):
    def app(self):
        self.state='generating'
        return SimpleNamespace(speech_output=SimpleNamespace(snapshot=lambda:dict(state=self.state)),
            character_sequences={'talking':dict(frames=['closed','open','wide','round'],fps=6)},
            is_sleeping=False,edit_mode=False,activity_queue=SimpleNamespace(started=1,arrived=2),
            gesture_started=3,idle_started=4,active_rest_role='sitting_rest',
            rest_transition={'started':5},sensor_reaction={'started':6},
            char_x=200,char_y=400,target_x=500,target_y=600,current_anim='walk',
            active_popup_modal={'title':'Read aloud'},audit_activity=lambda *a,**k:None)

    def test_playback_only_pause_and_restore_with_popup(self):
        a=self.app();self.assertFalse(tick(a,10));self.state='playing'
        self.assertTrue(tick(a,11));self.assertEqual(frame(a.speech_reaction,11.34),'wide')
        self.assertTrue(tick(a,12));self.state='idle';self.assertFalse(tick(a,13))
        self.assertIsNone(a.speech_reaction)
        self.assertEqual((a.activity_queue.started,a.activity_queue.arrived),(3,4))
        self.assertEqual((a.gesture_started,a.idle_started),(5,6))
        self.assertEqual(a.rest_transition['started'],7)
        self.assertEqual(a.sensor_reaction['started'],8)
        self.assertEqual((a.char_x,a.char_y,a.target_x,a.target_y,a.current_anim),(200,400,500,600,'walk'))
        self.assertEqual(a.active_popup_modal,{'title':'Read aloud'})

    def test_sleep_and_missing_character_sequence_do_not_override(self):
        a=self.app();self.state='playing';a.is_sleeping=True
        self.assertFalse(tick(a,1));a.is_sleeping=False;a.character_sequences={}
        self.assertFalse(tick(a,2))

    def test_stop_releases_visual_pause(self):
        a=self.app();self.state='playing';self.assertTrue(tick(a,1))
        self.state='error';self.assertFalse(tick(a,2));self.assertIsNone(a.speech_reaction)

if __name__=='__main__':unittest.main()
