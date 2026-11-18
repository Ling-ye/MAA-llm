"""Explicit approved recruitment/base/credit supplement. No startup or DLL at import."""

import argparse,hashlib,json,os,subprocess,sys,time,uuid

from pathlib import Path

import runner as base
from project_paths import config_path, require_execution

import ark_v2_evidence as evidence

import ark_plan as original # Import before isolated child patches runner plan.

ROOT=Path(__file__).resolve().parent



def make_plan(c):

 if c.get('supplement_policy')!='approved-ark-operations-v2':raise ValueError('Operations v2 policy mismatch')

 tasks=original.make_plan(dict(c,supplement_policy='approved-ark-operations-v1'))

 tasks[0]['params'].update(refresh=True,force_refresh=False,expedite=True,expedite_times=4)

 tasks[1]['params'].update(drones='Money',replenish=False)

 return tasks

ORIGINAL_MAKE_PLAN=base.make_plan



def stop_check():

 if (ROOT/'STOP').exists():raise RuntimeError('STOP requested')

def guard():

 p=ROOT/'state'/f'arknights-{base.game_day()}.operations.attempt.json'

 if list(p.parent.glob(p.name+'*')) or list(p.parent.glob(f'arknights-{base.game_day()}.accelerated-*.attempt.json*')):raise RuntimeError('Operations already attempted; inspect evidence, never replay')

 return p



def bound_summary(summary=None):

 ledger=ROOT/'state'/f'arknights-{base.game_day()}.operations.attempt.json'

 if summary is None and not ledger.exists():return None

 bound=Path(base.read_json(ledger)['run_dir']).resolve()/'summary.json'

 path=Path(summary).resolve() if summary is not None else bound

 if path.name!='summary.json' or path.parent.parent!=(ROOT/'runs').resolve() or path!=bound:raise RuntimeError('Summary outside current operations ledger scope')

 record=base.read_json(path)

 if record.get('game')!='arknights' or record.get('day')!=base.game_day() or Path(record.get('run_dir','')).resolve()!=path.parent:raise RuntimeError('Summary game/day/run binding mismatch')

 return path,record



def status(summary=None):

 loaded=bound_summary(summary)

 return loaded[1] if loaded else {'status':'not_attempted'}



def resume_check(summary,require_complete=False):

 path,record=bound_summary(summary);folder=path.parent

 if path.name!='summary.json' or folder.parent!=(ROOT/'runs').resolve() or record.get('schema')!=2 or record.get('day')!=base.game_day():raise RuntimeError('Not a current v2 receipt')

 ledger=ROOT/'state'/f'arknights-{base.game_day()}.operations.attempt.json'

 if Path(base.read_json(ledger)['run_dir']).resolve()!=folder:raise RuntimeError('Attempt binding mismatch')

 if list(ledger.parent.glob(f'arknights-{base.game_day()}.accelerated-*.attempt.json*')):raise RuntimeError('Additional accelerated attempt exists')

 cfg=folder/'config.json';c=base.read_json(cfg);plan=make_plan(c)

 if evidence.sha(cfg)!=record.get('config_sha256') or len(record.get('tasks',[]))!=len(plan):raise RuntimeError('Config or task list changed')

 pending=False;completed=0

 for i,(item,task) in enumerate(zip(record['tasks'],plan)):

  stage=folder/(str(i)+'-'+task['type'])

  if item.get('type')!=task['type'] or item.get('task_sha256')!=evidence.sha(stage/'task.json') or base.read_json(stage/'task.json')!=task:raise RuntimeError('Stage binding mismatch')

  if item.get('status')=='complete' and not pending:

   evidence.validate(stage,cfg,task,c['expected_version'],item.get('evidence'))

   ws=base.read_json(stage/'worker-state.json')

   if ws.get('status')!='complete' or ws.get('evidence')!=item.get('evidence'):raise RuntimeError('Worker receipt changed')

   completed+=1

  elif item.get('status')=='planned':

   pending=True

   if set(x.name for x in stage.iterdir())!={'task.json'}:raise RuntimeError('Planned stage has execution artifacts')

  else:raise RuntimeError('Running/submitting/unknown or non-prefix completion: never replay')

 if require_complete:

  if pending or completed!=len(plan) or record.get('daily_reward_verified') is not True or record.get('status') not in ('automation_completed_unverified','visual_verified','verified','verified_closed'):raise RuntimeError('Not fully completed and visually verified')

 elif not pending:raise RuntimeError('Nothing to resume')

 return record,c,plan,completed



