import base64,json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1] / 'scripts'
class CleanupGuardTests(unittest.TestCase):
 def test_worker_classification_offline(self):
  cases=[]
  for script in ['runner','ark_operations','ark_supplemental','gf2_safe','gf2_supplemental','gf2_breakthrough','endfield_safe','endfield_regional','endfield_stock','endfield_bootstrap','endfield_close','prepare_game']:
   for flag,want in [('--execute',True),('',False),('--help',False)]:cases.append({'Name':'python.exe','CommandLine':f'"python.exe" "{ROOT / (script+".py")}" {flag}','want':want})
  for script in ['gf2_input_once','endfield_continue_once','endfield_free_kills_once','reopen_launcher','restore_launcher','start_endfield_native']:cases.append({'Name':'pythonw.exe','CommandLine':f'pythonw.exe "{ROOT / (script+".py")}"','want':True})
  for line,want in [('python.exe ark_operations.py --worker',True),('python.exe -u .\\ark_operations.py --execute',True),('python.exe -m unittest discover --execute',False),('python.exe -c "ark_operations.py --execute"',False),('python.exe verify_maa_skill.py --execute',False),('python.exe tests\\test_ark_operations.py --execute',False),('python.exe C:\\other\\ark_operations.py --execute',False),('python.exe daily_pipeline.py status --execute',False),('python.exe daily_pipeline.py run --execute',True),('python.exe gf2_safe.py --check-agent',False)]:cases.append({'Name':'python.exe','CommandLine':line,'want':want})
  with tempfile.TemporaryDirectory() as temp:
   data_path=Path(temp)/'cases.json';data_path.write_text(json.dumps(cases),encoding='utf-8')
   psq=lambda value: str(value).replace("'","''")
   ps=f"[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); $OutputEncoding=[Console]::OutputEncoding; . '{psq(ROOT / 'game-worker-guard.ps1')}'; $cases=Get-Content -LiteralPath '{psq(data_path)}' -Raw -Encoding UTF8|ConvertFrom-Json; foreach($c in $cases){{$actual=Test-DailyGameWorker -ProcessName $c.Name -CommandLine $c.CommandLine -ProjectRoot '{psq(ROOT)}'; if($actual -ne $c.want){{throw ('Mismatch: '+$c.CommandLine+' got '+$actual)}}}}; 'PASS '+$cases.Count"
   enc=base64.b64encode(ps.encode('utf-16le')).decode();out=subprocess.run([r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',enc],capture_output=True,timeout=30)
  stdout=(out.stdout or b'').decode('utf-8',errors='backslashreplace');stderr=(out.stderr or b'').decode('utf-8',errors='backslashreplace')
  self.assertEqual(out.returncode,0,stdout+stderr);self.assertIn('PASS 52',stdout)
 def test_finish_game_uses_shared_classifier(self):
  s=(ROOT/'finish-game.ps1').read_text(encoding='utf-8-sig');self.assertIn('Test-DailyGameWorker',s);self.assertNotIn('daily-automation.(runner|gf2_safe)',s)
if __name__=='__main__':unittest.main()
