import contextlib
import datetime as dt
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import runner

class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.c = runner.read_json(Path(__file__).resolve().parent / "safe-config.json")
    def test_defaults_not_ready(self):
        self.assertIs(self.c["ready"], False)
    def test_plan_no_sdk_or_process(self):
        with patch.object(runner.subprocess, "run", side_effect=AssertionError("must not execute")):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runner.run(type("Args", (), {"config": Path(__file__).resolve().parent / "safe-config.json", "execute": False})()), 0)
    def test_execute_readiness_gate(self):
        with self.assertRaisesRegex(RuntimeError, "Not ready"):
            runner.run(type("Args", (), {"config": Path(__file__).resolve().parent / "safe-config.json", "execute": True})())
    def test_fight_requires_stage(self):
        self.c["fight"]["enabled"] = True
        with self.assertRaises(ValueError): runner.make_plan(self.c)
    def test_fight_forces_zero_spending(self):
        self.c["fight"] = {"enabled": True, "stage": "TL-9", "times": 10, "stone": 999, "medicine": 999}
        f = runner.make_plan(self.c)[1]["params"]
        self.assertEqual(f["stone"], 0)
        self.assertEqual(f["medicine"], 0)
        self.assertFalse(f["report_to_penguin"])
    def test_recruit_preserves_rare_tags(self):
        self.c["recruit"]["enabled"] = True
        with self.assertRaisesRegex(ValueError, "ark_operations_v2"):
            runner.make_plan(self.c)
    def test_no_headhunt_reward(self):
        self.assertFalse(runner.make_plan(self.c)[-1]["params"]["recruit"])
    def test_unknown_game_fails_closed(self):
        self.c["game"] = "endfield"
        with self.assertRaises(ValueError): runner.make_plan(self.c)
    def test_remote_adb_rejected(self):
        self.c["serial"] = "192.168.1.10:5555"
        with self.assertRaises(ValueError): runner.make_plan(self.c)
    def test_attempt_limit(self):
        self.c["fight"] = {"enabled": True, "stage": "TL-9", "times": 1000}
        with self.assertRaises(ValueError): runner.make_plan(self.c)
    def test_reset_boundary(self):
        self.assertEqual(runner.game_day(dt.datetime(2026,11,16,3,59,tzinfo=runner.TZ)), "2026-11-15")
        self.assertEqual(runner.game_day(dt.datetime(2026,11,16,4,0,tzinfo=runner.TZ)), "2026-11-16")
    def test_success_requires_positive_callback(self):
        self.assertFalse(runner.task_success([{"msg":3}], "Award"))
        self.assertTrue(runner.task_success([{"msg":10002,"details":{"taskchain":"Award"}}], "Award"))
    def test_failure_overrides_success(self):
        self.assertFalse(runner.task_success([{"msg":10002,"details":{"taskchain":"Award"}},{"msg":10000}], "Award"))
    def test_atomic_json(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as d:
            p=Path(d)/"x.json"
            runner.atomic_json(p, {"中文": True})
            self.assertEqual(runner.read_json(p), {"中文":True})
    def test_concurrent_lock_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as d:
            p=Path(d)/"lock"
            with runner.exclusive_lock(p):
                with self.assertRaises(RuntimeError):
                    with runner.exclusive_lock(p): pass
            with runner.exclusive_lock(p): pass

if __name__ == "__main__": unittest.main()
