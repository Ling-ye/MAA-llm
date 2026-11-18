import base64,datetime as dt,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'scripts'))
import endfield_common as c
import endfield_safe as s
import endfield_close as close
import endfield_bootstrap as boot
PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII=')
class EndfieldHardeningTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'state').mkdir();(self.root/'runs').mkdir();(self.root/'evidence').mkdir()
  self.patches=[patch.object(m,'ROOT',self.root) for m in (c,s,close,boot)]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.temp.cleanup()
 def test_timezone_reset(self):
  self.assertEqual(c.day(dt.datetime(2026,11,16,19,59,tzinfo=dt.timezone.utc)),'2026-11-16')
  self.assertEqual(c.day(dt.datetime(2026,11,16,20,0,tzinfo=dt.timezone.utc)),'2026-11-17')
 def test_instance_rejects_path_and_shell(self):
  for name in ['x','dot-safe-../../x','dot-safe-x;echo','http://x']:
   with self.assertRaises(ValueError):c.instance_id(name)
 def test_daily_rejects_any_prior_phase(self):
  (self.root/'state'/f'endfield-{c.day()}-rewards.attempt.json').write_text('{}')
  with self.assertRaises(RuntimeError):s.attempt_guard('daily',root=self.root)
 def test_daily_rejects_ambiguous_rejected_attempt(self):
  (self.root/'state'/f'endfield-{c.day()}-inventory.attempt.json.rejected').write_text('{}')
  with self.assertRaises(RuntimeError):s.attempt_guard('daily',root=self.root)
 def test_success_blocks_all_phases(self):
  (self.root/'state'/f'endfield-{c.day()}.success.json').write_text('{}')
  for phase in s.PHASES:
   with self.assertRaises(RuntimeError):s.attempt_guard(phase,root=self.root)
 def test_daily_marker_blocks_inventory(self):
  (self.root/'state'/f'endfield-{c.day()}-daily.attempt.json').write_text('{}')
  with self.assertRaises(RuntimeError):s.attempt_guard('inventory',root=self.root)
 def test_stop_blocks_before_any_api(self):
  (self.root/'STOP').write_text('stop');calls=[]
  with self.assertRaises(RuntimeError):s.execute({'phase':'daily','instance':'dot-safe-test'},lambda *a,**k:calls.append(a))
  self.assertEqual(calls,[])
 def test_callback_success_is_not_enough(self):
  task={'selected_task_id':'safe'};state={'is_running':False,'task_run_state':{'overall_status':'Succeeded','statuses':{}}}
  self.assertFalse(s.state_success(state,[task]))
 def test_stale_mapping_rejected(self):
  task={'selected_task_id':'safe'};state={'is_running':False,'task_run_state':{'overall_status':'Succeeded','statuses':{'safe':'succeeded'},'pending_task_ids':[1],'mappings':{'1':'safe'}}}
  self.assertFalse(s.state_success(state,[task],{'taskIds':[2]}))
  self.assertTrue(s.state_success(state,[task],{'taskIds':[1]}))
 def test_official_stop_overrides_success(self):
  self.assertEqual(len(c.safety_errors('{"level":"debug","stop_task":true}\n{"level":"error","message":"resolution check failed"}')),2)
 def receipt(self):
  path=self.root/'runs'/'test';path.mkdir();p=path/'summary.json';e=self.root/'evidence'/'proof.png';e.write_bytes(PNG)
  r={'game':'endfield','game_day':c.day(),'maa_version':c.VERSION,'framework_version':c.FRAMEWORK,'instance':'dot-safe-test','phase':'daily','activity':100,'daily_reward_verified':True,'automation_succeeded':True,'verification_evidence':{'path':str(e),'sha256':c.digest(e)}}
  c.atomic_json(p,r);return p,r,e
 def test_close_receipt_old_day_rejected(self):
  p,r,e=self.receipt();r['game_day']='2000-01-01';c.atomic_json(p,r)
  with self.assertRaises(RuntimeError):c.validate_receipt(p)
 def test_close_receipt_changed_image_rejected(self):
  p,r,e=self.receipt();e.write_bytes(PNG+b'changed')
  with self.assertRaises(RuntimeError):c.validate_receipt(p)
 def test_close_receipt_bad_version_rejected(self):
  p,r,e=self.receipt();r['maa_version']='v99';c.atomic_json(p,r)
  with self.assertRaises(RuntimeError):c.validate_receipt(p)
 def test_close_current_receipt_accepts(self):
  p,r,e=self.receipt();self.assertTrue(c.validate_receipt(p)['daily_reward_verified'])
 def test_verification_writes_success_without_api(self):
  p,r,e=self.receipt();r['daily_reward_verified']=False;c.atomic_json(p,r)
  with patch.object(s,'local_versions',return_value={}):s.record_verification(p,e,100)
  self.assertTrue((self.root/'state'/f'endfield-{c.day()}.success.json').exists())
 def test_running_blocks_close(self):
  p,r,e=self.receipt()
  def api(path,*args,**kwargs):
   if path=='/maa/initialized':return {'initialized':True,'version':c.FRAMEWORK}
   if path=='/maa/state':return {'instances':{'dot-safe-test':{'is_running':True}}}
   self.fail('No mutation allowed')
  with patch.object(close,'local_versions',return_value={}):
   with self.assertRaises(RuntimeError):close.close(p,api)
 def test_bootstrap_rejects_busy_before_mutation(self):
  calls=[]
  def api(path,*args,**kwargs):
   calls.append(path)
   if path=='/maa/initialized':return {'initialized':True,'version':c.FRAMEWORK}
   if path=='/maa/state':return {'instances':{'other':{'is_running':True}}}
   self.fail('No other endpoint permitted')
  with patch.object(boot,'local_versions',return_value={}):
   with self.assertRaises(RuntimeError):boot.prepare('dot-safe-test',123,api,lambda h:{'hwnd':h})
  self.assertEqual(calls,['/maa/initialized','/maa/state'])
 def fake_execute(self,error_log='',transport_error=False):
  plan={'phase':'rewards','instance':'dot-safe-test','tasks':[{'entry':'DailyRewardStart','selected_task_id':'safe','pipeline_override':'{}'}]};started=False;calls=[]
  def api(path,body=None,**kwargs):
   nonlocal started
   calls.append(path)
   if path=='/maa/initialized':return {'initialized':True,'version':c.FRAMEWORK}
   if path.endswith('/tasks/start'):
    started=True
    if transport_error:raise TimeoutError('ambiguous submission')
    return {'taskIds':[1]}
   if path.endswith('/tasks/stop'):return {'ok':True}
   if path=='/maa/state':
    state={'connected':True,'resource_loaded':True,'is_running':False}
    if started:state['task_run_state']={'overall_status':'Succeeded','statuses':{'safe':'succeeded'},'pending_task_ids':[1],'mappings':{'1':'safe'}}
    return {'instances':{'dot-safe-test':state}}
   self.fail('Unexpected real endpoint '+path)
  def shot(instance,path,api,required=False):
   Path(path).write_bytes(PNG);return {'path':str(path),'sha256':c.digest(path),'width':1280,'height':720}
  manifest={'agent':[],'controller':[{}],'resource':[{}]}
  with patch.object(s,'local_versions',return_value=manifest),patch.object(s,'capture',side_effect=shot),patch.object(s,'log_position',return_value=0),patch.object(s,'collect_log',return_value=error_log),patch.object(s.time,'sleep',return_value=None):
   result,code=s.execute(plan,api)
  return result,code,calls
 def test_execution_success_never_claims_daily_verified(self):
  result,code,calls=self.fake_execute();self.assertEqual(code,0);self.assertTrue(result['automation_succeeded']);self.assertFalse(result['daily_reward_verified']);self.assertEqual(result['status'],'awaiting_visual_verification')
 def test_official_error_forces_nonzero_exit(self):
  result,code,calls=self.fake_execute('{"level":"error","stop_task":true}')
  self.assertEqual(code,2);self.assertFalse(result['automation_succeeded'])
 def test_ambiguous_submit_stops_and_blocks_replay(self):
  result,code,calls=self.fake_execute(transport_error=True)
  self.assertEqual(code,2);self.assertIn('/maa/instances/dot-safe-test/tasks/stop',calls)
  with self.assertRaises(RuntimeError):s.attempt_guard('rewards',root=self.root)

 def test_reward_only_cannot_mark_full_daily_success(self):
  p,r,e=self.receipt();r['phase']='rewards';c.atomic_json(p,r)
  with patch.object(s,'local_versions',return_value={}):
   with self.assertRaisesRegex(RuntimeError,'combined daily'):s.record_verification(p,e,100)
  self.assertFalse((self.root/'state'/f'endfield-{c.day()}.success.json').exists())

if __name__=='__main__':unittest.main()
