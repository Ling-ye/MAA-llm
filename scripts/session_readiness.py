"""Pure supervisory policy, NOT a desktop/ADB probe or execution authorization.

Inputs must come from fresh independent observations. This module performs no I/O,
never starts a process, and cannot infer home, freshness or liveness from a PNG.
Existing phase/resource/attempt/evidence guards remain mandatory.
"""
import re


def assess(game, desktop="unknown", **observed):
    if game not in ("arknights", "gf2", "endfield"):
        raise ValueError("unknown game")
    if desktop not in ("locked", "unlocked", "unknown"):
        raise ValueError("unknown desktop state")
    required = ["authorized", "no_existing_attempt_or_worker", "no_stop", "account_home_reviewed", "fresh_frame_reviewed", "screen_not_blank", "screen_not_frozen", "no_unhandled_prompt"]
    if game == "arknights":
        required += ["android_started", "adb_device", "official_package_present", "guest_png_valid"]
        expected = observed.get("expected_serial", "")
        match = re.fullmatch(r"127\.0\.0\.1:(\d{1,5})", expected)
        serial_ok = bool(match and 1 <= int(match[1]) <= 65535 and observed.get("actual_serial") == expected)
    else:
        required += ["current_window_verified"]
        serial_ok = True
    missing = [key for key in required if observed.get(key) is not True]
    if not serial_ok:
        missing.append("exact_configured_loopback_serial")
    if game != "arknights" and desktop != "unlocked":
        missing.append("interactive_unlocked_desktop")
    return {"game": game, "transport": "adb_guest" if game == "arknights" else "desktop", "ready_for_stage_review": not missing, "missing": missing, "game_action_performed": False}
