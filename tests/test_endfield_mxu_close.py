import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import endfield_mxu_basic as basic
import endfield_mxu_close as close


class EndfieldCloseTest(unittest.TestCase):
    day = "2026-11-28"
    identity = {"pid": 31, "created_filetime": 5, "path": "example/Endfield.exe"}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = self.root / "runs" / "v330"
        self.run.mkdir(parents=True)
        state = self.root / "state"
        state.mkdir()
        (state / f"endfield-{self.day}-inventory.attempt.json").write_text(json.dumps(
            {"phase":"inventory","status":"awaiting_visual_verification","run_dir":str(self.run)}))
        ids = [11, 12]
        names = ["dot-v330-inventory","dot-v330-activity-rewards-only"]
        self.summary = self.run / "summary.json"
        self.summary.write_text(json.dumps(
            {"game":"endfield","phase":"inventory","game_day":self.day,"game_process":self.identity,
             "maa_version":basic.VERSION,"framework_version":basic.FRAMEWORK,"automation_succeeded":True,
             "status":"awaiting_visual_verification","safety_errors":[],"response":{"taskIds":ids},
             "state":{"is_running":False,"task_run_state":{"pending_task_ids":ids,"overall_status":"Succeeded",
             "mappings":dict(zip(map(str,ids),names)),"statuses":dict.fromkeys(names,"succeeded")}}}))
        self.shot = self.run / "after.png"
        Image.new("RGB",(1280,720)).save(self.shot)
        self.proof = self.run / "review.json"
        self.data = {"game":"endfield","game_day":self.day,"visually_reviewed":True,"activity":100,
                     "claimed_tiers":[20,40,60,80,100],"game_process":self.identity,"screenshot":"after.png",
                     "screenshot_sha256":basic.digest(self.shot),"summary_sha256":basic.digest(self.summary)}

    @staticmethod
    def audit(status):
        return lambda *_: {"stages":[
            {"game":"endfield","stage":"endfield.daily","status":"review_required"},
            {"game":"endfield","stage":"endfield.cleanup","status":"review_required"},
            {"game":"endfield","stage":"endfield.stock_sell","status":status}]}

    def verify(self, status="recorded_verified", **kwargs):
        self.proof.write_text(json.dumps(self.data))
        return close.completion(self.root,self.day,self.proof,report=self.audit(status),**kwargs)

    def test_full_completion_returns_bound_process(self):
        self.assertEqual(self.verify(),self.identity)

    def test_activity_60_or_missing_reward_keeps_game_open(self):
        self.data["activity"] = 60
        with self.assertRaisesRegex(RuntimeError,"100 activity"):
            self.verify()
        self.data["activity"] = 100
        self.data["claimed_tiers"] = [20,40,60,80]
        with self.assertRaisesRegex(RuntimeError,"five tiers"):
            self.verify()

    def test_side_tasks_and_screenshot_must_be_verified(self):
        with self.assertRaisesRegex(RuntimeError,"side tasks"):
            self.verify("recorded_limited")
        with self.assertRaisesRegex(RuntimeError,"stale"):
            self.verify(snapshot_time=self.shot.stat().st_mtime+301)
        self.data["screenshot_sha256"] = "0"*64
        with self.assertRaisesRegex(RuntimeError,"changed"):
            self.verify()

    def test_process_identity_and_summary_cannot_be_replaced(self):
        original = self.data["game_process"]
        self.data["game_process"] = {**original,"created_filetime":6}
        with self.assertRaisesRegex(RuntimeError,"same game session"):
            self.verify()
        self.data["game_process"] = original
        self.summary.write_text(self.summary.read_text() + "\n")
        with self.assertRaisesRegex(RuntimeError,"unchanged inventory receipt"):
            self.verify()

    def test_graceful_close_waits_for_exact_process_and_no_kill_fallback(self):
        win, kernel, window = Mock(), Mock(), Mock()
        kernel.WaitForSingleObject.side_effect = [258, 0]
        with patch.object(close.ctypes,"WinDLL",return_value=win,create=True), \
             patch.object(close,"process_api",return_value=kernel), \
             patch.object(close,"get_process",return_value=10), \
             patch.object(close,"process_identity",return_value=self.identity):
            close.request_close(44,self.identity,check_window=window)
        window.assert_called_once_with(44,31)
        win.PostMessageW.assert_called_once_with(44,0x0010,0,0)
        kernel.CloseHandle.assert_called_once_with(10)
        kernel.TerminateProcess.assert_not_called()

    def test_no_close_on_pid_reuse_and_no_kill_on_timeout(self):
        win, kernel, window = Mock(), Mock(), Mock()
        with patch.object(close.ctypes,"WinDLL",return_value=win,create=True), \
             patch.object(close,"process_api",return_value=kernel), \
             patch.object(close,"get_process",return_value=10), \
             patch.object(close,"process_identity",return_value={**self.identity,"created_filetime":9}):
            with self.assertRaisesRegex(RuntimeError,"process changed"):
                close.request_close(44,self.identity,check_window=window)
        win.PostMessageW.assert_not_called()
        kernel.WaitForSingleObject.side_effect = [258,258]
        with patch.object(close.ctypes,"WinDLL",return_value=win,create=True), \
             patch.object(close,"process_api",return_value=kernel), \
             patch.object(close,"get_process",return_value=10), \
             patch.object(close,"process_identity",return_value=self.identity):
            with self.assertRaisesRegex(RuntimeError,"not confirmed"):
                close.request_close(44,self.identity,check_window=window)
        kernel.TerminateProcess.assert_not_called()
