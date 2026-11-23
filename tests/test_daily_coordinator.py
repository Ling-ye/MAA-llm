import importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1] / 'scripts';sys.path.insert(0,str(ROOT))
import daily_pipeline as d,prepare_game as prep
class CoordinatorTests(unittest.TestCase):
 def test_serial_order(self):
  s=d.new_state('2026-11-17')
  with self.assertRaises(ValueError):d.transition(s,'gf2','prepared',{})
 def test_happy_lifecycle(self):
  s=d.new_state('2026-11-17')
  for g in d.GAMES:
   for event in ['prepared','started','returned','verified','closed']:d.transition(s,g,event,{})
  self.assertEqual(d.next_action(s)['action'],'review_required_stages_do_not_replay')
 def test_no_replay_running(self):
  s=d.new_state('x');d.transition(s,'arknights','prepared',{});d.transition(s,'arknights','started',{})
  with self.assertRaises(ValueError):d.transition(s,'arknights','started',{})
  self.assertIn('do_not_restart',d.next_action(s)['action'])
 def test_blocked_no_reset(self):
  s=d.new_state('x');d.transition(s,'arknights','blocked',{'reason':'login'})
  with self.assertRaises(ValueError):d.transition(s,'arknights','prepared',{})
 def test_callback_not_verification(self):
  self.assertFalse(d.verified_receipt('endfield',{'automation_succeeded':True}))
  self.assertFalse(d.verified_receipt('gf2',{'verified':False,'tasks':[{'status':'maa_completed'}]}))
 def test_partial_endfield_not_complete(self):
  self.assertFalse(d.verified_receipt('endfield',{'daily_reward_verified':True,'activity':40}))
 def test_running_receipt_not_terminal(self):
  self.assertFalse(d.receipt_terminal('arknights',{'status':'running'}))
  self.assertFalse(d.receipt_terminal('gf2',{'tasks':[{'status':'running'}]}))
  self.assertFalse(d.receipt_terminal('endfield',{'automation_succeeded':True,'state':{'is_running':True}}))
 def test_required_runtime(self):
  with self.assertRaises(ValueError):d.command('gf2',transport='pc')
  with self.assertRaises(ValueError):d.command('endfield',transport='pc')
 def test_path_escape_rejected(self):
  with self.assertRaises(ValueError):d.contained(ROOT.parent/'outside.json')
 def test_prepare_default_no_game_launch(self):
  for g in d.GAMES:
   r=subprocess.run([sys.executable,str(ROOT/'prepare_game.py'),'--game',g],capture_output=True)
   self.assertEqual(r.returncode,0,r.stderr)
   self.assertEqual(json.loads(r.stdout)['mode'],'plan')
   self.assertEqual(json.loads(r.stdout)['transport'],'mumu')

 def test_commands_preserve_supervisor_evidence(self):
  ark=d.command('arknights',stage_evidence='stage.png')
  self.assertIn('--stage-reviewed',ark);self.assertEqual(ark[ark.index('--stage-evidence')+1],'stage.png')
  gf=d.command('gf2',hwnd=123,screen_evidence='screen.png',transport='pc')
  self.assertIn('--screen-reviewed',gf);self.assertEqual(gf[gf.index('--screen-evidence')+1],'screen.png')
  self.assertEqual(gf[gf.index('--transport')+1],'pc')
  end=d.command('endfield',instance='dot-safe-test',transport='pc')
  self.assertEqual(end[end.index('--transport')+1],'pc')
 def test_default_never_dispatches_or_prepares_pc(self):
  for game in ('gf2','endfield'):
   with patch.object(d,'install_path',side_effect=AssertionError('native path')),patch.object(prep,'require_execution',side_effect=AssertionError('authorization gate reached')),patch.object(prep,'targets',side_effect=AssertionError('native path')):
    with self.assertRaisesRegex(ValueError,'mumu_daily.py'):
     d.command(game,hwnd=123,instance='dot-safe-test',screen_evidence='screen.png')
    with self.assertRaisesRegex(ValueError,'mumu_daily.py'):prep.prepare(game)
 def test_no_ark_pc(self):
  with self.assertRaisesRegex(ValueError,'only the MuMu transport'):prep.prepare('arknights','pc')
  with self.assertRaisesRegex(ValueError,'only the MuMu transport'):d.command('arknights',transport='pc')
 def test_legacy_native_prepared_record_is_never_reused(self):
  import time
  with tempfile.TemporaryDirectory() as t,patch.object(d,'ROOT',Path(t)),patch.object(d,'require_execution',side_effect=AssertionError('authorization gate reached')),patch.object(d.subprocess,'Popen',side_effect=AssertionError('native spawn')):
   s=d.new_state(d.game_day());s['games']['arknights']['phase']='closed';s['games']['gf2']={'phase':'prepared','prepared_at_epoch':time.time()}
   path=Path(t)/'state'/('daily-'+d.game_day()+'.json');path.parent.mkdir();path.write_text(json.dumps(s))
   with self.assertRaisesRegex(ValueError,'mumu_daily.py'):d.main(['run','--execute'])
   with self.assertRaisesRegex(ValueError,'Prepared transport missing'):d.main(['run','--execute','--transport','pc'])
   self.assertEqual(d.read_json(path),s)
 def test_missing_stage_evidence_blocks_command(self):
  with self.assertRaises(ValueError):d.command('arknights')

if __name__=='__main__':unittest.main()
