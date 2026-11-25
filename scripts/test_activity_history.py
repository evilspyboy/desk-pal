import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from activity_history import append, recent
from activity_queue import ActivityQueue


class History(unittest.TestCase):
    def test_filter_applies_before_history_limit_and_retains_heartbeat_playback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'history.jsonl'
            append(path,'received',app_id='custom',source_event='job_finished')
            append(path,'completed',app='Custom',source_event='heartbeat')
            for _ in range(6):append(path,'received',app_id='custom',source_event='heartbeat')
            self.assertEqual(len(recent(path,limit=2)),2)
            filtered=recent(path,limit=2,include_heartbeat_receipts=False)
            self.assertEqual([r['event'] for r in filtered],['received','completed'])
            self.assertEqual(filtered[0]['source_event'],'job_finished')

    def test_queue_explains_unrestricted_loop_without_overriding_attention(self):
        import math
        from unittest.mock import patch
        queue=ActivityQueue();queue.active=({'source_event':'job','_received_at':100},'Custom')
        queue.started=10;queue.arrived=12;queue.dwell=math.inf
        with patch('activity_queue.time.monotonic',return_value=20),patch('activity_queue.time.time',return_value=120):
            status=queue.snapshot()
            self.assertEqual(status['state'],'waiting_for_event')
            self.assertEqual(status['playback_seconds'],8)
            self.assertEqual(status['active']['received_age_seconds'],20)
            queue.paused_at=15
            self.assertEqual(queue.snapshot()['playback_seconds'],3)
            queue.active[0]['_attention_waiting']=True
            self.assertEqual(queue.snapshot()['state'],'waiting_for_interaction')
            queue.active[0].clear();queue.active[0]['_hold_popup_until_dismissed']=True
            self.assertEqual(queue.snapshot()['state'],'waiting_for_dismissal')
            queue.active[0].clear();queue.enqueue(({},'Next'))
            self.assertEqual(queue.snapshot()['state'],'playing')

    def test_persistence_and_rotation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'history.jsonl'
            append(path, 'received', app_id='custom', source_event='heartbeat')
            self.assertEqual(recent(path)[0]['source_event'], 'heartbeat')
            with path.open('a') as stream:
                stream.write(' ' * 2_000_000 + '\n')
            append(path, 'queued', activity_id='turn')
            self.assertTrue(Path(str(path)+'.1').exists())
            self.assertEqual([r['event'] for r in recent(path)], ['received', 'queued'])
            self.assertEqual(recent(path, limit=1)[0]['event'], 'queued')

    def test_queue_lifecycle_is_correlated(self):
        rows=[]
        app=SimpleNamespace(is_sleeping=False,edit_mode=False,char_x=0,char_y=0,target_x=0,target_y=0,
            scene_journey=[],journey_arriving=False,rest_transition=None,target_animation='inspect',current_anim='inspect',
            action_sequence=lambda _: {'fps':2,'playback_mode':'once'},sequence_tick_limit=lambda _:4,
            trigger_action=lambda *args:None,audit_activity=lambda event,**fields:rows.append(dict(event=event,**fields)))
        queue=ActivityQueue();queue.enqueue(({'_activity_id':'turn','id':'check','source_event':'heartbeat'},'Custom'))
        queue.tick(app,0);queue.tick(app,1);queue.tick(app,3)
        self.assertEqual([r['event'] for r in rows], ['started','arrived','completed'])
        self.assertTrue(all(r['activity_id']=='turn' for r in rows))
        self.assertEqual(rows[-1]['playback_seconds'], 2)


if __name__=='__main__':
    unittest.main()
