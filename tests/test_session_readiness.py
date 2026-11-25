import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from session_readiness import assess


class SessionReadinessTests(unittest.TestCase):
    def observations(self):
        keys = "authorized no_existing_attempt_or_worker no_stop account_home_reviewed fresh_frame_reviewed screen_not_blank screen_not_frozen no_unhandled_prompt android_started adb_device official_package_present guest_png_valid current_window_verified".split()
        return dict.fromkeys(keys, True) | {"expected_serial": "127.0.0.1:16384", "actual_serial": "127.0.0.1:16384"}

    def test_ark_uses_guest_not_host_desktop(self):
        for desktop in ("locked", "unknown", "unlocked"):
            for game in ("arknights", "gf2", "endfield"):
                with self.subTest(desktop=desktop, game=game):
                    result = assess(game, desktop, **(self.observations() | {"current_window_verified": False, "guest_transport_proof_valid": True}))
                    self.assertEqual(result["transport"], "mumu")
                    self.assertTrue(result["ready_for_stage_review"])

    def test_gf2_locked_or_unknown_requires_verified_guest_proof(self):
        for desktop in ("locked","unknown"):
            result = assess("gf2",desktop,**self.observations())
            self.assertIn("current_focused_guest_transport_proof",result["missing"])
            self.assertTrue(assess("gf2",desktop,guest_transport_proof_valid=True,
                                   **self.observations())["ready_for_stage_review"])

    def test_native_games_fail_closed(self):
        for game in ("gf2", "endfield"):
            for desktop in ("locked", "unknown", "unlocked"):
                self.assertEqual(assess(game, desktop, transport="pc", **self.observations())["ready_for_stage_review"], desktop == "unlocked")

    def test_every_required_observation_is_explicit(self):
        for key in self.observations():
            if key == "current_window_verified":
                continue
            data = self.observations(); data.pop(key)
            with self.subTest(key=key):
                self.assertFalse(assess("arknights", "locked", **data)["ready_for_stage_review"])

    def test_blank_frozen_missing_guest_not_ready(self):
        for key in ("guest_png_valid", "screen_not_blank", "screen_not_frozen", "android_started", "account_home_reviewed", "fresh_frame_reviewed"):
            data = self.observations(); data[key] = False
            self.assertFalse(assess("arknights", "locked", **data)["ready_for_stage_review"])

    def test_wrong_or_non_loopback_serial(self):
        for serial in ("127.0.0.1:5555", "remote:16384", "127.0.0.1:0", "127.0.0.1:99999"):
            data = self.observations(); data["actual_serial"] = serial
            self.assertFalse(assess("arknights", "locked", **data)["ready_for_stage_review"])
            data["expected_serial"] = serial
            if serial != "127.0.0.1:5555":
                self.assertFalse(assess("arknights", "locked", **data)["ready_for_stage_review"])

    def test_cli_return_and_title_are_not_home(self):
        self.assertFalse(assess("arknights", "locked", cli_returncode=0, title_visible=True)["ready_for_stage_review"])

    def test_no_io_even_when_readiness_succeeds(self):
        from unittest.mock import patch
        with patch("builtins.open", side_effect=AssertionError("file I/O")), patch("subprocess.run", side_effect=AssertionError("process")):
            for desktop in ("locked", "unknown", "unlocked"):
                for game in ("arknights", "gf2", "endfield"):
                    self.assertFalse(assess(game, desktop, **self.observations())["game_action_performed"])

    def test_invalid_game_or_state(self):
        with self.assertRaises(ValueError): assess("other")
        with self.assertRaises(ValueError): assess("arknights", "other")

    def test_transport_does_not_fall_back(self):
        with self.assertRaises(ValueError):
            assess("arknights", "unlocked", transport="pc", **self.observations())
        with self.assertRaises(ValueError):
            assess("gf2", "unlocked", transport="auto", **self.observations())
        data = self.observations() | {"expected_serial": None, "actual_serial": None}
        self.assertFalse(assess("gf2", "unlocked", **data)["ready_for_stage_review"])
        self.assertTrue(assess("gf2", "unlocked", transport="pc", **data)["ready_for_stage_review"])
