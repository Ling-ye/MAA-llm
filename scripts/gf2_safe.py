"""Safe GF2 PC adapter. Default is offline plan. No purchases, drugs or dismantling.
Exit: 0 plan/agent probe; 1 failed; 2 blocked; 3 tasks completed, manual daily verification needed.
"""
import argparse,ctypes,datetime,json,os,struct,subprocess,time,uuid,zlib
from pathlib import Path
from project_paths import install_path, POLICIES, require_execution, add_native_transport_argument, require_native_pc
BASE=install_path('gf2')
ROOT=Path(__file__).resolve().parent
VERSION='v2.8.4'
TASKS=['PrepareDailyTasks','PublicAreaDailyTasks','ClaimRewardTasks']
DISABLED=['使用完接入密钥(体力药水)','商城免费每日补给箱购买','DispatchCenter-mysteryBox','开始动态招募祝福任务','开始巡录任务','边界推进委托领取','领取班组奖励']
class Blocked(RuntimeError):pass

def atomic_json(path,data):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
 tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8');os.replace(tmp,path)

def game_day(now=None):
 tz=datetime.timezone(datetime.timedelta(hours=8))
 now=now or datetime.datetime.now(tz)
 if now.tzinfo is None:raise ValueError('timezone-aware time required')
 return (now.astimezone(tz)-datetime.timedelta(hours=4)).date().isoformat()

def plan():return {'game':'gf2','version':VERSION,'tasks':TASKS,'disabled':DISABLED,'verification_required':True}

def gate(root,day):
 if (root/'STOP').exists():raise Blocked('STOP exists; no launch permitted')
 ledger=root/'state'/('gf2-'+day+'.attempt.json')
 if ledger.exists():raise Blocked('Prior attempt exists; inspect receipt before any replay')
 return ledger

def write_png(path,im):
 if im is None:raise RuntimeError('empty screenshot')
 h,w,channels=im.shape
 if channels!=3:raise RuntimeError('unexpected screenshot format')
 def chunk(t,d):return struct.pack('!I',len(d))+t+d+struct.pack('!I',zlib.crc32(t+d)&0xffffffff)
 data=b''.join(b'\0'+row.tobytes() for row in im[:,:,::-1])
 path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(data))+chunk(b'IEND',b''))

def wait_job(job,root,deadline,agent=None):
 while not job.done:
  if (root/'STOP').exists():raise RuntimeError('STOP requested')
  if time.monotonic()>deadline:raise RuntimeError('operation timeout')
  if agent and agent.process.poll() is not None:raise RuntimeError('official agent exited')
  time.sleep(.2)
 if not job.succeeded:raise RuntimeError('MAA operation failed')

