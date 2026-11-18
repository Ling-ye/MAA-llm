import argparse
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import runner

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.c = runner.read_json(Path(__file__).resolve().parent / "safe-config.json")
        self.c["ready"] = True
        self.config = self.root / "config.json"
        runner.atomic_json(self.config, self.c)
        self.args = argparse.Namespace(config=self.config, execute=True, launch_emulator=False)
        self.patchers = [patch.object(runner, "ROOT", self.root),
                         patch.object(runner, "preflight"), patch.object(runner, "screenshot")]
        for p in self.patchers:
            p.start(); self.addCleanup(p.stop)
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__(); self.addCleanup(self.output.__exit__, None, None, None)
    def success(self, argv, **kwargs):
        d = Path(argv[argv.index("--directory") + 1])
        runner.atomic_json(d / "result.json", {"ok": True})
        return subprocess.CompletedProcess(argv, 0)
    def journal(self):
        return runner.read_json(self.root / "state" / f"arknights-{runner.game_day()}.json")
    def test_full_mock_run_is_not_claimed_daily_verified(self):
        with patch.object(runner.subprocess, "run", side_effect=self.success) as calls:
            self.assertEqual(runner.run(self.args), 0)
            self.assertEqual(calls.call_count, 3)
        record = self.journal()
        self.assertEqual(record["status"], "automation_completed_unverified")
        self.assertFalse(record["daily_reward_verified"])
    def test_successful_day_not_repeated(self):
        with patch.object(runner.subprocess, "run", side_effect=self.success) as calls:
            runner.run(self.args)
            calls.reset_mock()
            self.assertEqual(runner.run(self.args), 0)
            calls.assert_not_called()
    def test_nonzero_task_stops_later_tasks_and_replay(self):
        with patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 2)) as calls:
            self.assertEqual(runner.run(self.args), 2)
            self.assertEqual(calls.call_count, 1)
        self.assertEqual(self.journal()["status"], "blocked_or_partial")
        with self.assertRaisesRegex(RuntimeError, "Previous attempt exists"):
            runner.run(self.args)
    def test_timeout_reported_without_retry(self):
        with patch.object(runner.subprocess, "run", side_effect=subprocess.TimeoutExpired("worker", 1200)) as calls:
            self.assertEqual(runner.run(self.args), 2)
            self.assertEqual(calls.call_count, 1)
        self.assertIn("timed out", self.journal()["error"])
    def test_zero_exit_without_result_fails_closed(self):
        with patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
            self.assertEqual(runner.run(self.args), 2)
        self.assertEqual(self.journal()["status"], "blocked_or_partial")
    def test_stop_file_blocks_all_processes(self):
        (self.root / "STOP").touch()
        with patch.object(runner.subprocess, "run") as calls:
            with self.assertRaisesRegex(RuntimeError, "STOP file exists"):
                runner.run(self.args)
            calls.assert_not_called()
    def test_preflight_fail_is_preserved(self):
        with patch.object(runner, "preflight", side_effect=RuntimeError("offline")), patch.object(runner.subprocess, "run") as calls:
            self.assertEqual(runner.run(self.args), 2)
            calls.assert_not_called()
        self.assertEqual(self.journal()["error"], "offline")

if __name__ == "__main__": unittest.main()
