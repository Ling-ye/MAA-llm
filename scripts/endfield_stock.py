"""Stock Redistribution only: approved elastic sell/buy. Plan-only by default."""

import argparse,json,time,uuid,re,copy

from endfield_common import *
from project_paths import add_native_transport_argument, require_native_pc

from endfield_safe import state_success

PHASES=('sell','buy')

TASK_HASHES={'AutoSell.json': '2edd4975d85fca394e9c82c73b26600839ff619444eb86cd7b96514d2ea479f6', 'AutoStockpile.json': 'd4ab8539627c13e9f8fc99a3e54c28ae5ccc9e999a49aa10cce759b0fb81a5c0'}

APPROVED_OPTIONS={'AutoStockpile': {'AutoStockpileAllowDataUpload': {'type': 'switch', 'value': False}, 'AutoStockpileElasticValleyIV': {'type': 'switch', 'value': True}, 'AutoStockpileElasticWuling': {'type': 'switch', 'value': True}, 'AutoStockpileMinBuy': {'type': 'switch', 'value': False}, 'AutoStockpileServerTime': {'caseName': 'CN_UTC_PLUS_8', 'type': 'select'}}, 'AutoSell': {'AutoSellPricePerCategory': {'type': 'input', 'values': {'AutoSellPricePerCategoryLargePriceVolatilityValue': '5000', 'AutoSellPricePerCategoryMassivePriceVolatilityValue': '5300', 'AutoSellPricePerCategoryModeratePriceVolatilityValue': '4600'}}, 'AutoSellPriceType': {'caseName': 'AutoSellPriceTypePerCategory', 'type': 'select'}, 'AutoSellTicketOverflowValleyIV': {'type': 'input', 'values': {'AutoSellTicketOverflowValleyIVValue': '30000000'}}, 'AutoSellTicketOverflowWuling': {'type': 'input', 'values': {'AutoSellTicketOverflowWulingValue': '30000000'}}, 'AutoSellValleyIV': {'type': 'switch', 'value': True}, 'AutoSellWuling': {'type': 'switch', 'value': True}}}

def stock_versions():

 manifest=local_versions()

 for name,sha in TASK_HASHES.items():

  if digest(APP/'tasks'/name)!=sha:raise RuntimeError('Stock task changed; review '+name)

 return manifest



def make_plan(phase,instance=None):
 if phase not in PHASES:raise ValueError('Unknown stock phase')
 from policy_integrity import read_policy
 fixed=read_policy('endfield-stock-'+phase+'.json')
 return dict(fixed,phase=phase,game_day=day(),instance=instance_id(instance))

def attempt_guard(phase,current_day=None,root=None):

 if phase not in PHASES:raise ValueError('Unknown phase')

 root=root or ROOT;current_day=current_day or day();state=root/'state'

 if list(state.glob(f'endfield-stock-{current_day}-{phase}.attempt.json*')):raise RuntimeError('Stock phase already attempted; inspect evidence, no replay')

 return state/f'endfield-stock-{current_day}-{phase}.attempt.json'



PRETRADE_ERROR='json: cannot unmarshal string into Go struct field .large_price of type int'

def recovery_guard(receipt,plan):

 p=Path(receipt).resolve();p.relative_to((ROOT/'runs').resolve());r=read(p)

 if plan['phase']!='sell' or r.get('phase')!='sell' or r.get('game')!='endfield' or r.get('game_day')!=day() or r.get('instance')!=plan['instance'] or r.get('maa_version')!=VERSION or r.get('framework_version')!=FRAMEWORK:raise RuntimeError('Recovery receipt identity mismatch')

 state=r.get('state',{});run=state.get('task_run_state',{})

 if r.get('status')!='failed' or r.get('automation_succeeded') is not False or state.get('is_running') is not False or run.get('overall_status')!='Failed' or run.get('statuses')!={'dot-stock-sell':'failed'}:raise RuntimeError('Original task not proven failed and idle')

 original=ROOT/'state'/f'endfield-stock-{day()}-sell.attempt.json'

 if not original.exists() or Path(read(original).get('run_dir','')).resolve()!=p.parent:raise RuntimeError('Original attempt does not match receipt')

 errors=r.get('safety_errors',[])

 def exact(e):return e.get('component')=='autosell' and e.get('step')=='execute_sell' and e.get('message')=='parse params' and e.get('error')==PRETRADE_ERROR and e.get('level')=='error'

 if len(errors)!=1 or not exact(errors[0]):raise RuntimeError('Not the supported pretrade parse error')

 log=p.parent/'go-service.log';rows=[json.loads(line) for line in log.read_text(encoding='utf8').splitlines() if line.strip()]

 sell=[v for v in rows if v.get('component')=='autosell' or '/autosell/' in v.get('caller','')]

 if len(sell)!=2 or sell[0].get('step')!='scan_item' or sell[0].get('region')!='ValleyIV' or not exact(sell[1]):raise RuntimeError('Log not limited to scan then exact pretrade error; recovery forbidden')

 if safety_errors(log.read_text(encoding='utf8'))!=errors:raise RuntimeError('Log/receipt errors mismatch')

 req=read(p.parent/'request.json')

 if len(req.get('tasks',[]))!=1 or req['tasks'][0].get('entry')!='AutoSellMain':raise RuntimeError('Original request was not isolated sell')

 for name in ('before','after'):

  e=r.get(name,{});f=Path(e.get('path','')).resolve()

  if f.parent!=p.parent or not f.is_file() or digest(f)!=e.get('sha256'):raise RuntimeError('Original screenshot missing or changed')

 ledger=ROOT/'state'/f'endfield-stock-{day()}-sell.recovery-pretrade.attempt.json'

 if list(ledger.parent.glob(ledger.name+'*')):raise RuntimeError('Pretrade recovery already attempted')

 return ledger,{'source_receipt':str(p),'source_sha256':digest(p),'source_log_sha256':digest(log),'reason':PRETRADE_ERROR}



