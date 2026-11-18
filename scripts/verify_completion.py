"""Read-only full-scope cleanup gate. Never marks a run verified."""
import argparse, json
from pathlib import Path
from daily_audit import audit, identity
from project_paths import configured_path, config_path, install_path
from runner import game_day, read_json, load_config

ROOT=Path(__file__).resolve().parent
def require_coverage(game):
    report=audit(game_day(),ROOT)
    blocked=[r['stage'] for r in report['stages'] if r['game']==game and not r['stage'].endswith('.cleanup') and r['status']!='recorded_verified']
    if blocked: raise RuntimeError('Full game coverage is not verified: '+', '.join(blocked))
    return report

def verify(game,receipt):
    path=Path(receipt).resolve(); path.relative_to((ROOT/'runs').resolve())
    record=read_json(path); identity(record,game,game_day())
    if game=='arknights':
        import ark_operations_v2
        ark_operations_v2.resume_check(path,require_complete=True)
    elif game=='endfield':
        from endfield_common import validate_receipt
        validate_receipt(path)
    elif record.get('verified') is not True or record.get('daily_reward_verified') is not True:
        raise RuntimeError('GF2 reward verification missing')
    require_coverage(game)
    if game=='arknights':
        c=load_config(config_path('arknights.json'))
        paths={'game':'','maa':str(Path(c['maa_dir']).resolve()/'MAA.exe'),'adb':c['adb_path'],'mumu_cli':c['mumu_cli'],'serial':c['serial'],'vm_index':c['vm_index']}
    else:
        paths={'game':str(configured_path('gf2_game' if game=='gf2' else 'endfield_game')),
               'maa':str(install_path(game)/('MaaGF2Exilium.exe' if game=='gf2' else 'MaaEnd.exe')),
               'agent':str(install_path('gf2')/'agent'/'main.py')}
    return {'verified_complete':True,'game':game,'day':game_day(),'paths':paths}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--game',choices=['arknights','gf2','endfield'],required=True);p.add_argument('--receipt',required=True);a=p.parse_args()
    try: print(json.dumps(verify(a.game,a.receipt),ensure_ascii=False))
    except Exception as e: print(json.dumps({'blocked':str(e)}));raise SystemExit(2)
