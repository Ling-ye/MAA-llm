"""MaaEnd isolated API adapter; plan-only unless --execute. No automatic verification."""
from __future__ import annotations
import argparse,json,sys,time,uuid
from pathlib import Path
from endfield_common import *
DISABLE=['DailyTaskUpgradeWeapon','DailyTaskCreation','DailyTaskAssemble','DailyTaskLevelUpOperator']
ENABLE=['DailyEmailRewardSub','DailyTaskRewardSub','DailyClaimDeliveryJobsRewardSub','DailyProtocolPassRewardSub','DailyEventRewardSub','DailyTaskActivityFullCheck']
PHASES=['rewards','safe-maintenance','inventory','daily']
def make_plan(phase='rewards',instance=None):
 if phase not in PHASES:raise ValueError('Unknown phase')
 override={**{n:{'enabled':False} for n in DISABLE},**{n:{'enabled':True} for n in ENABLE}}
 reward={'entry':'DailyRewardStart','pipeline_override':json.dumps(override),'selected_task_id':'dot-safe-daily-rewards','task_name':'DailyRewards'}
 plan={'instance':instance_id(instance),'game_day':day(),'phase':phase,'tasks':[]}
 if phase in ('safe-maintenance','daily'):
  from policy_integrity import read_policy
  visit=read_policy('endfield-visit-overrides.json')
  collect={n:{'enabled':False} for n in ['RecoveryEmotionMain','ReceptionRoomMain','MFGCabinMain','GrowthChamberMain']}
  collect.update({n:{'enabled':True} for n in ['DijiangRewardsFastCollectProduction','DijiangRewardsFastCollectClues']})
  plan['tasks'] += [{'entry':'VisitFriendsMain','pipeline_override':json.dumps(visit),'selected_task_id':'dot-safe-visits','task_name':'VisitFriends'},
   {'entry':'DijiangRewards','pipeline_override':json.dumps(collect),'selected_task_id':'dot-safe-fast-collect','task_name':'DijiangRewards'}]
 if phase in ('inventory','daily'):
  from endfield_inventory_plan import build
  combat,targets=build();plan['selected_options']=combat.pop('options');plan['targets']=targets;plan['tasks'].append(combat)
 plan['tasks'].append(reward)
 return plan

def attempt_guard(phase,current_day=None,root=None):
 root=root or ROOT
 current_day=current_day or day();state=root/'state'
 if (state/f'endfield-{current_day}.success.json').exists():raise RuntimeError('Already verified complete today')
 attempts=list(state.glob(f'endfield-{current_day}-*.attempt.json*'))
 # A combined daily must never replay any older phase; daily blocks all follow-up phases.
 if phase=='daily' and attempts:raise RuntimeError('Endfield phase already attempted today; manual recovery review required')
 if any(f'-{phase}.attempt.json' in p.name or '-daily.attempt.json' in p.name for p in attempts):raise RuntimeError('This phase or daily already attempted; refusing replay')
 return state/f'endfield-{current_day}-{phase}.attempt.json'

def state_success(state,tasks,submitted=None):
 run=state.get('task_run_state',{});statuses=run.get('statuses',{})
 if submitted is not None:
  ids=submitted.get('taskIds',[])
  if len(ids)!=len(tasks) or len(set(ids))!=len(ids) or any(type(i) is not int or i<=0 for i in ids):return False
  if set(run.get('pending_task_ids',[]))!=set(ids):return False
  if any(run.get('mappings',{}).get(str(i))!=t['selected_task_id'] for i,t in zip(ids,tasks)):return False
 return not state.get('is_running') and run.get('overall_status')=='Succeeded' and all(statuses.get(t['selected_task_id'])=='succeeded' for t in tasks)

def record_verification(receipt,evidence,activity):
 check_stop();local_versions();p=Path(receipt).resolve();p.relative_to(ROOT/'runs');r=read(p)
 if r.get('game')!='endfield' or r.get('game_day')!=day() or r.get('maa_version')!=VERSION or r.get('framework_version')!=FRAMEWORK:raise RuntimeError('Receipt game/day/version mismatch')
 if r.get('phase')!='daily':raise RuntimeError('Only the combined daily phase can certify full core completion')
 if activity!=100 or not r.get('automation_succeeded') or r.get('safety_errors'):raise RuntimeError('Only safely completed automation can be verified as daily100')
 e=Path(evidence).resolve();e.relative_to(ROOT)
 if not e.is_file() or not e.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):raise RuntimeError('PNG evidence required')
 r.update({'verified':True,'daily_reward_verified':True,'activity':100,'verification_evidence':{'path':str(e),'sha256':digest(e)},'verified_at':now()})
 atomic_json(p,r);atomic_json(ROOT/'state'/f'endfield-{day()}.success.json',{'receipt':str(p),'verified_at':now(),'instance':r['instance'],'verification_evidence':r['verification_evidence']})
 return r

