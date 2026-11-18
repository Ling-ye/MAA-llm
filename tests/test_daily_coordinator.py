import importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1] / 'scripts';sys.path.insert(0,str(ROOT))
import daily_pipeline as d
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
  with self.assertRaises(ValueError):d.command('gf2')
  with self.assertRaises(ValueError):d.command('endfield')
 def test_path_escape_rejected(self):
  with self.assertRaises(ValueError):d.contained(ROOT.parent/'outside.json')
 def test_prepare_default_no_game_launch(self):
  for g in d.GAMES:
   r=subprocess.run([sys.executable,str(ROOT/'prepare_game.py'),'--game',g],capture_output=True)
   self.assertEqual(r.returncode,0,r.stderr)
   self.assertEqual(json.loads(r.stdout)['mode'],'plan')

 def test_commands_preserve_supervisor_evidence(self):
  ark=d.command('arknights',stage_evidence='stage.png')
  self.assertIn('--stage-reviewed',ark);self.assertEqual(ark[ark.index('--stage-evidence')+1],'stage.png')
  gf=d.command('gf2',hwnd=123,screen_evidence='screen.png')
  self.assertIn('--screen-reviewed',gf);self.assertEqual(gf[gf.index('--screen-evidence')+1],'screen.png')
 def test_missing_stage_evidence_blocks_command(self):
  with self.assertRaises(ValueError):d.command('arknights')

if __name__=='__main__':unittest.main()
