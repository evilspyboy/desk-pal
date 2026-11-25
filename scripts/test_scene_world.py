import sys, unittest, copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from scene_world import ensure_world, sync_scene, activate_scene, find_route
from seed_scenes import seed

class Scenes(unittest.TestCase):
    def config(self):
        return seed(dict(theme='cozy_study',walkable_trapezoid=dict(y_min=400,y_max=700,back_x_min=200,back_x_max=900,front_x_min=100,front_x_max=1100,scale_at_y_min=200,scale_at_y_max=350),obstacles=[],props=[],interaction_spots=[dict(id='desk',x=400,y=500)],pose_rules={'typing':{'valid_spots':['desk']}}))
    def test_migration_and_isolation(self):
        cfg=self.config();original=copy.deepcopy(cfg['interaction_spots']);activate_scene(cfg,'video_store');self.assertEqual(cfg['interaction_spots'],[])
        cfg['interaction_spots'].append(dict(id='counter'));sync_scene(cfg);activate_scene(cfg,'cozy_study');self.assertEqual(cfg['interaction_spots'],original)
        self.assertEqual(cfg['scene_placements']['video_store']['interaction_spots'][0]['id'],'counter')
    def test_multi_hop_bidirectional(self):
        cfg=self.config();route=find_route(cfg,'cozy_study','resort_beach');self.assertEqual([s['to']['scene'] for s in route],['video_store','resort_beach'])
        self.assertEqual(len(find_route(cfg,'resort_beach','cozy_study')),2)
        self.assertEqual(find_route(cfg,'cozy_study','cozy_study'),[])
    def test_disconnected_or_deleted_endpoint(self):
        cfg=self.config();cfg['scenes']['video_store']['portals']=[]
        with self.assertRaises(ValueError):find_route(cfg,'cozy_study','resort_beach')
    def test_blocked_route(self):
        cfg=self.config()
        with self.assertRaises(ValueError):find_route(cfg,'cozy_study','resort_beach',lambda *args:False)
    def test_seed_preserves_user_edit(self):
        cfg=self.config();cfg['scenes']['video_store']['name']='My store';seed(cfg);self.assertEqual(cfg['scenes']['video_store']['name'],'My store')
    def test_disabled_scene_keeps_data_and_blocks_routes(self):
        cfg=self.config();before=copy.deepcopy(cfg['scene_links']);cfg['scenes']['video_store']['enabled']=False
        with self.assertRaises(ValueError):find_route(cfg,'cozy_study','resort_beach')
        with self.assertRaises(ValueError):activate_scene(cfg,'video_store')
        self.assertEqual(cfg['scene_links'],before)
        cfg['scenes']['video_store']['enabled']=True
        self.assertEqual(len(find_route(cfg,'cozy_study','resort_beach')),2)

if __name__=='__main__':unittest.main()
