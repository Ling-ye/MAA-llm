import datetime,importlib.util,json,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1] / 'scripts'
spec=importlib.util.spec_from_file_location('gf2_adapter',ROOT/'gf2_safe.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
class GF2SafeTests(unittest.TestCase):
 def test_plan_scope(self):
  self.assertEqual(g.plan()['tasks'],['PrepareDailyTasks','PublicAreaDailyTasks','ClaimRewardTasks'])
  self.assertIn('使用完接入密钥(体力药水)',g.plan()['disabled'])
  self.assertIn('商城免费每日补给箱购买',g.plan()['disabled'])
 def test_reset_uses_china_not_machine_timezone(self):
  self.assertEqual(g.game_day(datetime.datetime(2026,11,16,19,59,tzinfo=datetime.timezone.utc)),'2026-11-16')
  self.assertEqual(g.game_day(datetime.datetime(2026,11,16,20,0,tzinfo=datetime.timezone.utc)),'2026-11-17')
 def test_naive_time_rejected(self):
  with self.assertRaises(ValueError):g.game_day(datetime.datetime(2026,1,1))
 def test_stop_before_launch(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'STOP').touch()
   with self.assertRaises(g.Blocked):g.gate(root,'2026-11-16')
 def test_any_attempt_prevents_replay(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);ledger=g.gate(root,'2026-11-16');g.atomic_json(ledger,{'verified':False})
   with self.assertRaises(g.Blocked):g.gate(root,'2026-11-16')
 def test_failed_callback_raises(self):
  job=type('Job',(),{'done':True,'succeeded':False})()
  with self.assertRaises(RuntimeError):g.wait_job(job,Path('.'),time.monotonic()+3)
 def test_stop_during_job(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'STOP').touch();job=type('Job',(),{'done':False})()
   with self.assertRaisesRegex(RuntimeError,'STOP'):g.wait_job(job,root,time.monotonic()+3)
 def test_timeout(self):
  with tempfile.TemporaryDirectory() as d:
   job=type('Job',(),{'done':False})()
   with self.assertRaisesRegex(RuntimeError,'timeout'):g.wait_job(job,Path(d),time.monotonic()-1)
 def test_atomic_receipt(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'state'/'r.json';g.atomic_json(p,{'verified':False});self.assertFalse(json.loads(p.read_text())['verified'])
if __name__=='__main__':unittest.main()
