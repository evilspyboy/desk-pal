import sys,unittest,copy
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sensor_reaction import begin,tick,frame

class Reaction(unittest.TestCase):
    def app(self,active=None):
        seq=dict(frames=['a','b','c','d'],fps=4,playback_mode='once')
        return SimpleNamespace(is_sleeping=False,edit_mode=False,facing_left=False,
            character_sequences={'balance':seq},sequence_tick_limit=lambda _:4,
            char_x=120,char_y=300,target_x=600,target_y=500,
            target_animation='idle',current_anim='walk',_route_goal=(600,500),
            scene_journey=[{'to':'beach'}],gesture_started=8,idle_started=4,
            activity_queue=SimpleNamespace(active=active,started=6,arrived=7),
            audit_activity=lambda *args,**kwargs:None)
    def test_pause_then_resume_same_destination_route_and_activity(self):
        active=({'id':'application'},'App');a=self.app(active)
        original=(a.target_x,a.target_y,a._route_goal,copy.deepcopy(a.scene_journey),a.current_anim,a.target_animation)
        self.assertTrue(begin(a,{'animation':'balance','facing':'left'},10))
        self.assertTrue(tick(a,10.5));self.assertEqual(frame(a.sensor_reaction,10.5),'c')
        self.assertTrue(a.sensor_reaction['facing_left'])
        self.assertFalse(tick(a,11));self.assertIsNone(a.sensor_reaction)
        self.assertEqual((a.target_x,a.target_y,a._route_goal,a.scene_journey,a.current_anim,a.target_animation),original)
        self.assertIs(a.activity_queue.active,active)
        self.assertEqual((a.activity_queue.started,a.activity_queue.arrived),(7,8))
        self.assertEqual((a.gesture_started,a.idle_started),(9,5))
    def test_protected_interactions_and_no_stacking(self):
        for key,value in [('active_popup_modal',{}),('is_sleeping',True),('edit_mode',True),('active_rest_role','seated_back')]:
            a=self.app();setattr(a,key,value or {'title':'popup'})
            self.assertFalse(begin(a,{'animation':'balance'},10))
        for key in ['_attention_waiting','_button_action']:
            self.assertFalse(begin(self.app(({key:True},'App')),{'animation':'balance'},10))
        a=self.app();self.assertTrue(begin(a,{'animation':'balance'},10));self.assertFalse(begin(a,{'animation':'balance'},10.2))
    def test_popup_cancels_visual_pause_without_consuming_it(self):
        a=self.app();begin(a,{'animation':'balance'},10);a.active_popup_modal={'title':'Button'}
        self.assertFalse(tick(a,10.2));self.assertEqual(a.active_popup_modal,{'title':'Button'})

if __name__=='__main__':unittest.main()
