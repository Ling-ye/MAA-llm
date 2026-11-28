"""Gracefully close only Endfield after a fully verified same-session PC daily."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
import functools
from pathlib import Path
import time

from daily_audit import audit
from endfield_mxu_port import discover, localhost_json, netstat_snapshot


def process_api():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.argtypes = (w.DWORD, w.BOOL, w.DWORD)
    k.OpenProcess.restype = w.HANDLE
    k.QueryFullProcessImageNameW.argtypes = (w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD))
    k.QueryFullProcessImageNameW.restype = w.BOOL
    k.GetProcessTimes.argtypes = (w.HANDLE, *(ctypes.POINTER(w.FILETIME),) * 4)
    k.GetProcessTimes.restype = w.BOOL
    k.WaitForSingleObject.argtypes = (w.HANDLE, w.DWORD)
    k.WaitForSingleObject.restype = w.DWORD
    k.CloseHandle.argtypes = (w.HANDLE,)
    k.CloseHandle.restype = w.BOOL
    return k


def get_process(k, pid):
    if type(pid) is not int or not 0 < pid <= 0xffffffff:
        raise ValueError("Invalid game PID")
    handle = k.OpenProcess(0x101000, False, pid)  # QUERY_LIMITED_INFORMATION | SYNCHRONIZE
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def process_identity(k, handle, pid):
    buffer = ctypes.create_unicode_buffer(32768)
    size = w.DWORD(len(buffer))
    clocks = [w.FILETIME() for _ in range(4)]
    if (not k.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)) or
        not k.GetProcessTimes(handle, *(ctypes.byref(t) for t in clocks))):
        raise ctypes.WinError(ctypes.get_last_error())
    image = Path(buffer.value)
    if image.name.casefold() != "endfield.exe":
        raise RuntimeError("Game PID is not Endfield.exe")
    return {"pid": pid, "created_filetime": (clocks[0].dwHighDateTime << 32) + clocks[0].dwLowDateTime,
            "path": str(image)}


def snapshot_process(pid):
    k = process_api()
    handle = get_process(k, pid)
    try:
        return process_identity(k, handle, pid)
    finally:
        k.CloseHandle(handle)


def completion(root, today, proof_path, *, report=audit, snapshot_time=None):
    import endfield_mxu_basic as m
    root = root.resolve(strict=True)
    proof_path = proof_path.resolve(strict=True)
    proof_path.relative_to(root / "runs")
    proof = m.config(proof_path)
    if (proof.get("game") != "endfield" or proof.get("game_day") != today
        or type(proof.get("activity")) is not int or proof["activity"] != 100
        or proof.get("claimed_tiers") != [20, 40, 60, 80, 100]
        or proof.get("visually_reviewed") is not True):
        raise RuntimeError("Need a visually reviewed same-day 100 activity reward page with all five tiers claimed")
    ledger = m.config(root / "state" / f"endfield-{today}-inventory.attempt.json")
    run = Path(ledger["run_dir"]).resolve(strict=True)
    run.relative_to(root / "runs")
    if ledger.get("phase") != m.INVENTORY or ledger.get("status") != "awaiting_visual_verification":
        raise RuntimeError("Inventory attempt is not in the reviewable terminal state")
    if proof_path.parent != run:
        raise RuntimeError("Completion proof must be in the exact inventory run directory")
    state_path = run / "summary.json"
    r = m.config(state_path)
    if (r.get("game") != "endfield" or r.get("game_day") != today or r.get("phase") != m.INVENTORY
        or r.get("maa_version") != m.VERSION or r.get("framework_version") != m.FRAMEWORK
        or r.get("automation_succeeded") is not True or r.get("status") != "awaiting_visual_verification"
        or r.get("safety_errors") != [] or r.get("error") or r.get("cleanup_error")
        or r.get("state", {}).get("is_running") is not False
        or not m.validate_response(r.get("state", {}), r.get("response", {}),
            [{"selected_task_id":"dot-v330-inventory"}, {"selected_task_id":"dot-v330-activity-rewards-only"}])):
        raise RuntimeError("Terminal inventory receipt or exact callback proof missing")
    if proof.get("summary_sha256") != m.digest(state_path):
        raise RuntimeError("Proof is not bound to the unchanged inventory receipt")
    identity = r.get("game_process")
    if not isinstance(identity, dict) or not identity.get("pid") or not identity.get("created_filetime") or not identity.get("path"):
        raise RuntimeError("Inventory run lacks an exact game process identity")
    if proof.get("game_process") != identity:
        raise RuntimeError("Reward evidence does not identify the same game session")
    shot = (run / proof["screenshot"]).resolve(strict=True)
    if shot.parent != run or shot.suffix.lower() != ".png":
        raise RuntimeError("Expected a PNG from the exact current inventory run")
    stamp = time.time() if snapshot_time is None else snapshot_time
    if not 0 <= stamp - shot.stat().st_mtime <= 300 or proof.get("screenshot_sha256") != m.digest(shot):
        raise RuntimeError("Reward screenshot is stale or changed")
    from PIL import Image
    with Image.open(shot) as image:
        if image.format != "PNG" or image.size != (1280, 720):
            raise RuntimeError("Reward evidence must be a captured 1280x720 PNG")
        image.verify()
    # The independent 100/100 proof above replaces only the legacy PC core receipt.
    rows = [s for s in report(today, root)["stages"] if s["game"] == "endfield"
            and s["stage"] not in {"endfield.daily", "endfield.cleanup"}]
    if not rows or any(row["status"] != "recorded_verified" for row in rows):
        raise RuntimeError("Required Endfield side tasks have not all been separately verified")
    return identity


def request_close(hwnd, identity, *, check_window, timeout_ms=30000):
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.PostMessageW.argtypes = (w.HWND, w.UINT, w.WPARAM, w.LPARAM)
    user.PostMessageW.restype = w.BOOL
    k = process_api()
    handle = get_process(k, identity["pid"])
    try:
        if process_identity(k, handle, identity["pid"]) != identity or k.WaitForSingleObject(handle, 0) != 258:
            raise RuntimeError("Game process changed or already exited")
        check_window(hwnd, identity["pid"])
        if not user.PostMessageW(hwnd, 0x0010, 0, 0):  # WM_CLOSE, never TerminateProcess
            raise ctypes.WinError(ctypes.get_last_error())
        if k.WaitForSingleObject(handle, timeout_ms) != 0:
            raise RuntimeError("Game exit not confirmed; left open, no force kill")
    finally:
        k.CloseHandle(handle)


def finalize(args):
    import endfield_mxu_basic as m
    from runner import exclusive_lock
    root = args.runtime.resolve(strict=True)
    today = m.day()
    with exclusive_lock(root / "state" / "pipeline.lock"):
        if (root / "STOP").exists():
            raise RuntimeError("STOP requested")
        identity = completion(root, today, args.completion_proof)
        if identity["pid"] != args.game_pid:
            raise RuntimeError("Current game PID differs from completion proof")
        m.validate_app(args.app)
        settings = m.config(args.app / "config" / "mxu-MaaEnd.json")["settings"]
        if settings.get("webServerEnabled") is not True:
            raise RuntimeError("MaaEnd idle state cannot be verified")
        peer = discover(netstat_snapshot(), args.maa_pid, int(settings.get("webServerPort", 12701)))
        if peer["framework"] != m.FRAMEWORK:
            raise RuntimeError("MaaFramework version mismatch before cleanup")
        api = functools.partial(localhost_json, peer["port"])
        if any(x.get("is_running") is not False for x in api("/maa/state")["instances"].values()):
            raise RuntimeError("MaaEnd is still running or its state is uncertain")
        if (root / "STOP").exists() or m.day() != today:
            raise RuntimeError("STOP requested or game day changed")
        receipt = root / "state" / f"endfield-{today}-mxu-close.json"
        with receipt.open("x", encoding="utf-8") as out:
            import json
            json.dump({"game":"endfield","game_day":today,"status":"close_requested","game_closed":False}, out)
        result = {"game":"endfield","game_day":today,"status":"unconfirmed","game_closed":False}
        try:
            request_close(args.hwnd, identity, check_window=m.window_check)
            result.update(status="closed", game_closed=True)
        finally:
            m.summary(receipt,result)
        return result
