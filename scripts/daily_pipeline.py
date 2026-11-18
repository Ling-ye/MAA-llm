"""Fail-closed serial day coordinator. Default/read commands never launch games.
The supervising dot verifies live screenshots between prepare, run and close.
"""
from __future__ import annotations
import argparse,datetime as dt,json,os,subprocess,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from project_paths import config_path, install_path, require_execution
from runner import atomic_json,exclusive_lock,game_day,now,read_json
GAMES=('arknights','gf2','endfield')
PHASES=('pending','prepared','running','awaiting_verification','verified','closed','blocked')

def new_state(day):return {'schema':1,'day':day,'games':{g:{'phase':'pending'} for g in GAMES},'events':[]}
def next_game(state):return next((g for g in GAMES if state['games'][g]['phase']!='closed'),None)
def contained(path,root=ROOT):
 p=Path(path).resolve();p.relative_to(root.resolve());return p

def validate_evidence(path,root=ROOT):
 p=contained(path,root)
 if not p.is_file() or not p.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('A local PNG evidence file is required')
 return str(p)

def verified_receipt(game,r):
 if r.get('error'):return False
 if game=='arknights':return r.get('daily_reward_verified') is True
 if game=='gf2':return r.get('verified') is True
 return r.get('daily_reward_verified') is True and r.get('activity')==100

def transition(state,game,event,payload):
 if game not in GAMES or next_game(state)!=game:raise ValueError('Games must finish and close serially')
 item=state['games'][game];phase=item['phase']
 required={'prepared':('pending',),'started':('prepared',),'returned':('running',),'verified':('awaiting_verification',),'closed':('verified',),'blocked':('pending','prepared','running','awaiting_verification','verified')}
 if event not in required or phase not in required[event]:raise ValueError(f'Invalid transition {phase}->{event}; do not reset/replay automatically')
 target={'started':'running','returned':'awaiting_verification'}.get(event,event)
 item.update(payload);item['phase']=target;item['updated']=now()
 state['events'].append({'game':game,'event':event,'at':now()})
 return state

def receipt_terminal(game,r):
 if r.get('error'):return True
 if game=='arknights':return r.get('status')=='automation_completed_unverified'
 if game=='endfield':return r.get('automation_succeeded') is True and r.get('state',{}).get('is_running') is False
 return bool(r.get('tasks')) and all(t.get('status')=='maa_completed' for t in r['tasks'])

def process_alive(pid):
 if not pid:raise ValueError('Missing tracked worker PID')
 import ctypes
 k=ctypes.WinDLL('kernel32',use_last_error=True);k.OpenProcess.restype=ctypes.c_void_p;k.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32];k.CloseHandle.argtypes=[ctypes.c_void_p]
 h=k.OpenProcess(0x100000,False,int(pid))
 if not h:
  err=ctypes.get_last_error()
  if err==87:return False
  raise RuntimeError('Cannot verify worker exit; fail closed')
 try:return k.WaitForSingleObject(h,0)==258
 finally:k.CloseHandle(h)
def next_action(state):
 game=next_game(state)
 if game is None:
  from daily_audit import audited_next
  return audited_next(state,ROOT)[0]
 item=state['games'][game];phase=item['phase']
 return {'game':game,'phase':phase,'action':{'pending':'prepare_and_inspect_login','prepared':'run_authorized_adapter','running':'inspect_existing_pid_and_receipt_do_not_restart','awaiting_verification':'inspect_live_rewards_and_save_verified_receipt','verified':'close_game_and_corresponding_maa_then_verify_process_absence','blocked':'report_blocker_do_not_retry'}[phase]}

def command(game,hwnd=None,instance=None,stage_evidence=None,screen_evidence=None):
 if game not in GAMES:raise ValueError('Unknown game')
 py=sys.executable
 if game=='arknights':
  if not stage_evidence:raise ValueError('Current TL-9 review evidence required')
  return [py,str(ROOT/'runner.py'),'--config',str(config_path('arknights.json')),'--execute','--launch-emulator','--stage-reviewed','--stage-evidence',str(stage_evidence)]
 if game=='gf2':
  if not hwnd or hwnd<=0:raise ValueError('GF2 requires freshly verified HWND')
  if not screen_evidence:raise ValueError('Current GF2 screen review evidence required')
  return [str(install_path('gf2')/'python'/'python.exe'),str(ROOT/'gf2_safe.py'),'--execute','--hwnd',str(hwnd),'--screen-reviewed','--screen-evidence',str(screen_evidence)]
 if not instance:raise ValueError('Endfield requires runtime ID returned by bootstrap')
 return [py,str(ROOT/'endfield_safe.py'),'--execute','--phase','daily','--instance',instance]