class OfficialAgent:
 def __init__(self,base,run,resource):
  from maa.agent_client import AgentClient
  self.client=AgentClient();self.process=None;self.log=None
  if not self.client.set_timeout(5000):raise RuntimeError('cannot bound agent timeout')
  if not self.client.bind(resource):raise RuntimeError('agent bind failed')
  self.log=(run/'official-agent.log').open('wb')
  try:
   self.process=subprocess.Popen([str(base/'python'/'python.exe'),'-u',str(base/'agent'/'main.py'),self.client.identifier],cwd=str(base),stdout=self.log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
   if not self.client.connect():raise RuntimeError('official agent connect failed')
   self.recognizers=self.client.custom_recognition_list
   if 'scroll_end' not in self.recognizers:raise RuntimeError('scroll_end not registered; fail closed')
  except Exception:
   self.close();raise
 def close(self):
  try:self.client.disconnect()
  except Exception:pass
  if self.process:
   try:self.process.wait(timeout=5)
   except subprocess.TimeoutExpired:
    self.process.terminate()
    try:self.process.wait(timeout=3)
    except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
  if self.log:self.log.close()

def execute(base,root,hwnd=None,probe=False):
 if (root/'STOP').exists():raise Blocked('STOP exists')
 manifest=json.loads((base/'interface.json').read_text(encoding='utf-8-sig'))
 if manifest.get('version')!=VERSION:raise Blocked('Untested resource version')
 # Explicit bounded game handle required. Never choose another app by loose title.
 if not probe:
  if not hwnd:raise Blocked('--hwnd is required')
  buf=ctypes.create_unicode_buffer(256);ctypes.windll.user32.GetWindowTextW(hwnd,buf,256)
  if '少女前线2' not in buf.value or '自动化' in buf.value:raise Blocked('Wrong game window')
  if not ctypes.windll.user32.IsWindow(hwnd):raise Blocked('Game window disappeared')
 import msvcrt
 (root/'state').mkdir(parents=True,exist_ok=True)
 lock=(root/'state'/'pipeline.lock').open('a+b');lock.seek(0)
 try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
 except OSError:lock.close();raise Blocked('Another game pipeline is active')
 run=None;agent=None;tasker=None;controller=None;status={'tasks':[],'verified':False,'daily_reward_verified':False,'game':'gf2','day':game_day(),'version':VERSION};ledger=None
 try:
  if not probe:ledger=gate(root,game_day())
  run=root/'runs'/(('gf2-agent-probe-' if probe else 'gf2-')+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);run.mkdir(parents=True)
  status.update(run=str(run),status='initializing',probe_only=probe)
  if ledger:
   with ledger.open('x',encoding='utf8') as f:json.dump({'run':str(run),'started_at':datetime.datetime.now().astimezone().isoformat(),'verified':False},f)
  atomic_json(run/'summary.json',status);atomic_json(run/'plan.json',plan())
  from maa.library import Library
  from maa.toolkit import Toolkit
  from maa.resource import Resource
  Library.open(base/'maafw');Toolkit.init_option(run)
  resource=Resource();agent=OfficialAgent(base,run,resource)
  status['registered_recognizers']=agent.recognizers
  atomic_json(run/'summary.json',status)
  if probe:
   status['status']='agent_registration_verified_no_game';return 0,status
  from maa.controller import Win32Controller
  from maa.define import MaaWin32ScreencapMethodEnum as SC,MaaWin32InputMethodEnum as IN
  from maa.tasker import Tasker
  controller=Win32Controller(hwnd,SC.Foreground,IN.Seize,IN.Seize)
  wait_job(controller.post_connection(),root,time.monotonic()+30,agent)
  for path in [base/'resource'/'base',base/'resource'/'resource_pc']:
   wait_job(resource.post_bundle(path),root,time.monotonic()+60,agent)
  tasker=Tasker();tasker.bind(resource,controller)
  if not tasker.inited:raise RuntimeError('tasker not initialized')
  if not agent.client.register_sink(resource,controller,tasker):raise RuntimeError('agent event sinks not registered')
  override={n:{'enabled':False} for n in DISABLED}
  def snap(name):
   wait_job(controller.post_screencap(),root,time.monotonic()+15,agent)
   write_png(run/name,controller.cached_image)
  snap('before.png')
  for index,name in enumerate(TASKS):
   if (root/'STOP').exists():raise RuntimeError('STOP before task')
   status['tasks'].append({'entry':name,'status':'running'});atomic_json(run/'summary.json',status)
   wait_job(tasker.post_task(name,override),root,time.monotonic()+600,agent)
   status['tasks'][-1]['status']='maa_completed';atomic_json(run/'summary.json',status)
   snap(f'{index+1:02d}-{name}-after.png')
  status['status']='automation_completed_unverified'
  return 3,status
 except Exception as e:
  status['status']='blocked' if isinstance(e,Blocked) else 'failed';status['error']=str(e)
  if status['tasks'] and status['tasks'][-1]['status']=='running':status['tasks'][-1]['status']='failed'
  if controller is not None and run is not None:
   try:
    shot=controller.post_screencap();end=time.monotonic()+10
    while not shot.done and time.monotonic()<end:time.sleep(.2)
    if shot.done and shot.succeeded:write_png(run/'failure.png',controller.cached_image)
   except Exception as evidence_error:status['evidence_error']=str(evidence_error)
  return (2 if isinstance(e,Blocked) else 1),status
 finally:
  if tasker:
   try:
    job=tasker.post_stop();deadline=time.monotonic()+15
    while not job.done and time.monotonic()<deadline:time.sleep(.2)
    if not job.done:status['stop_timeout']=True
   except Exception as e:status['stop_error']=str(e)
  if agent:agent.close()
  if run:
   atomic_json(run/'summary.json',status)
   if ledger:atomic_json(ledger,{'run':str(run),'status':status.get('status'),'verified':False})
  lock.close()

def main(argv=None):
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group();g.add_argument('--execute',action='store_true');g.add_argument('--check-agent',action='store_true');p.add_argument('--hwnd',type=int);p.add_argument('--screen-reviewed',action='store_true');p.add_argument('--screen-evidence');add_native_transport_argument(p);a=p.parse_args(argv)
 if not a.execute and not a.check_agent:print(json.dumps(plan(),ensure_ascii=False));return 0
 try:
  require_native_pc('gf2',a.transport)
  require_execution('gf2')
  if a.execute:
   if not a.screen_reviewed:raise Blocked('Current screen review required')
   from ark_operations_v2 import home_proof
   home_proof(a.screen_evidence)
  code,status=execute(BASE,ROOT,a.hwnd,a.check_agent)
 except Exception as e:code=2 if isinstance(e,Blocked) else 1;status={'status':'blocked' if code==2 else 'failed','error':str(e),'verified':False}
 print(json.dumps(status,ensure_ascii=False));return code
if __name__=='__main__':raise SystemExit(main())
