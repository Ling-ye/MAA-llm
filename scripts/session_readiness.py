"""Pure supervisory policy, NOT a desktop/ADB probe or execution authorization.

Inputs must come from fresh independent observations. This module performs no I/O,
never starts a process, and cannot infer home, freshness or liveness from a PNG.
Existing phase/resource/attempt/evidence guards remain mandatory.
"""
from project_paths import select_transport, is_loopback_adb_serial


def assess(game, desktop="unknown", transport="mumu", **observed):
    transport = select_transport(game, transport)
    if desktop not in ("locked", "unlocked", "unknown"):
        raise ValueError("unknown desktop state")
    required = ["authorized", "no_existing_attempt_or_worker", "no_stop", "account_home_reviewed", "fresh_frame_reviewed", "screen_not_blank", "screen_not_frozen", "no_unhandled_prompt"]
    if transport == "mumu":
        required += ["android_started", "adb_device", "official_package_present", "guest_png_valid"]
        expected = observed.get("expected_serial", "")
        serial_ok = is_loopback_adb_serial(expected) and observed.get("actual_serial") == expected
    else:
        required += ["current_window_verified"]
        serial_ok = True
    missing = [key for key in required if observed.get(key) is not True]
    if not serial_ok:
        missing.append("exact_configured_loopback_serial")
    if transport == "mumu" and game == "gf2" and desktop != "unlocked":
        if observed.get("guest_transport_proof_valid") is not True:
            missing.append("current_focused_guest_transport_proof")
    if transport == "pc" and desktop != "unlocked":
        missing.append("interactive_unlocked_desktop")
    return {"game": game, "transport": transport, "ready_for_stage_review": not missing, "missing": missing, "game_action_performed": False}