def home_proof(path):

 if not path:raise RuntimeError('Fresh home PNG evidence required: --home-evidence')

 p=Path(path).resolve();data=p.read_bytes();age=time.time()-p.stat().st_mtime

 if data[:8]!=b'\x89PNG\r\n\x1a\n' or not 0<=age<=300:raise RuntimeError('Home evidence must be PNG and no older than 5 minutes')

 return {'path':str(p),'sha256':hashlib.sha256(data).hexdigest(),'mtime':p.stat().st_mtime,'reviewed_at':base.now()}



def execute_child(argv,log,timeout,on_pid):

 stop_check()

 child=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

 deadline=time.monotonic()+timeout

 try:

  on_pid(child.pid)

  while child.poll() is None:

   stopped=(ROOT/'STOP').exists()

   if stopped or time.monotonic()>deadline:

    # STOP is also observed by the worker's own loop, which invokes Asst.stop in finally.

    # Never stop another Python process or remove STOP. On timeout the exact child alone is terminated.

    if stopped:

     try:child.wait(timeout=5)

     except subprocess.TimeoutExpired:pass

    if child.poll() is None:child.terminate()

    try:child.wait(timeout=5)

    except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)

    raise RuntimeError('STOP requested' if stopped else 'Worker timeout; side effects unknown')

   time.sleep(.2)

  return child.returncode

 except BaseException:

  if child.poll() is None:

   child.terminate()

   try:child.wait(timeout=5)

   except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)

  raise



def run(config,execute=False,home_reviewed=False,resume=None,home_evidence=None):

 c=base.load_config(config);plan=make_plan(c)

 if not execute:return {'mode':'plan_only','tasks':plan},0

 if not home_reviewed:raise RuntimeError('Verify current Arknights home before --home-reviewed')

 if c.get('ready') is not True:raise RuntimeError('Config not ready')

 proof=home_proof(home_evidence)

 with base.exclusive_lock(ROOT/'state'/'pipeline.lock'):

  stop_check();proof=home_proof(home_evidence)

  if resume:

   record,c,plan,start=resume_check(resume);folder=Path(resume).resolve().parent;cfg=folder/'config.json';ledger=ROOT/'state'/f'arknights-{base.game_day()}.operations.attempt.json'

  else:

   ledger=guard();start=0

   folder=ROOT/'runs'/('ark-operations-v2-'+base.dt.datetime.now(base.TZ).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);folder.mkdir(parents=True)

   cfg=folder/'config.json';base.atomic_json(cfg,c)

   primary=ROOT/'state'/f'arknights-{base.game_day()}.json'

   record={'schema':2,'game':'arknights','day':base.game_day(),'status':'planned','run_dir':str(folder),'plan_version':'approved-ark-operations-v2','config_sha256':evidence.sha(cfg),'tasks':[],'daily_reward_verified':False,'primary_receipt':str(primary),'primary_sha256':evidence.sha(primary) if primary.exists() else None}

   for i,task in enumerate(plan):

    stage=folder/(str(i)+'-'+task['type']);stage.mkdir();base.atomic_json(stage/'task.json',task)

    record['tasks'].append({'type':task['type'],'status':'planned','task_sha256':evidence.sha(stage/'task.json')})

   with ledger.open('x',encoding='utf8') as f:json.dump({'run_dir':str(folder),'status':'planned'},f)

  if resume:
   previous=Path(resume).read_bytes();archive=folder/('resume-before-'+uuid.uuid4().hex+'.json');archive.write_bytes(previous)
   record.setdefault('recovery_history',[]).append({'path':str(archive),'sha256':evidence.sha(archive),'at':base.now(),'previous_status':record.get('status')})
   record.pop('error',None);record.pop('capture_error',None)
  def save():

   base.atomic_json(folder/'summary.json',record);base.atomic_json(ledger,{'run_dir':str(folder),'status':record['status']})

  record["home_review"]=proof;save();active=None

  try:

   base.preflight(c,False);base.screenshot(c,folder/('resume-before.png' if resume else 'before.png'))

   for i in range(start,len(plan)):

    if i==start:home_proof(home_evidence)

    stop_check();task=plan[i];stage=folder/(str(i)+'-'+task['type']);active=record['tasks'][i]

    active['status']='submitting';record['status']='submitting';save()

    with (stage/'worker.log').open('wb') as log:

     # The child publishes its running handshake before touching DLL/ADB; submission is already durably uncertain.

     def pid_started(pid):active.update(child_pid=pid,status='running');record.update(status='running');save()

     code=execute_child([sys.executable,str(Path(__file__).resolve()),'--worker','--config',str(cfg),'--taskfile',str(stage/'task.json'),'--directory',str(stage)],log,c['task_timeout_seconds'],pid_started)

    if code!=0:raise RuntimeError(task['type']+' worker failed; never replay')

    active['evidence']=evidence.validate(stage,cfg,task,c['expected_version'])

    ws=base.read_json(stage/'worker-state.json')

    if ws.get('status')!='complete' or ws.get('evidence')!=active['evidence']:raise RuntimeError('Worker evidence binding missing or changed')

    active['status']='complete';record['status']='running';save();active=None

    base.screenshot(c,stage/'after.png')

   record['status']='automation_completed_unverified';code=0

  except Exception as exc:

   if active is not None:active['status']='unknown'

   record.update(status='unknown' if active is not None else 'paused',error=str(exc));code=2

   try:base.screenshot(c,folder/'blocked.png')

   except Exception as capture:record['capture_error']=str(capture)

  finally:record['ended']=base.now();save()

  return record,code