def execute(plan,api=request):
 check_stop();manifest=local_versions();current_day=day();instance=plan['instance']
 with exclusive_lock(ROOT/'state'/'pipeline.lock'):
  check_stop();ledger=attempt_guard(plan['phase'],current_day);live_versions(api);states=idle_states(api)
  s=states.get(instance,{})
  if not(s.get('connected') and s.get('resource_loaded')):raise RuntimeError('Run bootstrap and verify login/home before executing')
  run=ROOT/'runs'/('endfield-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);run.mkdir(parents=True)
  status={'game':'endfield','game_day':current_day,'maa_version':VERSION,'framework_version':FRAMEWORK,'instance':instance,
   'phase':plan['phase'],'verified':False,'daily_reward_verified':False,'started':False,'submission_attempted':False,'status':'preflight','run_dir':str(run),'started_at':now()}
  def save():atomic_json(run/'summary.json',status)
  save();atomic_json(run/'request.json',plan)
  offset=log_position()
  try:
   status['before']=capture(instance,run/'before.png',api,required=True);save()
   if (status['before']['width'],status['before']['height'])!=(1280,720):raise RuntimeError('Expected verified 1280x720 small-window capture; do not auto-toggle display')
   check_stop()
   # Exclusive create before submitting: ambiguous transport errors must never auto-replay.
   with ledger.open('x',encoding='utf8') as f:json.dump({'phase':plan['phase'],'run_dir':str(run),'game_day':current_day,'at':now(),'status':'attempted'},f)
   status['submission_attempted']=True;status['status']='submitting';save()
   status['response']=api('/maa/instances/'+instance+'/tasks/start',task_body(plan['tasks'],manifest));status['started']=True;status['status']='running';save()
   deadline=time.monotonic()+(3600 if plan['phase']=='daily' else 2400 if plan['phase']=='inventory' else 900)
   while True:
    check_stop()
    if time.monotonic()>deadline:raise RuntimeError('Task timeout; no automatic retry')
    time.sleep(2);s=api('/maa/state')['instances'][instance];status['state']=s;save()
    if not s.get('is_running'):break
   status['after']=capture(instance,run/'after.png',api)
   log=collect_log(offset,run/'go-service.log');status['safety_errors']=safety_errors(log)
   status['automation_succeeded']=state_success(s,plan['tasks'],status['response']) and not status['safety_errors'] and 'error' not in status['after']
   status['status']='awaiting_visual_verification' if status['automation_succeeded'] else 'failed'
   status['finished_at']=now();save();atomic_json(ledger,{'phase':plan['phase'],'run_dir':str(run),'status':status['status'],'at':now()})
   return status,0 if status['automation_succeeded'] else 2
  except Exception as e:
   status['error']=str(e);status['status']='failed';status['automation_succeeded']=False
   if hasattr(e,'read'):
    try:status['http_error_body']=e.read().decode('utf8',errors='replace')
    except Exception:pass
   if status['submission_attempted']:
    try:api('/maa/instances/'+instance+'/tasks/stop',{})
    except Exception as stop_error:status['stop_error']=str(stop_error)
   status['after']=capture(instance,run/'failure.png',api);status['safety_errors']=safety_errors(collect_log(offset,run/'go-service.log'));save()
   if ledger.exists():atomic_json(ledger,{'phase':plan['phase'],'run_dir':str(run),'status':'failed','at':now()})
   return status,2

def main():
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--phase',choices=PHASES,default='rewards');p.add_argument('--instance')
 p.add_argument('--record-verification',type=Path);p.add_argument('--evidence',type=Path);p.add_argument('--activity',type=int)
 a=p.parse_args()
 try:
  if a.execute:require_execution('endfield')
  if a.record_verification:
   if a.execute or not a.evidence:raise ValueError('Verification is separate from execution and requires evidence')
   result=record_verification(a.record_verification,a.evidence,a.activity);code=0
  else:
   plan=make_plan(a.phase,a.instance)
   if not a.execute:result=plan;code=0
   else:result,code=execute(plan)
  print(json.dumps(result,ensure_ascii=False));return code
 except Exception as e:print(json.dumps({'status':'blocked','error':str(e)},ensure_ascii=False));return 2
if __name__=='__main__':raise SystemExit(main())
