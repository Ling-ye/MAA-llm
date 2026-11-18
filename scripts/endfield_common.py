"""Shared fail-closed MaaEnd helpers. Importing performs no I/O or game actions."""
from __future__ import annotations
import datetime as dt, hashlib, json, re, struct, time, urllib.request, uuid
from pathlib import Path
from runner import atomic_json, exclusive_lock
ROOT=Path(__file__).resolve().parent
from project_paths import install_path, POLICIES, require_execution
APP=install_path('endfield')
HOST='http://127.0.0.1:12701/api'
VERSION='v3.1.0'; FRAMEWORK='v5.16.1'; TZ=dt.timezone(dt.timedelta(hours=8))
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def day(value=None): return ((value or dt.datetime.now(TZ)).astimezone(TZ)-dt.timedelta(hours=4)).date().isoformat()
def now(): return dt.datetime.now(TZ).isoformat(timespec='seconds')
def instance_id(value=None):
 value=value or 'dot-safe-'+day().replace('-','')
 if not re.fullmatch(r'dot-safe-[a-zA-Z0-9_-]{1,50}',value):raise ValueError('Invalid isolated runtime id')
 return value
def check_stop():
 if (ROOT/'STOP').exists(): raise RuntimeError('STOP requested; no new actions permitted')
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def local_versions():
 manifest=read(APP/'interface.json')
 if manifest.get('version')!=VERSION:raise RuntimeError('MaaEnd version changed; review before use')
 from policy_integrity import read_policy
 baseline=read_policy('endfield-safety-baseline.json')
 for name in ('endfield-visit-overrides.json','endfield-target-inventory-request.json','endfield-stock-sell.json','endfield-stock-buy.json'):read_policy(name)
 for file,sha in baseline['sha256'].items():
  if digest(APP/file)!=sha:raise RuntimeError('Reviewed resource changed: '+file)
 return manifest
def request(path,body=None,method=None,binary=False):
 if not path.startswith('/') or '..' in path:raise ValueError('API path rejected')
 data=None if body is None else json.dumps(body,ensure_ascii=False).encode('utf8')
 req=urllib.request.Request(HOST+path,data=data,headers={'Content-Type':'application/json'},method=method)
 with urllib.request.urlopen(req,timeout=30) as response:
  content=response.read()
  return content if binary else json.loads(content)
def idle_states(api=request):
 states=api('/maa/state')['instances']
 if any(v.get('is_running') for v in states.values()):raise RuntimeError('Another MaaEnd task is running')
 return states
def live_versions(api=request):
 value=api('/maa/initialized')
 if not value.get('initialized') or value.get('version')!=FRAMEWORK:raise RuntimeError('MaaFramework not initialized or version changed')
def capture(instance,target,api=request,required=False):
 sub='dot-evidence-'+uuid.uuid4().hex[:8];base='/maa/instances/'+instance
 subscribed=False
 try:
  api(base+'/screenshot/subscribe',{'subscriber_id':sub,'interval_ms':400});subscribed=True;time.sleep(1)
  data=api(base+'/screenshot',binary=True)
  if not data.startswith(b'\x89PNG\r\n\x1a\n'):raise RuntimeError('Screenshot is not PNG')
  width,height=struct.unpack('!II',data[16:24]);Path(target).write_bytes(data)
  return {'path':str(Path(target).resolve()),'sha256':hashlib.sha256(data).hexdigest(),'width':width,'height':height}
 except Exception as e:
  if required:raise
  return {'error':str(e)}
 finally:
  if subscribed:
   try:api(base+'/screenshot/unsubscribe',{'subscriber_id':sub})
   except Exception:pass

def task_body(tasks,manifest):
 return {'tasks':tasks,'agent_configs':manifest['agent'],'cwd':str(APP),'tcp_compat_mode':False,
  'controller_info':{'name':'Win32-Front','type':'Win32'},'pi_envs':{'PI_VERSION':VERSION,'PI_CLIENT_MAAFW_VERSION':FRAMEWORK,
  'PI_CONTROLLER':json.dumps(manifest['controller'][0]),'PI_RESOURCE':json.dumps(manifest['resource'][0]),'PI_CLIENT_LANGUAGE':'zh_cn'}}
def log_position():
 p=APP/'debug'/'go-service.log'
 if not p.exists():return {'size':0,'head':None}
 with p.open('rb') as f:head=hashlib.sha256(f.read(256)).hexdigest()
 return {'size':p.stat().st_size,'head':head}

def collect_log(offset,target):
 p=APP/'debug'/'go-service.log'
 if not p.exists():return ''
 with p.open('rb') as f:
  size=offset.get('size',0) if isinstance(offset,dict) else offset
  head=hashlib.sha256(f.read(256)).hexdigest();f.seek(0)
  same=not isinstance(offset,dict) or offset.get('head')==head
  if same and p.stat().st_size>=size:f.seek(size)
  data=f.read()
 Path(target).write_bytes(data)
 return data.decode('utf8',errors='replace')
def safety_errors(log_text):
 errors=[]
 for line in log_text.splitlines():
  try:v=json.loads(line)
  except ValueError:continue
  if v.get('stop_task') is True or v.get('level') in ('error','fatal','panic'):
   errors.append(v)
 return errors

def validate_receipt(path,evidence_required=True):
 path=Path(path).resolve(); path.relative_to(ROOT/'runs');r=read(path)
 if r.get('game')!='endfield' or r.get('game_day')!=day() or r.get('maa_version')!=VERSION or r.get('framework_version')!=FRAMEWORK:raise RuntimeError('Receipt game/day/version mismatch')
 instance_id(r.get('instance'))
 if r.get('daily_reward_verified') is not True or r.get('activity')!=100 or r.get('safety_errors'):raise RuntimeError('Daily 100 not verified safely')
 if evidence_required:
  e=r.get('verification_evidence',{});p=Path(e.get('path','')).resolve();p.relative_to(ROOT)
  if not p.is_file() or digest(p)!=e.get('sha256') or not p.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):raise RuntimeError('Missing or changed reward screenshot')
 return r
