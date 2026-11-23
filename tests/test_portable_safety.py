import argparse,contextlib,datetime as dt,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import project_paths as paths,runner,gf2_safe,gf2_supplemental,gf2_breakthrough,endfield_regional,policy_integrity,check_repository
class PortableSafetyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def local(self,value):
  p=self.root/'config.local/runtime.json';p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(value))
 def test_new_checkout_execution_disabled(self):
  with patch.object(paths,'PROJECT',self.root):
   with self.assertRaises(RuntimeError):paths.require_execution('gf2')
 def test_disabled_execution_rejected(self):
  self.local({'execution':{'gf2':{'enabled':False,'not_before_game_day':'2000-01-01'}}})
  with patch.object(paths,'PROJECT',self.root):
   with self.assertRaises(RuntimeError):paths.require_execution('gf2')
 def test_future_game_day_rejected(self):
  self.local({'execution':{'gf2':{'enabled':True,'not_before_game_day':'2999-01-01'}}})
  with patch.object(paths,'PROJECT',self.root):
   with self.assertRaises(RuntimeError):paths.require_execution('gf2')
 def test_missing_activation_date_rejected(self):
  self.local({'execution':{'gf2':{'enabled':True}}})
  with patch.object(paths,'PROJECT',self.root):
   with self.assertRaises(ValueError):paths.require_execution('gf2')
 def test_explicit_activation_accepted(self):
  self.local({'execution':{'gf2':{'enabled':True,'not_before_game_day':'2000-01-01'}}})
  with patch.object(paths,'PROJECT',self.root):paths.require_execution('gf2')
 def test_gf2_new_version_stops_before_sdk(self):
  (self.root/'interface.json').write_text('{"version":"v2.8.6"}')
  for mod in (gf2_safe,gf2_supplemental,gf2_breakthrough):
   with self.subTest(module=mod.__name__):
    with self.assertRaisesRegex(mod.Blocked,'version'):mod.execute(self.root,self.root,123)
 def test_ark_fight_requires_current_review(self):
  c=runner.read_json(Path(__file__).parent/'safe-config.json');c.update(ready=True,fight={'enabled':True,'stage':'TL-9','times':1})
  p=self.root/'cfg.json';p.write_text(json.dumps(c))
  with patch.object(runner,'preflight',side_effect=AssertionError('game')):
   with self.assertRaisesRegex(RuntimeError,'stage-reviewed'):runner.run(argparse.Namespace(config=p,execute=True,launch_emulator=False))
 def test_ark_non_tl9_rejected(self):
  c=runner.read_json(Path(__file__).parent/'safe-config.json');c['fight']={'enabled':True,'stage':'OTHER','times':1}
  with self.assertRaises(ValueError):runner.make_plan(c)
 def test_ark_base_shopping_rejected(self):
  c=runner.read_json(Path(__file__).parent/'safe-config.json');c['mall']={'enabled':True,'shopping':True}
  with self.assertRaises(ValueError):runner.make_plan(c)
 def test_delivery_plan_excluded(self):
  with self.assertRaises(ValueError):endfield_regional.make_plan('delivery-jobs')
 def test_environment_plan_without_install(self):
  with patch.object(endfield_regional,'regional_versions',side_effect=AssertionError('installation')):
   self.assertEqual(endfield_regional.make_plan('environment-monitoring')['tasks'][0]['entry'],'EnvironmentMonitoringMain')
 def test_reviewed_policy_tamper_rejected(self):
  p=self.root/'sample.json';p.write_text('{}');(self.root/'hashes.json').write_text(json.dumps({'sample.json':'0'*64}))
  with patch.object(policy_integrity,'POLICIES',self.root):
   with self.assertRaises(ValueError):policy_integrity.read_policy('sample.json')
 def test_all_checked_policies_match(self):
  hashes=json.loads((paths.POLICIES/'hashes.json').read_text(encoding='utf8'))
  for name in hashes:policy_integrity.read_policy(name)
 def test_scanner_reports_rule_not_value(self):
  secret='gh'+'p_'+'a'*36;p=self.root/'sample.txt';p.write_text(secret)
  result=check_repository.inspect([p],self.root)
  self.assertFalse(result['ok']);self.assertNotIn(secret,json.dumps(result))
 def test_scanner_rejects_forced_runtime_file(self):
  p=self.root/'state/attempt.json';p.parent.mkdir();p.write_text('{}')
  self.assertFalse(check_repository.inspect([p],self.root)['ok'])

 def test_relative_installation_resolves_from_project(self):
  self.local({'installations':{'gf2':'tools/gf2/pinned'}})
  with patch.object(paths,'PROJECT',self.root):
   self.assertEqual(paths.install_path('gf2'),(self.root/'tools/gf2/pinned').resolve())
 def test_relative_game_path_resolves_from_project(self):
  self.local({'paths':{'gf2_game':'clients/game.exe'}})
  with patch.object(paths,'PROJECT',self.root):
   self.assertEqual(paths.configured_path('gf2_game'),(self.root/'clients/game.exe').resolve())
 def test_runner_snapshot_normalizes_paths(self):
  p=self.root/'config.json';p.write_text(json.dumps({'maa_dir':'tools/maa','adb_path':'emulator/adb.exe','mumu_cli':'emulator/cli.exe'}))
  with patch.object(paths,'PROJECT',self.root):
   c=runner.load_config(p)
  self.assertEqual(c['adb_path'],str((self.root/'emulator/adb.exe').resolve()))
 def test_empty_config_path_stays_empty(self):
  p=self.root/'config.json';p.write_text('{"adb_path":""}')
  self.assertEqual(runner.load_config(p)['adb_path'],'')
 def test_endfield_cli_gates_before_plan_or_api(self):
  import endfield_regional as regional,endfield_stock as stock
  for module,phase in ((regional,'environment-monitoring'),(stock,'sell')):
   with self.subTest(module=module.__name__),patch.object(sys,'argv',['adapter','--phase',phase,'--execute','--transport','pc']),patch.object(module,'require_execution',side_effect=RuntimeError('disabled')) as gate,patch.object(module,'make_plan',side_effect=AssertionError('plan reached')),contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(module.main(),2);gate.assert_called_once_with('endfield')

 def test_direct_native_cli_execution_requires_pc(self):
  import endfield_safe,endfield_bootstrap,endfield_close,endfield_stock,endfield_extras
  modules = (
    (gf2_safe, ['--execute']), (gf2_supplemental, ['--check-agent']), (gf2_breakthrough, ['--execute']),
    (endfield_safe, ['--execute']), (endfield_bootstrap, ['--execute']),
    (endfield_close, ['--receipt','unused.json','--execute']),
    (endfield_regional, ['--phase','environment-monitoring','--execute']),
    (endfield_stock, ['--phase','sell','--execute']), (endfield_extras, ['--execute']),
  )
  for module,args in modules:
   with self.subTest(module=module.__name__),patch.object(sys,'argv',['adapter',*args]),contextlib.redirect_stdout(io.StringIO()) as out:
    self.assertNotEqual(module.main(),0)
    self.assertIn('mumu_daily.py',out.getvalue())
 def test_scanner_accepts_text_license(self):
  p=self.root/'LICENSE';p.write_text('GNU AFFERO GENERAL PUBLIC LICENSE\nVersion 3, 19 November 2007\n')
  result=check_repository.inspect([p],self.root)
  self.assertTrue(result['ok']);self.assertEqual(result['files'],1)
 def test_license_file_still_scanned_for_secrets(self):
  p=self.root/'LICENSE';p.write_text('gh'+'p_'+'a'*36)
  result=check_repository.inspect([p],self.root)
  self.assertFalse(result['ok'])
  self.assertEqual(result['issues'][0]['rule'],'github_token')

if __name__=='__main__':unittest.main()
