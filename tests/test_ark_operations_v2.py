import json,sys,tempfile,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'scripts'))
import ark_operations_v2 as a
class OpsTests(unittest.TestCase):
 def setUp(self):
  self.c=a.base.read_json(Path(__file__).resolve().parents[1]/'config.example'/'ark-operations-v2.json');self.c['ready']=True;self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'state').mkdir();self.cfg=self.root/'cfg.json';self.cfg.write_text(json.dumps(self.c));self.png=self.root/'home.png';self.png.write_bytes(b'\x89PNG\r\n\x1a\n');self.p=patch.object(a,'ROOT',self.root);self.p.start()
 def tearDown(self):self.p.stop();self.tmp.cleanup()
 def test_safe_tasks(self):
  plan=a.make_plan(self.c);self.assertEqual([t['type'] for t in plan],['Recruit','Infrast','Mall','Award']);r,i,m,award=[t['params'] for t in plan]
  self.assertEqual(r['times'],4);self.assertTrue(r['refresh']);self.assertTrue(r['expedite']);self.assertEqual(r['recruitment_time'],{'3':540,'4':540});self.assertEqual(len(r['preserve_tags']),3)
  self.assertEqual(i['mode'],0);self.assertEqual(i['drones'],'Money');self.assertFalse(i['replenish']);self.assertFalse(i['reception_send_clue']);self.assertFalse(i['reception_clue_exchange']);self.assertFalse(set(i['facility'])&{'Training','Processing','AssistantChange'});self.assertFalse(m['force_shopping_if_credit_full']);self.assertEqual(len(m['blacklist']),3)
 def test_award_only_claims_daily_no_battle(self):
  plan=a.make_plan(self.c);award=plan[-1];self.assertEqual(award['type'],'Award');self.assertTrue(award['params']['award']);self.assertFalse(any(v for k,v in award['params'].items() if k!='award'));self.assertNotIn('Fight',[t['type'] for t in plan])
 def test_recruit_selection_vs_confirmation(self):
  r=a.make_plan(self.c)[0]['params'];self.assertEqual(r['select'],[4]);self.assertEqual(r['confirm'],[3,4]);self.assertEqual(r['recruitment_time']['3'],540);self.assertFalse(r['force_refresh'])
 def test_plan_does_not_preflight(self):
  with patch.object(a.base,'preflight',side_effect=AssertionError('No game')):out,code=a.run(self.cfg)
  self.assertEqual(code,0);self.assertEqual(out['mode'],'plan_only')
 def test_home_gate(self):
  with self.assertRaises(RuntimeError):a.run(self.cfg,True)
 def test_stop_before_preflight(self):
  (self.root/'STOP').write_text('stop')
  with patch.object(a.base,'preflight',side_effect=AssertionError('No game')):
   with self.assertRaises(RuntimeError):a.run(self.cfg,True,True,home_evidence=self.png)
 def test_replay_rejected(self):
  a.guard().write_text('{}')
  with self.assertRaises(RuntimeError):a.guard()
 def test_accelerated_attempt_blocks_operations(self):
  (self.root/'state'/f'arknights-{a.base.game_day()}.accelerated-recovery-predll.attempt.json').write_text('{}')
  with self.assertRaises(RuntimeError):a.guard()
 def test_real_worker_plan_before_dll(self):
  bad=self.root/'bad.json';bad.write_text('{}')
  script=Path(__file__).resolve().parents[1]/'scripts'/'ark_operations_v2.py'
  done=subprocess.run([sys.executable,str(script),'--worker','--config',str(self.cfg),'--taskfile',str(bad),'--directory',str(self.root)],capture_output=True)
  self.assertEqual(done.returncode,2);self.assertEqual(json.loads(done.stdout.decode())['error'],'Worker readiness or task allowlist rejected')
 def test_bad_policy_rejected(self):
  self.c['supplement_policy']='other'
  with self.assertRaises(ValueError):a.make_plan(self.c)
 def fake(self,failed=False):
  old=self.root/'state'/f'arknights-{a.base.game_day()}.json';old.write_text('old primary')
  def shot(c,p):Path(p).write_bytes(b'png')
  def worker(argv,log,timeout,on_pid):
   on_pid(12345);folder=Path(argv[argv.index('--directory')+1]);task=a.base.read_json(folder/'task.json');cfg=argv[argv.index('--config')+1]
   (folder/'result.json').write_text(json.dumps({'ok':not failed,'version':self.c['expected_version'],'task':task['type']}))
   events=[{'msg':msg,'details':dict(taskchain=task['type'],taskid=1,uuid='test',**({'finished_tasks':[1]} if msg==3 else {}))} for msg in [10001,10002,3]]
   (folder/'events.jsonl').write_text('\n'.join(json.dumps(x) for x in events))
   if not failed:a.base.atomic_json(folder/'worker-state.json',{'status':'complete','evidence':a.evidence.validate(folder,cfg,task,self.c['expected_version'])})
   return 2 if failed else 0
  with patch.object(a.base,'preflight'),patch.object(a.base,'screenshot',side_effect=shot),patch.object(a,'execute_child',side_effect=worker):out,code=a.run(self.cfg,True,True,home_evidence=self.png)
  self.assertEqual(old.read_text(),'old primary');return out,code
 def test_mock_success_preserves_primary_unverified(self):
  out,code=self.fake();self.assertEqual(code,0);self.assertEqual(out['status'],'automation_completed_unverified');self.assertFalse(out['daily_reward_verified'])
 def test_failure_stops_sequence_and_retains_attempt(self):
  out,code=self.fake(True);self.assertEqual(code,2);self.assertEqual(out['tasks'][0]['status'],'unknown');self.assertTrue(all(t['status']=='planned' for t in out['tasks'][1:]))
  with self.assertRaises(RuntimeError):a.guard()
 def test_missing_fresh_evidence_blocks_execute(self):
  with self.assertRaisesRegex(RuntimeError,'evidence'):a.run(self.cfg,True,True)
 def test_stale_home_proof(self):
  import os,time
  os.utime(self.png,(time.time()-301,time.time()-301))
  with self.assertRaises(RuntimeError):a.home_proof(self.png)
 def test_unknown_never_resumes(self):
  out,_=self.fake(True)
  with self.assertRaises(RuntimeError):a.resume_check(Path(out['run_dir'])/'summary.json')
 def test_complete_never_replays(self):
  out,_=self.fake()
  with self.assertRaisesRegex(RuntimeError,'Nothing'):a.resume_check(Path(out['run_dir'])/'summary.json')
 def test_resume_planned_suffix_after_verified_prefix(self):
  out,_=self.fake();folder=Path(out['run_dir']);doc=a.base.read_json(folder/'summary.json')
  # Synthetic interruption before later stages were submitted; test data only.
  for i,item in enumerate(doc['tasks'][1:],1):
   item['status']='planned';item.pop('evidence',None)
   for p in (folder/(str(i)+'-'+item['type'])).iterdir():
    if p.name!='task.json':p.unlink()
  a.base.atomic_json(folder/'summary.json',doc)
  self.assertEqual(a.resume_check(folder/'summary.json')[3],1)
  with (folder/'0-Recruit/events.jsonl').open('a') as f:f.write('\n{}')
  with self.assertRaises(ValueError):a.resume_check(folder/'summary.json')
 def test_status_readonly(self):
  with patch.object(a.base,'preflight',side_effect=AssertionError('No game')):self.assertEqual(a.status()['status'],'not_attempted')
 def test_timeout_only_exact_child(self):
  ids=[]
  with (self.root/'timeout.log').open('wb') as log:
   with self.assertRaisesRegex(RuntimeError,'timeout'):a.execute_child([sys.executable,'-c','import time;time.sleep(10)'],log,.01,ids.append)
  self.assertEqual(len(ids),1);self.assertIsInstance(ids[0],int)
 def test_stop_only_exact_child(self):
  (self.root/'STOP').write_text('test')
  ids=[]
  with (self.root/'stop.log').open('wb') as log:
   with self.assertRaisesRegex(RuntimeError,'STOP'):a.execute_child([sys.executable,'-c','pass'],log,10,ids.append)
  self.assertEqual(ids,[]);self.assertTrue((self.root/'STOP').exists())
 def test_false_ok_without_task_events_rejected(self):
  out,_=self.fake();folder=Path(out['run_dir']);stage=folder/'0-Recruit';(stage/'events.jsonl').write_text('')
  with self.assertRaises(ValueError):a.evidence.validate(stage,folder/'config.json',a.make_plan(self.c)[0],self.c['expected_version'])
 def test_task_chain_error_rejected(self):
  out,_=self.fake();folder=Path(out['run_dir']);stage=folder/'0-Recruit'
  with (stage/'events.jsonl').open('a') as f:f.write('\n'+json.dumps({'msg':10000,'details':{}}))
  with self.assertRaises(ValueError):a.evidence.validate(stage,folder/'config.json',a.make_plan(self.c)[0],self.c['expected_version'])
 def test_status_rejects_outside_and_wrong_day(self):
  out,_=self.fake();folder=Path(out['run_dir']);outside=self.root/'summary.json';outside.write_text(json.dumps(out))
  with self.assertRaises(RuntimeError):a.status(outside)
  out['day']='1999-01-01';a.base.atomic_json(folder/'summary.json',out)
  with self.assertRaises(RuntimeError):a.status(folder/'summary.json')
 def test_status_rejects_unbound_run(self):
  out,_=self.fake();other=self.root/'runs'/'other';other.mkdir();a.base.atomic_json(other/'summary.json',out)
  with self.assertRaises(RuntimeError):a.status(other/'summary.json')
 def test_close_requires_visual_and_full_bound_evidence(self):
  out,_=self.fake();path=Path(out['run_dir'])/'summary.json'
  with self.assertRaises(RuntimeError):a.resume_check(path,require_complete=True)
  out['daily_reward_verified']=True;a.base.atomic_json(path,out)
  self.assertEqual(a.resume_check(path,require_complete=True)[3],4)
  (path.parent/'3-Award/result.json').write_text('{"ok":true}')
  with self.assertRaises(ValueError):a.resume_check(path,require_complete=True)
 def test_close_rejects_planned_even_with_visual_true(self):
  out,_=self.fake();path=Path(out['run_dir'])/'summary.json';out['daily_reward_verified']=True;out['tasks'][-1]['status']='planned';a.base.atomic_json(path,out)
  with self.assertRaises(RuntimeError):a.resume_check(path,require_complete=True)
 def test_finish_guard_verifies_schema2_before_process_access(self):
  script=(Path(__file__).resolve().parents[1]/'scripts'/'finish-game.ps1').read_text(encoding='utf-8-sig')
  self.assertIn('--verify-complete --summary $Receipt',script);self.assertIn("$_.status -ne 'maa_completed'",script)
  self.assertLess(script.index('--verify-complete'),script.index('Get-CimInstance'))

 def test_resume_archives_old_error_and_allows_current_success(self):
  out,_=self.fake();folder=Path(out['run_dir']);path=folder/'summary.json';stage=folder/'3-Award'
  artifacts={p.name:p.read_bytes() for p in stage.iterdir() if p.name!='task.json'}
  for name in artifacts:(stage/name).unlink()
  out['tasks'][-1]['status']='planned';out['tasks'][-1].pop('evidence',None);out.update(status='paused',error='old screenshot failure')
  a.base.atomic_json(path,out)
  def worker(argv,log,timeout,on_pid):
   on_pid(123)
   for name,data in artifacts.items():(stage/name).write_bytes(data)
   return 0
  with patch.object(a.base,'preflight'),patch.object(a.base,'screenshot'),patch.object(a,'execute_child',side_effect=worker):
   resumed,code=a.run(self.cfg,True,True,resume=path,home_evidence=self.png)
  self.assertEqual(code,0);self.assertNotIn('error',resumed)
  previous=Path(resumed['recovery_history'][-1]['path'])
  self.assertEqual(a.base.read_json(previous)['error'],'old screenshot failure')
  self.assertEqual(a.evidence.sha(previous),resumed['recovery_history'][-1]['sha256'])

if __name__=='__main__':unittest.main()
