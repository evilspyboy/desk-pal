from pathlib import Path
import sys
import tempfile
import unittest
import json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scratch/satellite_deps'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from satellite_bmcbf import BmCBFSatellite, button_summary


class Tasks(unittest.TestCase):
    def test_button_uses_dated_latest_check_per_category_not_static_ticker(self):
        data={'activity':'Idle','last_update':'2026-10-04T00:15:00','ticker':['Stale game news'],
              'recent_events':[{'event':'Checked Emails','timestamp':'23:55:00'},
                               {'event':'Checked Emails','timestamp':'00:10:00'},
                               {'event':'Promoted Articles to Socials','timestamp':'00:05:00'}]}
        result=button_summary(data)
        self.assertIn('04 Oct 00:10 - Checked Emails',result)
        self.assertNotIn('Stale game news',result)
        self.assertNotIn('23:55',result)
        data['recent_events']=[{'event':'Checked Emails','timestamp':'23:55:00'}]
        self.assertIn('03 Oct 23:55',button_summary(data))
    def test_newer_scheduler_file_supplies_completed_tasks(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'companion.json'
            current={'last_update':'2026-10-03T08:00:00','recent_events':[{'event':'Checked Emails (none)','timestamp':'08:00:00'}]}
            path.write_text(json.dumps(current),encoding='utf-8')
            agent=BmCBFSatellite(companion_state_path=path);agent.tasks_initialized=True
            sent=[];agent.post_deskpal=lambda endpoint,payload:sent.append(payload) or True
            merged=agent.merge_completion_state({'last_update':'2026-10-02T18:00:00'})
            agent.relay_completed_tasks(merged);agent.relay_completed_tasks(merged)
            self.assertEqual(len(sent),1);self.assertEqual(sent[0]['event'],'email_check')
            self.assertEqual(agent.merge_completion_state({'last_update':'2026-10-03T09:00:00'})['last_update'],'2026-10-03T09:00:00')
    def test_baseline_new_run_restart_and_unchanged_poll(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.json'
            sent=[];agent=BmCBFSatellite(state_path=path)
            agent.post_deskpal=lambda p,d:sent.append((p,d)) or True
            data={'last_update':'2026-10-02T18:00:00','recent_events':[{'event':'Checked Emails','timestamp':'17:50:00'}]}
            agent.relay_completed_tasks(data);self.assertEqual(sent,[])
            data['recent_events'].insert(0,{'event':'Checked Emails','timestamp':'18:00:00'})
            agent.relay_completed_tasks(data);agent.relay_completed_tasks(data)
            self.assertEqual(len(sent),1);self.assertEqual(sent[0][1]['event'],'email_check');self.assertEqual(sent[0][1]['task_phase'],'completed')
            agent=BmCBFSatellite(state_path=path);agent.post_deskpal=lambda p,d:sent.append((p,d)) or True
            agent.relay_completed_tasks(data);self.assertEqual(len(sent),1)
            data['last_update']='2026-10-02T18:10:00';data['recent_events'].insert(0,{'event':'Checked Emails','timestamp':'18:10:00'})
            agent.relay_completed_tasks(data);self.assertEqual(len(sent),2)
            self.assertNotEqual(sent[0][1]['task_run_id'],sent[1][1]['task_run_id'])

    def test_failed_send_is_retried(self):
        agent=BmCBFSatellite();agent.relay_completed_tasks({'recent_events':[]})
        data={'last_update':'2026-10-02T18:00:00','recent_events':[{'event':'Calendar sweep','timestamp':'18:00:00'}]}
        agent.post_deskpal=lambda *args:False;agent.relay_completed_tasks(data);self.assertEqual(agent.seen_tasks,[])
        agent.post_deskpal=lambda *args:True;agent.relay_completed_tasks(data);self.assertEqual(len(agent.seen_tasks),1)


if __name__=='__main__':unittest.main()