def bound_worker(config,taskfile,directory):

 c=base.load_config(config);task=base.read_json(taskfile)

 if c.get('ready') is not True or task not in make_plan(c):raise RuntimeError('Worker readiness or task allowlist rejected')

 stop_check();folder=Path(directory).resolve()

 base.atomic_json(folder/'worker-state.json',{'status':'running','pid':os.getpid(),'task_sha256':evidence.sha(taskfile),'config_sha256':evidence.sha(config),'at':base.now()})

 base.make_plan=make_plan

 try:

  code=base.worker(config,taskfile,directory)

  proof=evidence.validate(folder,config,task,c['expected_version']) if code==0 else None

  base.atomic_json(folder/'worker-state.json',{'status':'complete' if code==0 else 'unknown','evidence':proof,'at':base.now()});return code

 except Exception:

  base.atomic_json(folder/'worker-state.json',{'status':'unknown','at':base.now()});raise



def main():

 p=argparse.ArgumentParser();p.add_argument('--config',default=str(config_path('ark-operations-v2.json')));p.add_argument('--execute',action='store_true');p.add_argument('--home-reviewed',action='store_true');p.add_argument('--worker',action='store_true');p.add_argument('--taskfile');p.add_argument('--directory');p.add_argument('--verify-complete',action='store_true');p.add_argument('--status',action='store_true');p.add_argument('--summary');p.add_argument('--home-evidence');p.add_argument('--resume');a=p.parse_args()

 try:

  if a.execute:require_execution('arknights')
  if a.worker:

   # Isolated child uses this fixed approved allowlist; base worker still enforces membership,

   # exact MAA version, STOP, timeouts and callback success. No arbitrary caller task is accepted.

   return bound_worker(a.config,a.taskfile,a.directory)

  if a.verify_complete:

   if not a.summary:raise RuntimeError('--summary required')

   resume_check(a.summary,require_complete=True);print(json.dumps({'verified_complete':True,'day':base.game_day()}));return 0

  if a.status:print(json.dumps(status(a.summary),ensure_ascii=False));return 0

  out,code=run(a.config,a.execute,a.home_reviewed,a.resume,a.home_evidence);print(json.dumps(out,ensure_ascii=False));return code

 except Exception as e:print(json.dumps({'status':'blocked','error':str(e)},ensure_ascii=False));return 2

if __name__=='__main__':raise SystemExit(main())
