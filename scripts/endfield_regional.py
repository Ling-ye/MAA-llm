"""Independent regional phases; plan-only by default. Never closes or verifies daily."""

import argparse,json,time,uuid

from endfield_common import *

from endfield_safe import state_success

PHASES=('environment-monitoring',)

TASK_HASHES={'EnvironmentMonitoring.json': '63d0883332bec66d9aa790460af614878185641dee39a8bea7a6dc53b0b5f36d'}



def regional_versions():

 manifest=local_versions()

 for name,sha in TASK_HASHES.items():

  if digest(APP/'tasks'/name)!=sha:raise RuntimeError('Regional task changed; review before use: '+name)

 return manifest



def make_plan(phase,instance=None,region=None):
 if phase not in PHASES or region is not None:raise ValueError('Only environment-monitoring is supported; DeliveryJobs is not stock redistribution')
 from policy_integrity import read_policy
 patches=read_policy('endfield-visit-overrides.json')[:3]
 return {'phase':phase,'region':None,'instance':instance_id(instance),'game_day':day(),'selected_options':{},'cargo_review_required':False,'tasks':[{'entry':'EnvironmentMonitoringMain','task_name':'EnvironmentMonitoring','selected_task_id':'dot-regional-'+phase,'pipeline_override':json.dumps(patches)}]}

def attempt_guard(phase,current_day=None,root=None,region=None):

 if phase not in PHASES:raise ValueError('Unknown phase')

 if phase=='delivery-jobs':

  if region not in ('valleyiv','wuling'):raise ValueError('Explicit delivery region required')

  phase=phase+'-'+region

 root=root or ROOT;current_day=current_day or day();state=root/'state'

 if list(state.glob(f'endfield-regional-{current_day}-{phase}.attempt.json*')):raise RuntimeError('Regional phase attempted; inspect evidence, never automatically replay')

 return state/f'endfield-regional-{current_day}-{phase}.attempt.json'



def execute(plan,api=request,cargo_reviewed=False):

 if plan['phase'] not in PHASES:raise RuntimeError('DeliveryJobs is excluded from this repository workflow')
 if plan['phase']=='delivery-jobs' and cargo_reviewed is not True:raise RuntimeError('Inspect actual cargo item and quantity first; --cargo-reviewed required')

 if plan['phase']=='delivery-jobs' and plan.get('region') not in ('valleyiv','wuling'):raise RuntimeError('Execute requires --region valleyiv or wuling after reviewing that region cargo')

 if plan.get('game_day')!=day():raise RuntimeError('Stale regional plan')

 check_stop();manifest=regional_versions();current_day=day();instance=plan['instance']

 with exclusive_lock(ROOT/'state'/'pipeline.lock'):

  check_stop();ledger=attempt_guard(plan['phase'],current_day,region=plan.get('region'));live_versions(api);states=idle_states(api)

  s=states.get(instance,{})

  if not(s.get('connected') and s.get('resource_loaded')):raise RuntimeError('Run bootstrap and verify login/home before executing')

  run=ROOT/'runs'/('endfield-regional-'+plan['phase']+'-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);run.mkdir(parents=True)

  status={'game':'endfield','game_day':current_day,'maa_version':VERSION,'framework_version':FRAMEWORK,'instance':instance,

   'region':plan.get('region'),'cargo_reviewed':cargo_reviewed,'phase':plan['phase'],'verified':False,'daily_reward_verified':False,'started':False,'submission_attempted':False,'status':'preflight','run_dir':str(run),'started_at':now()}

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

   deadline=time.monotonic()+1800

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

   try:status['after']=capture(instance,run/'failure.png',api)

   except Exception as evidence_error:status['after']={'error':str(evidence_error)}

   try:status['safety_errors']=safety_errors(collect_log(offset,run/'go-service.log'))

   except Exception as log_error:status['log_error']=str(log_error)

   save()

   if ledger.exists():atomic_json(ledger,{'phase':plan['phase'],'run_dir':str(run),'status':'failed','at':now()})

   return status,2



def main():

 p=argparse.ArgumentParser();p.add_argument('--phase',choices=PHASES,required=True);p.add_argument('--instance');p.add_argument('--execute',action='store_true');p.add_argument('--cargo-reviewed',action='store_true');p.add_argument('--region',choices=['valleyiv','wuling']);a=p.parse_args()

 try:

  if a.execute:require_execution('endfield')
  plan=make_plan(a.phase,a.instance,a.region)

  if a.execute:result,code=execute(plan,cargo_reviewed=a.cargo_reviewed)

  else:result,code=plan,0

  print(json.dumps(result,ensure_ascii=False));return code

 except Exception as e:print(json.dumps({'status':'blocked','error':str(e)},ensure_ascii=False));return 2

if __name__=='__main__':raise SystemExit(main())