def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('action',choices=['plan','status','init','prepared','run','collect','verified','closed','blocked']);p.add_argument('--game',choices=GAMES);p.add_argument('--execute',action='store_true');p.add_argument('--evidence',type=Path);p.add_argument('--receipt',type=Path);p.add_argument('--hwnd',type=int);p.add_argument('--instance');p.add_argument('--reason');p.add_argument('--stage-reviewed',action='store_true');p.add_argument('--stage-evidence',type=Path);a=p.parse_args(argv)
 day=game_day();path=ROOT/'state'/('daily-'+day+'.json');state=read_json(path) if path.exists() else new_state(day)
 if a.action in ('plan','status'):
  from daily_audit import audit
  print(json.dumps({'state':state,'next':next_action(state),'coverage_audit':audit(day,ROOT,state)},ensure_ascii=False,indent=2));return 0
 if not a.execute:raise ValueError('Mutation/launch requires --execute; plan is read-only')
 if (ROOT/'STOP').exists():raise RuntimeError('STOP exists; no changes or launches')
 with exclusive_lock(ROOT/'state'/'orchestrator.lock'):
  state=read_json(path) if path.exists() else new_state(day)
  if a.action=='init':atomic_json(path,state);return 0
  game=a.game or next_game(state)
  if not game:raise ValueError('Day already closed; no replay')
  item=state['games'][game]
  if a.action=='prepared':
   ev=validate_evidence(a.evidence)
   if time.time()-Path(ev).stat().st_mtime>300:raise ValueError('Home screenshot stale')
   stage_evidence=None
   if game=='arknights':
    if not a.stage_reviewed:raise ValueError('Current TL-9 review required')
    stage_evidence=validate_evidence(a.stage_evidence)
    if not 0<=time.time()-Path(stage_evidence).stat().st_mtime<=300:raise ValueError('Stage screenshot stale')
   transition(state,game,'prepared',{'home_evidence':ev,'stage_evidence':stage_evidence,'hwnd':a.hwnd,'instance':a.instance,'prepared_at_epoch':time.time()})
  elif a.action=='run':
   if item['phase']!='prepared':raise ValueError('Home/login verification required')
   if time.time()-item['prepared_at_epoch']>300:raise ValueError('Home verification stale; inspect instead of launch')
   require_execution(game)
   cmd=command(game,item.get('hwnd'),item.get('instance'),item.get('stage_evidence'),item.get('home_evidence'))
   directory=ROOT/'runs'/('coordinator-'+day+'-'+game);directory.mkdir(parents=True,exist_ok=True)
   transition(state,game,'started',{'command':cmd,'directory':str(directory),'started_epoch':time.time()});atomic_json(path,state)
   try:
    with (directory/'stdout.log').open('ab') as out,(directory/'stderr.log').open('ab') as err:
     child=subprocess.Popen(cmd,cwd=ROOT,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    item['pid']=child.pid
   except Exception as e:transition(state,game,'blocked',{'reason':'launch failed: '+str(e)})
  elif a.action=='collect':
   # Deliberately requires an explicit adapter receipt; never guess most recent run.
   rp=contained(a.receipt);r=read_json(rp)
   if process_alive(item.get('pid')):raise ValueError('Adapter still running; do not collect')
   if not receipt_terminal(game,r):raise ValueError('Receipt is not terminal')
   if rp.stat().st_mtime<item.get('started_epoch',0):raise ValueError('Receipt predates this run')
   if r.get('error'):transition(state,game,'blocked',{'reason':str(r['error']),'receipt':str(rp)})
   else:transition(state,game,'returned',{'receipt':str(rp),'adapter_result':r.get('status',r.get('automation_succeeded'))})
  elif a.action=='verified':
   rp=contained(a.receipt);r=read_json(rp);ev=validate_evidence(a.evidence)
   if str(rp)!=item.get('receipt'):raise ValueError('Verification must use this run receipt')
   if not verified_receipt(game,r):raise ValueError('Receipt lacks verified full daily rewards')
   transition(state,game,'verified',{'reward_evidence':ev})
  elif a.action=='closed':
   rp=contained(a.receipt);r=read_json(rp)
   if r.get('game')!=game or not(r.get('closed') is True or (r.get('game_closed') and r.get('maa_closed'))):raise ValueError('Verified cleanup receipt required')
   if rp.stat().st_mtime<item.get('started_epoch',0):raise ValueError('Cleanup receipt stale')
   transition(state,game,'closed',{'cleanup_receipt':str(rp)})
  elif a.action=='blocked':transition(state,game,'blocked',{'reason':a.reason or 'Manual inspection needed'})
  atomic_json(path,state);print(json.dumps(next_action(state),ensure_ascii=False));return 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as e:print(str(e),file=sys.stderr);raise SystemExit(2)
