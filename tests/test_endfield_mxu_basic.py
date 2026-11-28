import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import endfield_mxu_basic as m


class TestMXUBasic(unittest.TestCase):
    def test_two_allowlisted_tasks_and_disabled_resource_actions(self):
        collect, reward = m.tasks()
        self.assertEqual([collect["entry"], reward["entry"]], ["DijiangRewards", "DailyRewardStart"])
        c, r = map(lambda task: json.loads(task["pipeline_override"]), (collect, reward))
        for key in ("RecoveryEmotionMain","ReceptionRoomMain","MFGCabinMain","GrowthChamberMain",
                    "ReceptionRoomStartExchange","ReceptionRoomSetCluesQuickAdd"):
            self.assertIs(c[key]["enabled"], False)
        for key in ("DailyTaskUpgradeWeapon","DailyTaskCreation","DailyTaskAssemble","DailyTaskLevelUpOperator"):
            self.assertIs(r[key]["enabled"], False)

    def test_no_replay_after_other_or_ambiguous_current_day_attempt(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            state = root / "state"
            state.mkdir()
            (state / "endfield-2026-11-28-rewards.attempt.json.rejected").write_text("{}")
            with self.assertRaises(RuntimeError):
                m.guard(root, "2026-11-28")
            self.assertEqual(m.guard(root, "2026-11-29").parent, state)
            (root / "STOP").touch()
            with self.assertRaises(RuntimeError):
                m.guard(root, "2026-11-29")

    def test_refuses_unknown_release(self):
        with tempfile.TemporaryDirectory() as path:
            p = Path(path)
            (p / "interface.json").write_text('{"version":"v3.4.0"}')
            with self.assertRaisesRegex(RuntimeError, "Unknown MaaEnd"):
                m.validate_app(p)
            (p / "interface.json").write_text('{"version":"v3.3.0"}')
            with self.assertRaisesRegex(RuntimeError, "Unreviewed installed file"):
                m.validate_app(p)

    def test_wrong_task_ids_do_not_pass(self):
        tasks = m.tasks()
        ids = [1001, 1002]
        state = {"is_running": False, "task_run_state": {
            "pending_task_ids": ids, "overall_status": "Succeeded",
            "mappings": {str(i): t["selected_task_id"] for i,t in zip(ids,tasks)},
            "statuses": {t["selected_task_id"]: "succeeded" for t in tasks},
        }}
        self.assertTrue(m.validate_response(state, {"taskIds": ids}, tasks))
        self.assertFalse(m.validate_response(state, {"taskIds": ids[::-1]}, tasks))
        self.assertFalse(m.validate_response(state, {"taskIds": [True, 1002]}, tasks))


    def test_inventory_requires_exact_successful_own_maintenance(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            s = root / "state"; s.mkdir()
            day = "2026-11-28"
            ledger = s / f"endfield-{day}-safe-maintenance.attempt.json"
            run = root / "runs" / "run"; run.mkdir(parents=True)
            ledger.write_text(json.dumps({"run_dir":str(run)}))
            r = {"game":"endfield","phase":m.PHASE,"game_day":day,"maa_version":m.VERSION,
                 "framework_version":m.FRAMEWORK,"automation_succeeded":False,"safety_errors":[]}
            summary = run / "summary.json"
            summary.write_text(json.dumps(r))
            with self.assertRaises(RuntimeError):
                m.guard(root,day,m.INVENTORY)
            r["automation_succeeded"] = True
            summary.write_text(json.dumps(r))
            self.assertEqual(m.guard(root,day,m.INVENTORY).name,f"endfield-{day}-inventory.attempt.json")
            (s / f"endfield-stock-{day}-buy.attempt.json").touch()
            with self.assertRaises(RuntimeError):
                m.guard(root,day,m.INVENTORY)

    def test_combat_removes_stale_nodes_and_turns_off_spending(self):
        from unittest.mock import patch
        old = {"entry":"ProtocolSpaceSchedule","options":{"ProtocolSpaceMode":"TargetInventory",
               "ProtocolSpaceObtainModeClaim":"ObtainScaling1","ProtocolSpaceUseSpMedication":"EndTask"},
               "pipeline_override":json.dumps([{"ProtocolSpaceTouchExitTouchRetry":{"key":70},
                   "ProtocolSpaceTouchExitTouch":{"key":70}}])}
        with patch.object(m, "digest",side_effect=[m.INVENTORY_POLICY_HASH,m.INVENTORY_DEFINITION_HASH]), \
             patch.object(m, "config",return_value=old):
            f, r = m.inventory_tasks(Path("example"),Path("example"))
        parts = json.loads(f["pipeline_override"])
        self.assertFalse(any("ProtocolSpaceTouchExitTouchRetry" in p for p in parts))
        self.assertIs(parts[-1]["ProtocolSpaceRewardUsePermit"]["enabled"],False)
        self.assertIs(parts[-1]["AutoUseSpMedicationInPrepareWithAnchor"]["enabled"],False)
        self.assertIs(json.loads(r["pipeline_override"])["DailyEventRewardSub"]["enabled"],False)
