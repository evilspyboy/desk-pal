import sys, unittest, copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from action_targets import resolve_action_placement

class Targets(unittest.TestCase):
    def setUp(self):
        self.cfg={'active_scene':'study','interaction_spots':[
            {'id':'desk','x':100,'y':200,'facing':'left','animation':'typing','animations':['typing','inspect']},
            {'id':'table','x':300,'y':400,'animation':'inspect'},
            {'id':'wrong_scene','x':500,'y':400,'animation':'drink'}],
            'pose_rules':{'typing':{'valid_spots':['desk']}}}
        self.sequences={'typing':{'frames':[1]},'inspect':{'frames':[1]},'drink':{'frames':[1],'allowed_scenes':['beach']}}
    def resolve(self,action,**kwargs):
        return resolve_action_placement(self.cfg,action,self.sequences,choose=lambda choices:choices[0],**kwargs)
    def test_gesture_uses_placement_and_keeps_original(self):
        action={'target_mode':'gesture','animation':'typing','spot_id':'stale','speech':'hello'};before=copy.deepcopy(action)
        result=self.resolve(action);self.assertEqual(result['spot_id'],'desk');self.assertEqual(result['facing'],'left');self.assertEqual(action,before)
    def test_location_and_any(self):
        result=self.resolve({'target_mode':'location','spot_id':'table','animation':'typing'})
        self.assertEqual(result['animation'],'inspect')
        result=self.resolve({'target_mode':'any'},reachable=lambda spot:spot['id']!='desk')
        self.assertEqual(result['spot_id'],'table')
    def test_unreachable_and_missing_matches(self):
        with self.assertRaises(ValueError):self.resolve({'target_mode':'gesture','animation':'typing'},reachable=lambda spot:False)
        with self.assertRaises(ValueError):self.resolve({'target_mode':'location'})
        with self.assertRaises(ValueError):self.resolve({'target_mode':'gesture','animation':'drink'})
        self.sequences['typing']['transition_only']=True
        with self.assertRaises(ValueError):self.resolve({'target_mode':'gesture','animation':'typing'})
    def test_rules_and_legacy(self):
        self.cfg['pose_rules']['typing']['valid_spots']=[]
        with self.assertRaises(ValueError):self.resolve({'target_mode':'gesture','animation':'typing'})
        action={'spot_id':'desk','animation':'typing','x':5};self.assertEqual(self.resolve(action),action)
    def test_current_uses_runtime_position_not_stale_scene_or_spot(self):
        action={'target_mode':'current','animation':'inspect','scene':'beach','spot_id':'table','x':99,'target_prop':'old'}
        result=self.resolve(action,current=(420,550))
        self.assertEqual((result['x'],result['y']),(420,550))
        self.assertNotIn('scene',result);self.assertNotIn('spot_id',result);self.assertNotIn('target_prop',result)
        self.assertEqual(action['scene'],'beach')
        with self.assertRaises(ValueError):self.resolve(action)
        with self.assertRaises(ValueError):self.resolve({'target_mode':'current','animation':'drink'},current=(420,550))

if __name__=='__main__':unittest.main()
