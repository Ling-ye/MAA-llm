import ast,copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'scripts'))
import daily_audit as a

class AuditTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.day='2026-11-17'
  (self.root/'evidence').mkdir();(self.root/'evidence'/'proof.png').write_bytes(b'\x89PNG\r\n\x1a\nfixture')
  self.state={'day':self.day,'games':{}}
 def put(self,name,game,**kw):
  p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True)
  r=dict(game=game,day=self.day,verified=True,daily_reward_verified=True,game_closed=True,maa_closed=True,emulator_closed=True,evidence=['proof.png'],**kw)
  p.write_text(json.dumps(r));return str(p)
 def full(self):
  ark={'phase':'closed'};self.state['games']['arknights']=ark
  ark['receipt']=self.put('runs/base/summary.json','arknights',verified_at='yes',tasks=[{'type':'Fight','status':'maa_completed'}])
  for key,types in [('operations_receipt',['Recruit','Infrast','Mall','Award']),('acceleration_receipt',['Recruit','Infrast','Award'])]:
   ark[key]=self.put('runs/'+key+'/summary.json','arknights',tasks=[{'type':t,'status':'maa_completed'} for t in types])
  gf={'phase':'closed','receipt':self.put('runs/gf/summary.json','gf2',daily_activity=110,daily_goal=80)};self.state['games']['gf2']=gf
  self.put('state/gf2-'+self.day+'.supplemental.attempt.json','gf2',cooking_completed=True,tea_completed=True,watering_completed=True,partial_verified=True)
  gf['breakthrough_receipt']=self.put('runs/gf-breakthrough/summary.json','gf2',highest_sweepable_breakthrough_verified=True,natural_or_levelup_stamina_only=True,tasks=[{'entry':'AutoSweepBattleSupplyOperationPrepare','status':'maa_completed'}])
  end={'phase':'closed','receipt':self.put('runs/end/summary.json','endfield',activity=100,phase='daily'),'regional_supplement':{}};self.state['games']['endfield']=end
  for name,phase in [('environment_monitoring','environment-monitoring'),('stock_sell','sell'),('stock_buy','buy')]:
   end['regional_supplement'][name]={'receipt':self.put('runs/'+name+'/summary.json','endfield',phase=phase,automation_succeeded=True)}
  end['regional_supplement']['cleanup']=self.put('runs/cleanup.json','endfield')
 def result(self):return a.audit(self.day,self.root,self.state)
 def alter(self,key,value):
  p=Path(self.state['games']['arknights']['operations_receipt']);r=json.loads(p.read_text());r[key]=value;p.write_text(json.dumps(r))
 def test_closed_not_complete(self):
  self.state['games']={g:{'phase':'closed'} for g in ('arknights','gf2','endfield')}
  self.assertFalse(self.result()['all_required_stages_recorded_verified'])
 def test_complete_bound_records(self):
  self.full();self.assertTrue(self.result()['all_required_stages_recorded_verified'])
 def test_wrong_day_game_and_path(self):
  self.full()
  for key,value in [('day','2026-11-16'),('game','gf2')]:
   self.full();self.alter(key,value);self.assertIn('arknights.operations',self.result()['blocked_stages'])
  self.state['games']['arknights']['operations_receipt']=str(self.root.parent/'outside.json')
  self.assertIn('arknights.operations',self.result()['blocked_stages'])
 def test_running_failure_and_unverified(self):
  for key,value in [('status','running'),('status','failed'),('verified',False),('daily_reward_verified',False)]:
   self.full();self.alter(key,value);self.assertIn('arknights.operations',self.result()['blocked_stages'])
 def test_missing_and_hash_evidence(self):
  for ev in [[],[{'path':'proof.png','sha256':'bad'}],['missing.png']]:
   self.full();self.alter('evidence',ev);self.assertIn('arknights.operations',self.result()['blocked_stages'])
 def test_no_latest_guess(self):
  self.full();del self.state['games']['arknights']['operations_receipt']
  self.assertIn('arknights.operations',self.result()['blocked_stages'])
 def test_ledger_conflict(self):
  self.full();p=self.root/'state'/('arknights-'+self.day+'.operations.attempt.json');p.write_text(json.dumps({'run_dir':'runs/different'}))
  self.assertIn('arknights.operations',self.result()['blocked_stages'])
 def test_delivery_is_not_stock(self):
  self.full();p=Path(self.state['games']['endfield']['regional_supplement']['stock_sell']['receipt']);r=json.loads(p.read_text());r['phase']='delivery-jobs';p.write_text(json.dumps(r))
  self.assertIn('endfield.stock_sell',self.result()['blocked_stages'])
 def test_v2_requires_bound_proof(self):
  self.full();self.alter('plan_version','approved-ark-operations-v2');self.alter('schema',2)
  self.assertIn('arknights.operations',self.result()['blocked_stages'])
 def test_v2_proof_and_worker_tamper(self):
  import ark_v2_evidence as proof
  self.full();p=Path(self.state['games']['arknights']['operations_receipt']);folder=p.parent
  cfg=folder/'config.json';cfg.write_text(json.dumps({'supplement_policy':'approved-ark-operations-v2','expected_version':'test'}))
  r=json.loads(p.read_text());r.update(schema=2,plan_version='approved-ark-operations-v2',run_dir=str(folder),config_sha256=proof.sha(cfg))
  for i,item in enumerate(r['tasks']):
   d=folder/(str(i)+'-'+item['type']);d.mkdir();task={'type':item['type'],'params':{}}
   (d/'task.json').write_text(json.dumps(task));(d/'result.json').write_text(json.dumps({'ok':True,'version':'test','task':item['type']}))
   detail={'taskchain':item['type'],'taskid':i+1,'uuid':'test'}
   events=[{'msg':10001,'details':detail},{'msg':10002,'details':detail},{'msg':3,'details':{'finished_tasks':[i+1],'uuid':'test'}}]
   (d/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
   item.update(status='complete',task_sha256=proof.sha(d/'task.json'),evidence=proof.validate(d,cfg,task,'test'))
   (d/'worker-state.json').write_text(json.dumps({'status':'complete','evidence':item['evidence']}))
  p.write_text(json.dumps(r));self.assertTrue(self.result()['all_required_stages_recorded_verified'])
  (folder/'0-Recruit'/'worker-state.json').write_text('{"status":"running"}')
  self.assertIn('arknights.operations',self.result()['blocked_stages'])
 def test_audit_does_not_mutate_or_launch(self):
  self.full();before={str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
  with patch('subprocess.Popen',side_effect=AssertionError('launch forbidden')),patch('socket.socket',side_effect=AssertionError('network forbidden')):
   self.result()
  self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
  tree=ast.parse(Path(a.__file__).read_text())
  forbidden={'runner','ark_operations','ark_operations_v2','subprocess','ctypes','socket','os'}
  for node in ast.walk(tree):
   if isinstance(node,ast.Import):self.assertFalse(forbidden.intersection(n.name for n in node.names))
   if isinstance(node,ast.ImportFrom):self.assertNotIn(node.module,forbidden)


 def test_breakthrough_missing_blocks_full_coverage(self):
  self.full();del self.state['games']['gf2']['breakthrough_receipt']
  self.assertIn('gf2.breakthrough',self.result()['blocked_stages'])
 def test_reward_only_is_not_full_endfield_daily(self):
  self.full();p=Path(self.state['games']['endfield']['receipt']);r=json.loads(p.read_text());r['phase']='rewards';p.write_text(json.dumps(r))
  self.assertIn('endfield.daily',self.result()['blocked_stages'])

if __name__=='__main__':unittest.main()
