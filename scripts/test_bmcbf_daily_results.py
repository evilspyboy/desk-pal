import sys,tempfile,unittest
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bmcbf_daily_results import daily_summary

class Results(unittest.TestCase):
 def test_today_actual_results_not_task_labels_or_old_news(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'bot.log'
   p.write_text('\n'.join([
    '2026-10-03 08:00:00,001 - actions.social_media.post_daily_to_social_media - INFO - Facebook post successful: private',
    '2026-10-04 07:00:00,001 - actions.email.unread_summarizer - INFO - Discord summary notification sent successfully.',
    '2026-10-04 07:10:00,001 - actions.email.unread_summarizer - INFO - No unread emails found.',
    '2026-10-04 07:11:00,001 - actions.social_media.promote_wordpress_post - INFO - Facebook post successful: private',
    '2026-10-04 07:12:00,001 - actions.wordpress.wordpress_utils - ERROR - private error detail',
   ]))
   result=daily_summary(p,datetime(2026,10,4,8))
   self.assertIn('Today Oct 4',result)
   self.assertIn('- 1 email summaries today',result)
   self.assertEqual(len(result.splitlines()),5)
   self.assertTrue(result.splitlines()[-1].startswith('- Last article: '))
   self.assertIn("Today's events: unavailable",result)
   self.assertNotIn('private',result)
   self.assertIsNone(daily_summary(p,datetime(2026,10,5,8)))
if __name__=='__main__':unittest.main()