def execute(plan,api=request,recover_pretrade=None):

 if plan.get('game_day')!=day():raise RuntimeError('Stale stock plan')

 check_stop();manifest=stock_versions();current_day=day();instance=plan['instance']

 with exclusive_lock(ROOT/'state'/'pipeline.lock'):

  check_stop()

  if recover_pretrade:ledger,recovery=recovery_guard(recover_pretrade,plan)

  else:ledger=attempt_guard(plan['phase'],current_day);recovery=None

  live_versions(api);states=idle_states(api)

  s=states.get(instance,{})

  if not(s.get('connected') and s.get('resource_loaded')):raise RuntimeError('Run bootstrap and verify login/home before executing')

  run=ROOT/'runs'/('endfield-stock-'+plan['phase']+'-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);run.mkdir(parents=True)

  status={'game':'endfield','game_day':current_day,'maa_version':VERSION,'framework_version':FRAMEWORK,'instance':instance,

   'recovery':recovery,'phase':plan['phase'],'verified':False,'daily_reward_verified':False,'started':False,'submission_attempted':False,'status':'preflight','run_dir':str(run),'started_at':now()}

  def save():atomic_json(run/'summary.json',status)

  save();atomic_json(run/'request.json',plan)

  offset=log_position()

  try:

   status['before']=capture(instance,run/'before.png',api,required=True);save()

   if (status['before']['width'],status['before']['height'])!=(1280,720):raise RuntimeError('Expected verified 1280x720 small-window capture; do not auto-toggle display')

   check_stop()

   # Exclusive create before submitting: ambiguous transport errors must never auto-replay.

   with ledger.open('x',encoding='utf8') as f:json.dump({'recovery':recovery,'phase':plan['phase'],'run_dir':str(run),'game_day':current_day,'at':now(),'status':'attempted'},f)

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

   status['finished_at']=now();save();atomic_json(ledger,{'recovery':recovery,'phase':plan['phase'],'run_dir':str(run),'status':status['status'],'at':now()})

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

   if ledger.exists():atomic_json(ledger,{'recovery':recovery,'phase':plan['phase'],'run_dir':str(run),'status':'failed','at':now()})

   return status,2



def main():

 p=argparse.ArgumentParser();p.add_argument('--phase',choices=PHASES,required=True);p.add_argument('--instance');p.add_argument('--execute',action='store_true');p.add_argument('--recover-pretrade-parse-failure',type=Path);add_native_transport_argument(p);a=p.parse_args()

 try:

  if a.execute:
   require_native_pc('endfield',a.transport)
   require_execution('endfield')
  plan=make_plan(a.phase,a.instance)

  if a.recover_pretrade_parse_failure and not a.execute:plan['recovery_preview']=recovery_guard(a.recover_pretrade_parse_failure,plan)[1]

  result,code=execute(plan,recover_pretrade=a.recover_pretrade_parse_failure) if a.execute else (plan,0)

  print(json.dumps(result,ensure_ascii=False));return code

 except Exception as e:print(json.dumps({'status':'blocked','error':str(e)},ensure_ascii=False));return 2

if __name__=='__main__':raise SystemExit(main())
