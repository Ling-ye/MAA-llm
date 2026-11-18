"""Prepare isolated runtime in an ALREADY running MaaEnd. Never launches or elevates apps."""
import argparse,ctypes,json,time
from pathlib import Path
from endfield_common import *

def window_check(hwnd):
 if not isinstance(hwnd,int) or hwnd<=0:raise ValueError('Explicit positive game HWND required')
 user=ctypes.windll.user32;user.SetProcessDPIAware()
 title=ctypes.create_unicode_buffer(256);klass=ctypes.create_unicode_buffer(256)
 user.GetWindowTextW(ctypes.c_void_p(hwnd),title,256);user.GetClassNameW(ctypes.c_void_p(hwnd),klass,256)
 if title.value!='Endfield' or klass.value!='UnityWndClass':raise RuntimeError('HWND is not the verified Endfield game')
 class Rect(ctypes.Structure):_fields_=[('left',ctypes.c_long),('top',ctypes.c_long),('right',ctypes.c_long),('bottom',ctypes.c_long)]
 r=Rect()
 if not user.GetClientRect(ctypes.c_void_p(hwnd),ctypes.byref(r)) or (r.right,r.bottom)!=(1280,720):raise RuntimeError('Set actual client to1280x720 window before bootstrap')
 return {'hwnd':hwnd,'title':title.value,'class':klass.value,'width':r.right,'height':r.bottom}

def prepare(instance,hwnd,api=request,check_window=window_check):
 check_stop();local_versions();instance=instance_id(instance)
 with exclusive_lock(ROOT/'state'/'pipeline.lock'):
  check_stop();window=check_window(hwnd);live_versions(api);states=idle_states(api)
  if not api('/system/is-elevated').get('elevated'):raise RuntimeError('MaaEnd is not in its verified elevated session; user must handle permission prompt')
  record=ROOT/'state'/('endfield-bootstrap-'+instance+'.json');base='/maa/instances/'+instance
  if instance in states:
   if not record.exists() or read(record).get('window')!=window or read(record).get('game_day')!=day():raise RuntimeError('Existing runtime binding uncertain; do not overwrite')
  else:
   check_stop();api(base,{},method='PUT')
   atomic_json(record,{'instance':instance,'game_day':day(),'window':window,'status':'created','at':now()})
  check_stop();api(base+'/connect',{'type':'Win32','handle':hwnd,'screencap_method':32,'mouse_method':1,'keyboard_method':1})
  check_stop();api(base+'/resource/load',{'paths':[str(APP/'resource')]})
  deadline=time.monotonic()+60
  while True:
   check_stop();s=api('/maa/state')['instances'][instance]
   if s.get('connected') and s.get('resource_loaded'):break
   if time.monotonic()>deadline:raise RuntimeError('Bootstrap connection/resource timeout')
   time.sleep(1)
  evidence=ROOT/'evidence';evidence.mkdir(exist_ok=True)
  shot=capture(instance,evidence/(instance+'-bootstrap.png'),api,required=True)
  if (shot['width'],shot['height'])!=(1280,720):raise RuntimeError('Controller screenshot dimension mismatch')
  result={'instance':instance,'game_day':day(),'maa_version':VERSION,'framework_version':FRAMEWORK,'window':window,'status':'awaiting_home_visual_review','screenshot':shot,'at':now()}
  atomic_json(record,result);return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--instance');p.add_argument('--hwnd',type=int);a=p.parse_args()
 try:
  if a.execute:require_execution('endfield')
  if not a.execute:r={'mode':'plan_only','instance':instance_id(a.instance),'requires':['already running MaaEnd localhost12701','user-authorized elevated session','Endfield logged in','actual1280x720window','explicit verified HWND'],'changes':['isolated runtime only'],'does_not':['launch or elevate software','accept agreements','login','start daily','edit GUI profiles']}
  else:r=prepare(a.instance,a.hwnd)
  print(json.dumps(r,ensure_ascii=False));return 0
 except Exception as e:print(json.dumps({'status':'blocked','error':str(e)},ensure_ascii=False));return 2
if __name__=='__main__':raise SystemExit(main())
