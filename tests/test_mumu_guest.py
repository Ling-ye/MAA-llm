import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import mumu_guest as g


def png(color):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    row = b"\x00" + b"\x00\x01\x02\x04\x05\x06" * 80 + bytes((color, 3, 4, color, 6, 8)) * 80
    return g.PNG + chunk(b"IHDR", struct.pack(">IIBBBBB", 320, 180, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(row * 180)) + chunk(b"IEND", b"")


class GuestCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.cfg = dict(serial="127.0.0.1:5555", vm_index=1, adb_path="adb.exe", mumu_cli="mumu-cli.exe")
        self.package = g.PACKAGES["gf2"]
        self.vm = dict(is_android_started=True, adb_host_ip="127.0.0.1", adb_port=5555)
        self.resumed = self.focus = self.package + "/.MainActivity"
        self.pid = b"47\n"
        self.device = b"device\n"
        self.boot = b"00000000-0000-4000-8000-000000000123\n"
        self.image = png(10)
        self.calls = []
        self.auth = []
        self.inputs = []
        self.post_input = None
        self.on_capture = None

    def command(self, argv):
        self.calls.append(tuple(argv))
        if argv[0] == "mumu-cli.exe":
            self.assertEqual(argv, ["mumu-cli.exe", "info", "-v", "1"])
            return json.dumps(self.vm).encode()
        self.assertEqual(argv[:3], ["adb.exe", "-s", self.cfg["serial"]])
        cmd = argv[3:]
        if cmd == ["get-state"]:
            return self.device
        if cmd == ["shell", "pm", "path", self.package]:
            return b"package:/data/app/fixture/base.apk\n"
        if cmd == ["shell", "dumpsys", "activity", "activities"]:
            return f"topResumedActivity=ActivityRecord{{foo u0 {self.resumed} t2}}\n".encode()
        if cmd == ["shell", "dumpsys", "window", "displays"]:
            return f"mCurrentFocus=Window{{123 u0 {self.focus}}}\n".encode()
        if cmd == ["shell", "pidof", self.package]:
            return self.pid
        if cmd == ["shell", "cat", "/proc/sys/kernel/random/boot_id"]:
            return self.boot
        if cmd == ["exec-out", "screencap", "-p"]:
            if self.on_capture:
                self.on_capture()
            return self.image
        if cmd[:3] in (["shell", "input", "tap"], ["shell", "input", "swipe"]):
            self.inputs.append(tuple(cmd))
            if self.post_input:
                self.post_input()
            return b""
        self.fail(f"Unexpected child command: {cmd!r}")

    def cli(self, *args, game="gf2"):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(g.time, "sleep"):
            code = g.main([*args, "--game", game], root=self.root,
                          load_config=lambda _: self.cfg, command=self.command,
                          authorize=self.auth.append)
        return code, json.loads(output.getvalue())

    def probe(self):
        code, result = self.cli("probe")
        self.assertEqual(code, 0, result)
        self.assertFalse(result["game_action_performed"])
        self.assertEqual(result["frame"]["raw_size"], [320, 180])
        return result

    def tap(self, result, *options):
        return self.cli("tap", "--probe-proof", result["probe"], "--reviewed-frame",
                        "--xy", "11", "22", *options)

    def expect_blocked(self, result, why):
        code, response = result
        self.assertEqual(code, 2, response)
        self.assertEqual(response["status"], "blocked")
        self.assertFalse(response["game_action_performed"])
        self.assertIn(why, response["reason"])

    def test_probe_tap_new_proof_and_one_shot(self):
        before = self.probe()
        self.assertEqual(self.auth, [])
        self.assertEqual(self.inputs, [])
        self.post_input = lambda: setattr(self, "image", png(30))
        code, after = self.tap(before, "--navigation")
        self.assertEqual(code, 0, after)
        self.assertEqual(after["status"], "input_sent_effect_unverified")
        self.assertNotEqual(after["probe"], before["probe"])
        self.assertNotEqual(after["frame"]["sha256"], before["frame"]["sha256"])
        self.assertEqual(self.inputs, [("shell", "input", "tap", "11", "22")])
        self.assertEqual(self.auth, ["gf2"])
        self.image = png(10)
        self.expect_blocked(self.tap(before, "--navigation"), "exists")
        self.assertEqual(len(self.inputs), 1)

    def test_invalid_native_and_stop_avoid_any_command(self):
        self.expect_blocked(self.cli("probe", game="endfield"), "not a MuMu guest")
        (self.root / "STOP").touch()
        self.expect_blocked(self.cli("probe"), "STOP")
        self.assertFalse(self.calls)

    def test_stop_between_capture_and_input(self):
        before = self.probe()
        self.on_capture = lambda: (self.root / "STOP").touch()
        self.expect_blocked(self.tap(before, "--navigation"), "STOP")
        self.assertFalse(self.inputs)

    def test_identity_changes_and_focus_overlay(self):
        self.vm["adb_port"] = 5556
        self.expect_blocked(self.cli("probe"), "different serial")
        self.assertEqual(len(self.calls), 1)
        self.vm["adb_port"] = 5555
        self.device = b"offline\n"
        self.expect_blocked(self.cli("probe"), "not already online")
        self.device = b"device\n"
        self.focus = "com.android.systemui/.GrantPermissionsActivity"
        self.expect_blocked(self.cli("probe"), "both resumed and focused")
        self.focus = self.resumed
        self.on_capture = lambda: setattr(self, "pid", b"48\n")
        self.expect_blocked(self.cli("probe"), "changed during capture")
        self.assertFalse(self.inputs)

    def test_different_resumed_package_and_ambiguous_pid_block(self):
        target = self.resumed
        self.resumed = "com.example.other/.Main"
        self.expect_blocked(self.cli("probe"), "both resumed and focused")
        self.resumed = target
        self.pid = b"47 48\n"
        self.expect_blocked(self.cli("probe"), "process or boot identity ambiguous")
        self.assertFalse(self.inputs)

    def test_forged_changed_and_stale_proof_block_before_input(self):
        before = self.probe()
        receipt = self.root / before["probe"]
        picture = self.root / before["frame"]["path"]
        evidence = picture.read_bytes()
        picture.write_bytes(png(60))
        self.expect_blocked(self.tap(before, "--navigation"), "PNG changed")
        picture.write_bytes(evidence)
        at = dt.datetime.fromisoformat(before["captured_at"]) + dt.timedelta(seconds=g.TTL + 1)
        with patch.object(g, "utcnow", return_value=at):
            self.expect_blocked(self.tap(before, "--navigation"), "expired")
        self.image = png(15)
        self.expect_blocked(self.tap(before, "--navigation"), "state or frame changed")
        self.image = evidence
        body = json.loads(receipt.read_text(encoding="utf-8"))
        body["identity"]["pid"] = 10
        receipt.write_text(json.dumps(body), encoding="utf-8")
        self.expect_blocked(self.tap(before, "--navigation"), "invalid guest probe integrity")
        self.assertFalse(self.inputs)

    def test_requires_exact_scope_and_raw_bounds(self):
        before = self.probe()
        self.expect_blocked(self.tap(before), "choose non-spending navigation")
        self.expect_blocked(self.tap(before, "--item", "tea"), "matching reservation")
        self.expect_blocked(self.cli("swipe", "--probe-proof", before["probe"], "--reviewed-frame",
                                     "--navigation", "--xy", "11", "22", "320", "100", "700"),
                            "outside guest frame")
        self.assertFalse(self.inputs)

    def test_uncertain_post_input_returns_unknown_and_keeps_reservation(self):
        before = self.probe()
        self.post_input = lambda: setattr(self, "focus", "com.android.systemui/.PermissionPrompt")
        code, after = self.tap(before, "--navigation")
        self.assertEqual(code, 3, after)
        self.assertEqual(after["status"], "unknown_after_submission")
        self.assertIsNone(after["game_action_performed"])
        self.assertTrue(after["do_not_retry"])
        self.focus, self.post_input = self.resumed, None
        self.expect_blocked(self.tap(before, "--navigation"), "unconfirmed")
        self.expect_blocked(self.tap(self.probe(), "--navigation"), "unconfirmed")
        self.assertEqual(len(self.inputs), 1)

    def test_uncertain_navigation_needs_new_visual_ack_before_different_step(self):
        before = self.probe()
        self.post_input = lambda: setattr(self, "focus", "com.android.systemui/.PermissionPrompt")
        code, _ = self.tap(before,"--navigation")
        self.assertEqual(code,3)
        self.focus,self.post_input = self.resumed,None
        self.expect_blocked(self.cli("acknowledge","--probe-proof",before["probe"],
                            "--reviewed-frame","--reason","synthetic result reviewed"),"newly verified")
        after = self.probe()
        code,outcome = self.cli("acknowledge","--probe-proof",after["probe"],"--reviewed-frame",
                                "--reason","synthetic result reviewed")
        self.assertEqual(code,0,outcome)
        self.assertFalse(outcome["game_action_performed"])
        self.assertEqual(len(self.inputs),1)
        self.expect_blocked(self.tap(before,"--navigation"),"exists")
        code,_ = self.tap(self.probe(),"--navigation")
        self.assertEqual(code,0)

    def test_exact_navigation_anchor_accepts_outside_change_only(self):
        code,before = self.cli("probe","--anchor","4","4","100","60")
        self.assertEqual(code,0,before)
        self.image = png(30)  # change only far to the right of the reviewed rectangle
        code,after = self.tap(before,"--navigation")
        self.assertEqual(code,0,after)
        self.assertEqual(len(self.inputs),1)
        code,before = self.cli("probe","--anchor","160","4","260","60")
        self.assertEqual(code,0,before)
        self.image = png(31)
        self.expect_blocked(self.cli("tap","--probe-proof",before["probe"],"--reviewed-frame",
                           "--navigation","--xy","200","20"),"navigation anchor changed")
        self.assertEqual(len(self.inputs),1)

    def test_png_checksum_and_format_not_just_signature(self):
        self.image = self.image[:-1] + bytes([self.image[-1] ^ 1])
        self.expect_blocked(self.cli("probe"), "checksum mismatch")
        self.assertFalse(self.inputs)


if __name__ == "__main__":
    unittest.main()
