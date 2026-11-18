"""Read-only, receipt-bound daily coverage audit. Never imports game adapters.

This verifies recorded evidence, not current game screens or live process absence.
Missing/uncertain records require review; they never authorize replay.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TZ = dt.timezone(dt.timedelta(hours=8))
LEGACY_DAY = '2026-11-17'

def game_day():
    return (dt.datetime.now(TZ) - dt.timedelta(hours=4)).date().isoformat()

def contained(value, root):
    if not isinstance(value, (str, Path)) or not str(value):
        raise ValueError('missing exact receipt reference')
    p = Path(value)
    if not p.is_absolute(): p = root / p
    p = p.resolve(); p.relative_to(root.resolve())
    return p

def read(value, root):
    p = contained(value, root)
    data = json.loads(p.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict): raise ValueError('receipt must be an object')
    return p, data

def identity(r, game, day, *, bound_game=None):
    actual_game = r.get('game', bound_game)
    if actual_game != game: raise ValueError('wrong or absent game identity')
    dates = [r[k] for k in ('day', 'game_day') if k in r]
    if dates:
        if any(d != day for d in dates): raise ValueError('cross-day receipt')
    else:
        stamp = next((r.get(k) for k in ('checked_at', 'started_at', 'verified_at') if r.get(k)), None)
        if not stamp: raise ValueError('absent game-day identity')
        t = dt.datetime.fromisoformat(stamp)
        if t.tzinfo is None: raise ValueError('timestamp has no timezone')
        if (t.astimezone(TZ)-dt.timedelta(hours=4)).date().isoformat() != day:
            raise ValueError('cross-day timestamp')

def evidence(r, root):
    """Validate every declared PNG path and SHA, without interpreting pixels."""
    found = []
    def walk(v):
        if isinstance(v, dict):
            if isinstance(v.get('path'), str) and v['path'].lower().endswith('.png'):
                p = check(v['path'])
                if v.get('sha256') and hashlib.sha256(p.read_bytes()).hexdigest() != v['sha256']:
                    raise ValueError('screenshot hash mismatch')
            for k, child in v.items():
                if k not in ('path',): walk(child)
        elif isinstance(v, list):
            for child in v: walk(child)
        elif isinstance(v, str) and v.lower().endswith('.png'):
            check(v)
    def check(value):
        p = Path(value)
        # Older GF2 attestations use evidence basenames, never arbitrary searches.
        if not p.is_absolute() and len(p.parts) == 1: p = root/'evidence'/p
        p = contained(p, root)
        if not p.is_file() or not p.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('missing or invalid PNG evidence')
        found.append(str(p)); return p
    for k in ('before', 'after', 'evidence', 'verification', 'verification_evidence', 'reward_evidence'):
        if k in r: walk(r[k])
    return sorted(set(found))

def condition(r):
    status = str(r.get('status', '')).lower()
    if r.get('state', {}).get('is_running') is True or status in ('running','submitting','planned','preflight'):
        return 'running_or_uncertain'
    if r.get('error') or r.get('safety_errors') or any(w in status for w in ('failed','blocked','unknown','uncertain')):
        return 'failed_or_uncertain'
    if any(t.get('status') not in ('maa_completed','completed','complete','verified') for t in r.get('tasks', [])):
        return 'failed_or_uncertain'
    return None

def validate_v2(path, r, root):
    """Hash/callback/worker binding only; never imports the execution adapter."""
    import ark_v2_evidence as proof
    folder=path.parent
    if r.get('schema')!=2 or contained(r.get('run_dir'),root)!=folder:
        raise ValueError('v2 schema/run binding mismatch')
    cfg,c=read(folder/'config.json',root)
    if proof.sha(cfg)!=r.get('config_sha256') or c.get('supplement_policy')!='approved-ark-operations-v2':
        raise ValueError('v2 config binding mismatch')
    if [t.get('type') for t in r.get('tasks',[])]!=['Recruit','Infrast','Mall','Award']:
        raise ValueError('v2 task sequence mismatch')
    for i,item in enumerate(r['tasks']):
        stage=contained(folder/(str(i)+'-'+item['type']),root)
        taskpath,task=read(stage/'task.json',root)
        if item.get('status')!='complete' or proof.sha(taskpath)!=item.get('task_sha256') or task.get('type')!=item['type']:
            raise ValueError('v2 task binding/status mismatch')
        if not isinstance(item.get('evidence'),dict):raise ValueError('v2 callback proof missing')
        # Resolve all validator inputs within the audit root, including symlinks.
        for name in ('result.json','events.jsonl','worker-state.json'):contained(stage/name,root)
        proof.validate(stage,cfg,task,c['expected_version'],item['evidence'])
        _,worker=read(stage/'worker-state.json',root)
        if worker.get('status')!='complete' or worker.get('evidence')!=item['evidence']:
            raise ValueError('v2 worker receipt mismatch')

def audit(day=None, root=ROOT, state=None):
    root = Path(root).resolve(); day = day or game_day()
    dt.date.fromisoformat(day)
    if state is None:
        path = root/'state'/f'daily-{day}.json'
        state = read(path, root)[1] if path.exists() else {'day':day,'games':{}}
    if state.get('day') != day: raise ValueError('coordinator day mismatch')
    games = state.get('games', {}); rows = []
    def stage(name, game, ref, predicate, *, bound_game=None, require_evidence=True, phase=None):
        row = {'stage':name, 'game':game, 'status':'review_required', 'no_replay':True}
        rows.append(row)
        try:
            p, r = read(ref, root); row['receipt'] = str(p)
            row['receipt_sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()
            identity(r, game, day, bound_game=bound_game)
            if r.get('plan_version')=='approved-ark-operations-v2':validate_v2(p,r,root)
            if phase is not None and r.get('phase') != phase: raise ValueError('wrong task phase')
            bad = condition(r)
            if bad: row['status']=bad; row['reason']='record does not establish terminal success'; return r
            ev = evidence(r, root)
            if require_evidence and not ev: raise ValueError('no explicit screenshot evidence')
            row['evidence'] = ev
            if not predicate(r): raise ValueError('required completion/verification fields absent')
            row['status']='recorded_verified'; row['no_replay']=True
            return r
        except (OSError, ValueError, TypeError, KeyError) as e:
            row['reason']=str(e); return None
    def ledger_ref(filename):
        p = root/'state'/filename
        if not p.exists(): return None
        _, r = read(p, root)
        target = r.get('run_dir', r.get('run'))
        return contained(target, root)/'summary.json'
    def choose(link, filename):
        # A coordinator link must equal the exact attempt target when both exist.
        try:
            expected = ledger_ref(filename)
            if link and expected and contained(link, root) != expected:
                raise ValueError('coordinator reference differs from attempt ledger')
            return link or expected
        except (OSError, ValueError, TypeError) as e:
            return {'invalid_reference':str(e)}
    def all_tasks(types):
        return lambda r: [t.get('type') for t in r.get('tasks', [])] == types and r.get('daily_reward_verified') is True and r.get('verified') is True
    ark=games.get('arknights', {})
    stage('arknights.base', 'arknights', ark.get('receipt') or root/'state'/f'arknights-{day}.json',
          lambda r: any(t.get('type')=='Fight' for t in r.get('tasks', [])) and bool(r.get('verified_at')))
    ops_ref=choose(ark.get('operations_receipt'),f'arknights-{day}.operations.attempt.json')
    ops=stage('arknights.operations','arknights',ops_ref,all_tasks(['Recruit','Infrast','Mall','Award']))
    if ops and ops.get('plan_version') != 'approved-ark-operations-v2':
        if day == LEGACY_DAY:
            acc=choose(ark.get('acceleration_receipt'),f'arknights-{day}.accelerated-recovery-predll.attempt.json')
            stage('arknights.authorized_acceleration','arknights',acc,all_tasks(['Recruit','Infrast','Award']))
        else:
            rows.append({'stage':'arknights.authorized_acceleration','game':'arknights','status':'review_required','reason':'non-v2 operations do not cover current authorization','no_replay':True})
    close_ref=ark.get('cleanup_receipt') or (ark.get('acceleration_receipt') if day==LEGACY_DAY and ark.get('acceleration_receipt') else ops_ref)
    stage('arknights.cleanup','arknights',close_ref,lambda r: r.get('game_closed') is True and r.get('maa_closed') is True,require_evidence=False)

    gf=games.get('gf2', {})
    stage('gf2.daily_and_battle','gf2',gf.get('receipt'),lambda r: r.get('daily_reward_verified') is True and r.get('daily_activity',0)>=r.get('daily_goal',80))
    supp=root/'state'/f'gf2-{day}.supplemental.attempt.json'
    bound=None
    try:
        _, sr=read(supp,root); _, summary=read(contained(sr.get('run'),root)/'summary.json',root)
        if summary.get('game')=='gf2' and contained(summary.get('run'),root)==contained(sr.get('run'),root): bound='gf2'
    except (OSError, ValueError, TypeError): pass
    stage('gf2.cooking_tea_watering','gf2',supp,lambda r: all(r.get(k) is True for k in ('cooking_completed','tea_completed','watering_completed','partial_verified')),bound_game=bound)
    stage('gf2.breakthrough','gf2',choose(gf.get('breakthrough_receipt'),f'gf2-{day}.breakthrough.attempt.json'),lambda r:r.get('verified') is True and r.get('highest_sweepable_breakthrough_verified') is True and r.get('natural_or_levelup_stamina_only') is True)
    stage('gf2.cleanup','gf2',gf.get('cleanup_receipt') or gf.get('receipt'),lambda r: r.get('game_closed') is True and r.get('maa_closed') is True,require_evidence=False)

    end=games.get('endfield',{}); regional=end.get('regional_supplement',{})
    stage('endfield.daily','endfield',choose(end.get('receipt'),f'endfield-{day}-daily.attempt.json'),lambda r:r.get('daily_reward_verified') is True and r.get('activity')==100,phase='daily')
    for name, filename, phase in (
        ('environment_monitoring',f'endfield-regional-{day}-environment-monitoring.attempt.json','environment-monitoring'),
        ('stock_sell',f'endfield-stock-{day}-sell.recovery-pretrade.attempt.json' if (root/'state'/f'endfield-stock-{day}-sell.recovery-pretrade.attempt.json').exists() else f'endfield-stock-{day}-sell.attempt.json','sell'),
        ('stock_buy',f'endfield-stock-{day}-buy.attempt.json','buy')):
        stage('endfield.'+name,'endfield',choose(regional.get(name,{}).get('receipt'),filename),lambda r:r.get('verified') is True and r.get('automation_succeeded') is True,phase=phase)
    cleanup_ref=regional.get('cleanup') or end.get('cleanup_receipt')
    bound=None
    try:
        _, cr=read(cleanup_ref,root); _, er=read(regional.get('environment_monitoring',{}).get('receipt'),root)
        if er.get('game')=='endfield' and cr.get('instance') and cr.get('instance')==er.get('instance'): bound='endfield'
    except (OSError, ValueError, TypeError): pass
    stage('endfield.cleanup','endfield',cleanup_ref,lambda r:r.get('game_closed') is True and r.get('maa_closed') is True,require_evidence=False,bound_game=bound)
    if day >= '2026-11-19':
        from endfield_extra_audit import audit as extra_audit
        rows.extend(extra_audit(root,day)['stages'])
    pending=[r['stage'] for r in rows if r['status']!='recorded_verified']
    return {'schema':1,'game_day':day,'mode':'read_only','all_required_stages_recorded_verified':not pending,
            'stages':rows,'blocked_stages':pending,'next_review':pending[0] if pending else None,
            'limits':['No game/API/ADB/process calls; recorded evidence only, not live state.',
                      'Visual labels and process-absence attestations remain supervised; do not auto-replay.',
                      'DeliveryJobs is not Stock Redistribution and never satisfies stock sell/buy.']}

def audited_next(state, root=ROOT):
    result=audit(state['day'],root,state)
    return ({'action':'report_complete','day':state['day'],'basis':'all_required_receipts_recorded_verified'} if result['all_required_stages_recorded_verified'] else
            {'action':'review_required_stages_do_not_replay','day':state['day'],'next_review':result['next_review'],'blocked_stages':result['blocked_stages']}),result

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--day');a=p.parse_args(argv)
    try: print(json.dumps(audit(a.day),ensure_ascii=False,indent=2));return 0
    except (OSError,ValueError,TypeError) as e: print(json.dumps({'status':'review_required','error':str(e),'no_replay':True}));return 2

if __name__=='__main__': raise SystemExit(main())
