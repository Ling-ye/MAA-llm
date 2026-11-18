"""Read-only evidence validation; no game or DLL imports."""

import hashlib,json

from pathlib import Path



def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def read(p):return json.loads(Path(p).read_text(encoding='utf8'))

def validate(folder,config,task,expected_version,receipt=None):

 folder=Path(folder);result=read(folder/'result.json')

 if result.get('ok') is not True or result.get('version')!=expected_version or result.get('task')!=task['type']:raise ValueError('Result identity/version/success mismatch')

 if read(folder/'task.json')!=task:raise ValueError('Task differs from fixed plan')

 events=[json.loads(x) for x in (folder/'events.jsonl').read_text(encoding='utf8').splitlines() if x.strip()]

 if any(e.get('msg') in (0,1,10000,10004) for e in events):raise ValueError('Fatal task event')

 starts=[(i,e['details']) for i,e in enumerate(events) if e.get('msg')==10001]

 ends=[(i,e['details']) for i,e in enumerate(events) if e.get('msg')==10002]

 if len(starts)!=1 or len(ends)!=1:raise ValueError('Expected exactly one started/completed chain')

 si,sd=starts[0];ei,ed=ends[0]

 if si>=ei or sd.get('taskchain')!=task['type'] or ed.get('taskchain')!=task['type'] or type(sd.get('taskid')) is not int or sd['taskid']<=0 or sd.get('taskid')!=ed.get('taskid') or not sd.get('uuid') or sd.get('uuid')!=ed.get('uuid'):raise ValueError('Task chain binding/order mismatch')

 if not any(i>ei and e.get('msg')==3 and e.get('details',{}).get('finished_tasks')==[sd['taskid']] and e.get('details',{}).get('uuid')==sd['uuid'] for i,e in enumerate(events)):raise ValueError('Missing bound all-tasks-completed event')

 counters={name:sum(1 for e in events if e.get('msg')==20002 and e.get('details',{}).get('details',{}).get('task')==name) for name in ('RecruitNowConfirm','RecruitRefreshConfirm','RecruitConfirm','DroneConfirm','DeliverableOrder')}

 proof={'callback_counts':counters,'count_unit':'completed callback occurrences, not resource quantities','config_sha256':sha(config),'task_sha256':sha(folder/'task.json'),'result_sha256':sha(folder/'result.json'),'events_sha256':sha(folder/'events.jsonl'),'taskid':sd['taskid'],'uuid':sd['uuid'],'version':expected_version,'type':task['type']}

 if receipt is not None and proof!=receipt:raise ValueError('Evidence hashes changed')

 return proof
