"""Bounded startup; a request is never treated as login or UAC approval."""
import argparse, json, os, subprocess, time
from pathlib import Path
from project_paths import configured_path, config_path, install_path, require_execution
from runner import read_json, load_config, preflight, call, screenshot, game_day, exclusive_lock
ROOT = Path(__file__).resolve().parent

def processes():
    shell = Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    command = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-CimInstance Win32_Process | Where-Object {$_.Name -in @('GF2_Exilium.exe','Endfield.exe','MaaEnd.exe','Games.exe')} | Select-Object ProcessId,Name,ExecutablePath | ConvertTo-Json -Compress"
    out = call([str(shell), '-NoProfile', '-NonInteractive', '-Command', command], 20).stdout.decode('utf-8-sig').strip()
    result = json.loads(out) if out else []
    return result if isinstance(result, list) else [result]

def targets(game):
    if game == 'gf2': return [('GF2_Exilium.exe', configured_path('gf2_game'))]
    return [('Games.exe', configured_path('endfield_launcher')), ('MaaEnd.exe', install_path('endfield')/'MaaEnd.exe')]

def prepare(game):
    require_execution(game)
    if (ROOT/'STOP').exists(): raise RuntimeError('STOP exists')
    journal = ROOT/'state'/('daily-'+game_day()+'.json')
    if journal.exists() and read_json(journal)['games'][game]['phase'] == 'closed':
        return {'game':game, 'status':'already_closed_today', 'launched':False}
    with exclusive_lock(ROOT/'state'/'pipeline.lock'):
        if game == 'arknights':
            c = load_config(config_path('arknights.json')); preflight(c, True)
            call([c['adb_path'], '-s', c['serial'], 'shell', 'monkey', '-p', 'com.hypergryph.arknights', '-c', 'android.intent.category.LAUNCHER', '1'], 20)
            time.sleep(5); (ROOT/'evidence').mkdir(exist_ok=True)
            screenshot(c, ROOT/'evidence'/'arknights-prepare.png')
            return {'game':game, 'status':'awaiting_home_review', 'tasks_executed':False}
        expected = targets(game); existing = processes(); requests = []
        for name, path in expected:
            if not path.is_file(): raise FileNotFoundError(path)
            candidates = [p for p in existing if p['Name'].casefold() == name.casefold()]
            if any(not p.get('ExecutablePath') or Path(p['ExecutablePath']).resolve() != path.resolve() for p in candidates):
                raise RuntimeError('Cannot bind existing process to configured executable: ' + name)
            if candidates: continue
            try:
                child = subprocess.Popen([str(path)], cwd=path.parent, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                requests.append({'name':name, 'requested_pid':child.pid})
            except OSError as exc:
                if getattr(exc, 'winerror', None) == 740:
                    return {'game':game, 'status':'user_elevation_required', 'target':name, 'launch_requests':requests, 'started_verified':False}
                raise
        after = []
        for _ in range(10):
            after = processes()
            if all(any(p.get('ExecutablePath') and Path(p['ExecutablePath']).resolve() == path.resolve() for p in after) for _,path in expected): break
            time.sleep(1)
        verified = all(any(p.get('ExecutablePath') and Path(p['ExecutablePath']).resolve() == path.resolve() for p in after) for _,path in expected)
        return {'game':game, 'launch_requests':requests, 'target_processes_present':verified,
                'status':'awaiting_process_permission_and_home_review' if verified else 'launch_not_verified',
                'note':'Endfield must start through the official launcher. Blank UI blocks progress; never bypass UAC or launch Endfield.exe directly.'}

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game', choices=['arknights','gf2','endfield'], required=True); p.add_argument('--execute', action='store_true'); a=p.parse_args(argv)
    result = prepare(a.game) if a.execute else {'mode':'plan', 'game':a.game, 'requires':'local paths, authorized execution, fresh login/window review'}
    print(json.dumps(result, ensure_ascii=False)); return 0
if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status':'blocked','error':str(exc)})); raise SystemExit(2)
