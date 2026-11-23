"""Close only a current-day, version-matched, visually verified Endfield run."""
import argparse,json,time
from pathlib import Path
from endfield_common import *
from project_paths import add_native_transport_argument, require_native_pc
ATTACH={'CloseLauncher':False,'ApplyGameSetting':True,'GameSettingRegion':'CN','GameSettingDisplayType':'Window','ResolutionWidth':1280,'ResolutionHeight':720,'GameSettingLanguage':'Unchanged','GraphicsQuality':-1,'FrameRate':-1,'AutoHDR':'Unchanged'}
def close(receipt,api=request):
 check_stop();manifest=local_versions();r=validate_receipt(receipt);instance=r['instance']
 from verify_completion import require_coverage
 require_coverage('endfield')
 with exclusive_lock(ROOT/'state'/'pipeline.lock'):
  check_stop();live_versions(api);states=idle_states(api)
  if instance not in states or not states[instance].get('connected'):raise RuntimeError('Verified runtime is not connected; inspect process state before closing')
  task={'entry':'CloseGamePC','pipeline_override':json.dumps({'CloseGamePC':{'attach':ATTACH}}),'selected_task_id':'dot-close-verified'}
  result={'receipt':str(Path(receipt).resolve()),'instance':instance,'game_day':day(),'maa_version':VERSION,'closed':False,'started_at':now()}
  path=ROOT/'cleanup-endfield-task.json';atomic_json(path,result)
  try:
   check_stop();result['response']=api('/maa/instances/'+instance+'/tasks/start',task_body([task],manifest));deadline=time.monotonic()+90
   while True:
    check_stop();time.sleep(1);s=api('/maa/state')['instances'][instance];result['state']=s
    if not s.get('is_running'):break
    if time.monotonic()>deadline:raise RuntimeError('Close pending; do not force terminate blindly')
   state=s.get('task_run_state',{})
   if state.get('overall_status')!='Succeeded' or state.get('statuses',{}).get('dot-close-verified')!='succeeded':raise RuntimeError('Official close task did not succeed')
   result['status']='awaiting_process_absence_verification'
  except Exception as e:
   result['error']=str(e);result['status']='failed';atomic_json(path,result);raise
  atomic_json(path,result);return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--receipt',type=Path,required=True);p.add_argument('--execute',action='store_true');add_native_transport_argument(p);a=p.parse_args()
 try:
  if a.execute:
   require_native_pc('endfield',a.transport)
   require_execution('endfield')
  if a.execute:r=close(a.receipt)
  else:
   receipt=validate_receipt(a.receipt);r={'mode':'plan_only','instance':receipt['instance'],'CloseGamePC':ATTACH}
  print(json.dumps(r,ensure_ascii=False));return 0
 except Exception as e:print(json.dumps({'status':'blocked','error':str(e)},ensure_ascii=False));return 2
if __name__=='__main__':raise SystemExit(main())
