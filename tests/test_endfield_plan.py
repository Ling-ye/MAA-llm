import json,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1] / 'scripts'
class EndfieldPlanTests(unittest.TestCase):
 def plan(self,*args):return json.loads(subprocess.check_output([sys.executable,str(ROOT/'endfield_safe.py'),*args],encoding='utf8'))
 def test_default_no_execution(self):self.assertEqual([x['entry'] for x in self.plan()['tasks']],['DailyRewardStart'])
 def test_no_upgrade_or_crafting(self):
  o=json.loads(self.plan()['tasks'][0]['pipeline_override'])
  for n in ['DailyTaskUpgradeWeapon','DailyTaskCreation','DailyTaskAssemble','DailyTaskLevelUpOperator']:self.assertIs(o[n]['enabled'],False)
 def test_maintenance_is_white_list(self):
  tasks=self.plan('--phase','safe-maintenance')['tasks']
  self.assertEqual([x['entry'] for x in tasks],['VisitFriendsMain','DijiangRewards','DailyRewardStart'])
  o=json.loads(tasks[1]['pipeline_override'])
  for n in ['RecoveryEmotionMain','ReceptionRoomMain','MFGCabinMain','GrowthChamberMain']:self.assertIs(o[n]['enabled'],False)
 def test_inventory_safe_defaults(self):
  p=self.plan('--phase','inventory');self.assertEqual(p['selected_options']['ProtocolSpaceMode'],'TargetInventory')
  self.assertEqual(p['selected_options']['ProtocolSpaceUseSpMedication'],'EndTask')
  self.assertEqual(p['selected_options']['ProtocolSpaceObtainModeClaim'],'ObtainScaling1')
  self.assertEqual(p['targets']['SupplyPlanLimit_T_CREDS'],'3580000')
  merged={}
  for patch in json.loads(p['tasks'][0]['pipeline_override']):
   for k,v in patch.items():merged.setdefault(k,{}).update(v)
  for n in ['ProtocolSpacePopupSanityLowUseSpMedicationPrepare','ProtocolSpaceRewardClaimSuccessSanityLowUseSpMedicationPrepare','ProtocolSpaceRewardClaimRestoreSanityUseMedication','ProtocolSpaceRewardUsePermit']:
   self.assertFalse(merged[n]['enabled'])
if __name__=='__main__':unittest.main()
