import sys,unittest,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sensor_events import SensorEvents,ensure_sensor_source

class Sensors(unittest.TestCase):
    def setUp(self):
        self.engine=SensorEvents();self.mount=dict(axes=[0,1,2],signs=[1,1,1],neutral=[0,0])
        self.options=dict(enabled=True,mild_degrees=12,strong_degrees=28,cooldown_seconds=1,shake_g=.45)
        self.now=10
    def motion(self,forward=0,side=0,count=12,magnitude=1):
        values=[]
        f,s=math.radians(forward),math.radians(side)
        vector=[-math.sin(s),math.sin(f)*math.cos(s),math.cos(f)*math.cos(s)]
        for _ in range(count):
            self.now+=.1
            imu=dict(state='live',at=self.now,accel_g=[v*magnitude for v in vector])
            values+=self.engine.tick(self.options,self.mount,imu,{},self.now)
        return [v['event'] for v in values]
    def test_edges_escalation_and_neutral_rearm(self):
        self.assertEqual(self.motion(side=18),['tilt_right'])
        self.assertEqual(self.motion(side=18,count=50),[])
        self.assertEqual(self.motion(side=40),['tilt_right_strong'])
        self.motion();self.assertEqual(self.motion(side=-18),['tilt_left'])
    def test_forward_back_and_calibrated_axes(self):
        self.assertEqual(self.motion(forward=18),['tilt_forward'])
        self.motion();self.assertEqual(self.motion(forward=-40),['tilt_back_strong'])
        self.engine=SensorEvents();self.mount=dict(axes=[1,0,2],signs=[1,-1,1],neutral=[0,0])
        out=[]
        for i in range(10):
            now=50+i*.1
            out+=self.engine.tick(self.options,self.mount,dict(state='live',at=now,accel_g=[-math.sin(.35),0,math.cos(.35)]),{},now)
        self.assertEqual([v['event'] for v in out],['tilt_forward'])
    def test_shake_requires_two_impulses_and_cooldown(self):
        self.assertEqual(self.motion(count=1,magnitude=1.8),[])
        self.assertEqual(self.motion(count=1,magnitude=1.8),['shake'])
        self.assertEqual(self.motion(count=2,magnitude=1.8),[])
    def test_disabled_stale_and_calibration(self):
        imu=dict(state='live',at=10,accel_g=[0,1,0])
        for now in [20,21]:self.assertEqual(self.engine.tick(self.options,self.mount,imu,{},now),[])
        imu['at']=22
        self.assertEqual(self.engine.tick(self.options,self.mount,imu,{},22,True),[])
        self.options['enabled']=False
        self.assertEqual(self.motion(side=45),[])
    def test_presence_absence_return_and_outage(self):
        self.options.update(presence_enabled=True,absence_seconds=5)
        def tick(now,present,state='receiving'):
            return self.engine.tick(self.options,self.mount,{},dict(state=state,targets=[{}] if present else [],_monotonic_at=now),now)
        self.assertEqual(tick(10,True)+tick(11,True),[])
        tick(12,False);tick(17,False);tick(18,True)
        self.assertEqual([v['event'] for v in tick(19,True)],['person_returned'])
        self.assertEqual(tick(20,True)+tick(21,True),[])
        tick(22,False);tick(29,False,'stale');tick(30,True)
        self.assertEqual(tick(31,True),[])
    def test_source_preserves_existing_mappings(self):
        cfg={'apps':[]};source=ensure_sensor_source(cfg);source['actions'].append({'id':'mine'})
        self.assertIs(ensure_sensor_source(cfg),source)
        self.assertEqual(source['actions'],[{'id':'mine'}]);self.assertEqual(len(cfg['apps']),1)
    def test_half_second_cooldown_allows_rearmed_repeat(self):
        self.options['cooldown_seconds']=.5
        self.assertEqual(self.motion(side=18),['tilt_right'])
        self.motion(count=10)
        self.assertEqual(self.motion(side=18),['tilt_right'])
        self.assertEqual(self.motion(side=18,count=30),[])

if __name__=='__main__':unittest.main()
