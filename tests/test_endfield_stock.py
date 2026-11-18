import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'scripts'))
import endfield_common as c
import endfield_stock as r
class StockTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'state').mkdir();self.ps=[patch.object(c,'ROOT',self.root),patch.object(r,'ROOT',self.root)]
  for p in self.ps:p.start()
 def tearDown(self):
  for p in reversed(self.ps):p.stop()
  self.tmp.cleanup()
 def plan(self):return {'phase':'sell','game_day':c.day(),'instance':'dot-safe-test','tasks':[{'entry':'AutoSellMain','selected_task_id':'test'}]}
 def test_stop(self):
  (self.root/'STOP').write_text('stop')
  with self.assertRaises(RuntimeError):r.execute(self.plan(),lambda *a:self.fail('API'))
 def test_independent_ledger_preserves_old_success(self):
  old=self.root/'state'/f'endfield-{c.day()}.success.json';old.write_text('old')
  r.attempt_guard('sell').write_text('{}')
  with self.assertRaises(RuntimeError):r.attempt_guard('sell')
  self.assertFalse(r.attempt_guard('buy').exists());self.assertEqual(old.read_text(),'old')
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
  with patch.object(r,'stock_versions',return_value={'agent':[],'controller':[{}],'resource':[{}]}),patch.object(r,'capture',side_effect=shot),patch.object(r,'log_position',return_value=0),patch.object(r,'collect_log',return_value=errors),patch.object(r.time,'sleep'):
   result,code=r.execute(self.plan(),api)
  return result,code,calls
 def test_mock_success_still_pending_visual(self):
  out,code,calls=self.run_fake();self.assertEqual(code,0);self.assertEqual(out['status'],'awaiting_visual_verification');self.assertFalse(out['verified']);self.assertFalse(out['daily_reward_verified']);self.assertFalse(list((self.root/'state').glob('*.success.json')))
 def test_ambiguous_submission_stops_own_and_blocks(self):
  out,code,calls=self.run_fake(fail=True);self.assertEqual(code,2);self.assertIn('/maa/instances/dot-safe-test/tasks/stop',calls)
  with self.assertRaises(RuntimeError):r.attempt_guard('sell')
 def test_official_error_not_success(self):
  out,code,calls=self.run_fake(errors='{"stop_task":true}');self.assertEqual(code,2);self.assertFalse(out['automation_succeeded'])
 def test_busy_prevents_submission(self):
  with self.assertRaises(RuntimeError):self.run_fake(running=True)
 def test_stale_plan_rejected(self):
  p=self.plan();p['game_day']='2000-01-01'
  with self.assertRaises(RuntimeError):r.execute(p,lambda *a:self.fail('API called'))
 def fixture_recovery(self):
  run=self.root/'runs'/'old';run.mkdir(parents=True)
  error={'level':'error','component':'autosell','step':'execute_sell','message':'parse params','error':r.PRETRADE_ERROR}
  rows=[{'component':'autosell','step':'scan_item','region':'ValleyIV'},error]
  (run/'go-service.log').write_text('\n'.join(json.dumps(v) for v in rows),encoding='utf8')
  receipt={'game':'endfield','phase':'sell','game_day':c.day(),'instance':'dot-safe-test','maa_version':c.VERSION,'framework_version':c.FRAMEWORK,'status':'failed','automation_succeeded':False,'state':{'is_running':False,'task_run_state':{'overall_status':'Failed','statuses':{'dot-stock-sell':'failed'}}},'safety_errors':[error]}
  for name in ('before','after'):
   f=run/(name+'.png');f.write_bytes(b'png');receipt[name]={'path':str(f),'sha256':c.digest(f)}
  (run/'request.json').write_text(json.dumps({'tasks':[{'entry':'AutoSellMain'}]}))
  path=run/'summary.json';path.write_text(json.dumps(receipt));(self.root/'state'/f'endfield-stock-{c.day()}-sell.attempt.json').write_text(json.dumps({'run_dir':str(run)}));return path
 def test_recovery_once_keeps_original(self):
  path=self.fixture_recovery();old=path.read_bytes();ledger,meta=r.recovery_guard(path,self.plan());ledger.write_text('{}')
  with self.assertRaises(RuntimeError):r.recovery_guard(path,self.plan())
  self.assertEqual(old,path.read_bytes())
 def test_recovery_rejects_any_other_sell_log(self):
  path=self.fixture_recovery();log=path.parent/'go-service.log';log.write_text(log.read_text()+'\n'+json.dumps({'component':'autosell','step':'execute_sell','message':'success'}))
  with self.assertRaises(RuntimeError):r.recovery_guard(path,self.plan())
 def test_recovery_rejects_other_error(self):
  path=self.fixture_recovery();v=json.loads(path.read_text());v['safety_errors'][0]['error']='other';path.write_text(json.dumps(v))
  with self.assertRaises(RuntimeError):r.recovery_guard(path,self.plan())
 def test_recovery_rejects_tampered_screenshot(self):
  path=self.fixture_recovery();(path.parent/'after.png').write_bytes(b'changed')
  with self.assertRaises(RuntimeError):r.recovery_guard(path,self.plan())
class StockPlanTests(unittest.TestCase):
 def test_only_approved_tasks(self):
  for phase,entry in [('sell','AutoSellMain'),('buy','AutoStockpileMain')]:
   plan=r.make_plan(phase);self.assertEqual(len(plan['tasks']),1);self.assertEqual(plan['tasks'][0]['entry'],entry)
   patch=json.loads(plan['tasks'][0]['pipeline_override'])[-1];self.assertFalse(patch['AutoStockpileAttach']['attach']['allow_data_upload']);self.assertFalse(patch['AutoStockpileGetUid']['enabled'])
 def test_prices_are_native_integers_overflow_is_expression(self):
  p=r.make_plan('sell');patches=json.loads(p['tasks'][0]['pipeline_override']);merged={}
  for v in patches:merged.update(v)
  for node in ('AutoSellExecuteValleyIVMain','AutoSellExecuteWulingMain'):
   params=merged[node]['custom_action_param']
   self.assertEqual({k:type(v) for k,v in params.items() if k.endswith('_price')},{'large_price':int,'massive_price':int,'moderate_price':int})
  self.assertIsInstance(merged['AutoSellTicketValleyIVOverflow']['custom_recognition_param']['expression'],str)
 def test_existing_price_thresholds(self):
  p=r.make_plan('sell');v=p['selected_options']['AutoSellPricePerCategory'];self.assertEqual(set(v.values()),{'4600','5000','5300'})
 def test_buy_strategy_not_stable_reserve(self):
  p=r.make_plan('buy');self.assertEqual(p['selected_options']['AutoStockpileMinBuy'],'No');self.assertEqual(p['selected_options']['AutoStockpileAllowDataUpload'],'No');self.assertNotIn('240000',json.dumps(p))
if __name__=='__main__':unittest.main()
