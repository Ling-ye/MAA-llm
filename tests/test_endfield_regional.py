import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'scripts'))
import endfield_common as c
import endfield_regional as r
class RegionalTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'state').mkdir();self.ps=[patch.object(c,'ROOT',self.root),patch.object(r,'ROOT',self.root)]
  for p in self.ps:p.start()
 def tearDown(self):
  for p in reversed(self.ps):p.stop()
  self.tmp.cleanup()
 def plan(self,phase='environment-monitoring'):
  return {'phase':phase,'game_day':c.day(),'instance':'dot-safe-test','tasks':[{'entry':'EnvironmentMonitoringMain','selected_task_id':'test'}]}
 def test_cargo_gate_before_api(self):
  with self.assertRaises(RuntimeError):r.execute(self.plan('delivery-jobs'),lambda *a:self.fail('API called'))
 def test_stop_before_api(self):
  (self.root/'STOP').write_text('stop')
  with self.assertRaises(RuntimeError):r.execute(self.plan(),lambda *a:self.fail('API called'))
 def test_daily_success_does_not_block_regional(self):
  (self.root/'state'/f'endfield-{c.day()}.success.json').write_text('{}');self.assertFalse(r.attempt_guard('environment-monitoring').exists())
 def test_stage_independent_but_replay_blocked(self):
  r.attempt_guard('environment-monitoring').write_text('{}')
  with self.assertRaises(RuntimeError):r.attempt_guard('environment-monitoring')

 def run_fake(self,fail=False,errors='',running=False):
  calls=[];submitted=False
  def api(path,body=None,**kw):
   nonlocal submitted
   calls.append(path)
   if path=='/maa/initialized':return {'initialized':True,'version':c.FRAMEWORK}
   if path.endswith('/tasks/start'):
    submitted=True
    if fail:raise TimeoutError('ambiguous')
    return {'taskIds':[1]}
   if path.endswith('/tasks/stop'):return {}
   if path=='/maa/state':
    s={'is_running':running,'connected':True,'resource_loaded':True}
    if submitted:s['task_run_state']={'overall_status':'Succeeded','statuses':{'test':'succeeded'},'pending_task_ids':[1],'mappings':{'1':'test'}}
    return {'instances':{'dot-safe-test':s}}
   raise AssertionError(path)
  def shot(i,p,a,required=False):
   Path(p).write_bytes(b'png');return {'path':str(p),'width':1280,'height':720}
  with patch.object(r,'regional_versions',return_value={'agent':[],'controller':[{}],'resource':[{}]}),patch.object(r,'capture',side_effect=shot),patch.object(r,'log_position',return_value=0),patch.object(r,'collect_log',return_value=errors),patch.object(r.time,'sleep'):
   result,code=r.execute(self.plan(),api)
  return result,code,calls
 def test_mock_success_still_pending_visual(self):
  out,code,calls=self.run_fake();self.assertEqual(code,0);self.assertEqual(out['status'],'awaiting_visual_verification');self.assertFalse(out['verified']);self.assertFalse(out['daily_reward_verified']);self.assertFalse(list((self.root/'state').glob('*.success.json')))
 def test_ambiguous_submission_stops_own_and_blocks(self):
  out,code,calls=self.run_fake(fail=True);self.assertEqual(code,2);self.assertIn('/maa/instances/dot-safe-test/tasks/stop',calls)
  with self.assertRaises(RuntimeError):r.attempt_guard('environment-monitoring')
 def test_official_error_not_success(self):
  out,code,calls=self.run_fake(errors='{"stop_task":true}');self.assertEqual(code,2);self.assertFalse(out['automation_succeeded'])
 def test_busy_prevents_submission(self):
  with self.assertRaises(RuntimeError):self.run_fake(running=True)
 def test_stale_plan_rejected(self):
  p=self.plan();p['game_day']='2000-01-01'
  with self.assertRaises(RuntimeError):r.execute(p,lambda *a:self.fail('API called'))
 def test_delivery_missing_region_blocked_before_api(self):
  with self.assertRaises(RuntimeError):r.execute(self.plan('delivery-jobs'),lambda *a:self.fail('API'),cargo_reviewed=True)
if __name__=='__main__':unittest.main()
