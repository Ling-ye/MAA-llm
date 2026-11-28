"""Supervised PC maintenance for reviewed MaaEnd releases; never a full-daily claim."""
from __future__ import annotations
import argparse, ctypes, datetime as dt, functools, hashlib, json, os, struct, time, uuid
from pathlib import Path
from endfield_mxu_port import discover, localhost_json, netstat_snapshot

VERSION = "v3.3.0"
FRAMEWORK = "v6.0.0-beta.3"
HASHES = {
    "interface.json": "4b495e38f94440782c1ffeff7fbe7cf87722183ad039982ac7b0aee0d8867b28",
    "resource/pipeline/nodes.json": "53379603f705e525284b7619d9794bc26b1a54e743613bbf1c1f86d194cbe15d",
    "tasks/DijiangRewards.json": "bd58dd4b3a355fd44c4d4c49961d10dab1a099c94697ba10a75e78e28c88d43c",
    "tasks/DailyRewards.json": "4f1564036d2468fd92330b56637f21c42adfe9a02febabb2b39d9f9a2f4acc36",
    "maafw/MaaFramework.dll": "363ce4acc7cf7f72581b0ab14b4f8dc8ffcb4937f363743ab689680931518e66",
    "agent/go-service.exe": "a09b8ee5446dcb0ef35090dd41be1a3822fb29ab7fb8aea64288f8368183cba2",
    "agent/cpp-algo.exe": "d6642976e4dac0f07ef7cd6d666efa8ae1e27fa654c1604e7bf5d9b3905368fe",
}
PHASE = "safe-maintenance"
INVENTORY = "inventory"
INVENTORY_POLICY_HASH = "c507ffd6dc475a55ad9822f484169d230b2d57dc06a07cb5cc194d60465fcd31"
INVENTORY_DEFINITION_HASH = "097ba3c5569923d3f8bea3d9b24341246202da0079bd68a92cf684fe2d927ce9"
PNG = b"\x89PNG\r\n\x1a\n"

def config(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def validate_app(app):
    manifest = config(app / "interface.json")
    if manifest.get("version") != VERSION:
        raise RuntimeError("Unknown MaaEnd build: review before executing")
    for file, expected in HASHES.items():
        if digest(app / file) != expected:
            raise RuntimeError("Unreviewed installed file: " + file)
    if [a.get("child_exec") for a in manifest["agent"]] != ["agent/go-service", "agent/cpp-algo"]:
        raise RuntimeError("Unexpected official agent commands")
    return manifest

def tasks():
    def task(name, entry, disabled, enabled):
        overrides = {k: {"enabled": False} for k in disabled.split()}
        overrides.update({k: {"enabled": True} for k in enabled.split()})
        return {"entry": entry, "pipeline_override": json.dumps(overrides),
                "selected_task_id": "dot-v330-" + name, "task_name": name}
    return [
        task("DijiangRewards", "DijiangRewards",
             "RecoveryEmotionMain ReceptionRoomMain MFGCabinMain GrowthChamberMain "
             "ReceptionRoomStartExchange ReceptionRoomSetCluesQuickAdd",
             "DijiangRewardsFastCollectProduction DijiangRewardsFastCollectClues"),
        task("DailyRewards", "DailyRewardStart",
             "DailyTaskUpgradeWeapon DailyTaskCreation DailyTaskAssemble DailyTaskLevelUpOperator",
             "DailyEmailRewardSub DailyTaskRewardSub DailyClaimDeliveryJobsRewardSub "
             "DailyProtocolPassRewardSub DailyEventRewardSub DailyTaskActivityFullCheck"),
    ]

def inventory_tasks(root, app):
    source = root / "references" / "endfield-target-inventory-request.json"
    if (digest(source) != INVENTORY_POLICY_HASH
        or digest(app / "tasks" / "ProtocolSpace.json") != INVENTORY_DEFINITION_HASH):
        raise RuntimeError("Unreviewed combat configuration or version")
    old = config(source)
    options = old["options"]
    if (old["entry"] != "ProtocolSpaceSchedule" or options["ProtocolSpaceMode"] != "TargetInventory"
        or options["ProtocolSpaceObtainModeClaim"] != "ObtainScaling1"
        or options["ProtocolSpaceUseSpMedication"] != "EndTask"):
        raise RuntimeError("Expected reviewed natural-only single-reward inventory mode")
    obsolete = {"EnterCameraModeKeyUp","EnterCameraModeLongPress","ProtocolSpaceTouchExitTouchRetry"}
    segments = [{key:value for key,value in s.items() if key not in obsolete}
                for s in json.loads(old["pipeline_override"])]
    segments.append({name: {"enabled": False} for name in (
        "ProtocolSpacePopupSanityLowUseSpMedicationPrepare", "ProtocolSpacePopupSanityLowUseSpMedication",
        "ProtocolSpaceRewardClaimSuccessSanityLowUseSpMedicationPrepare",
        "ProtocolSpaceRewardClaimSuccessSanityLowUseSpMedication", "ProtocolSpaceRewardClaimRestoreSanityUseMedication",
        "AutoUseSpMedicationInPrepareWithAnchor", "ProtocolSpaceRewardUsePermit", "ProtocolSpaceRewardFallbackSingle",
    )})
    fight = {"entry": "ProtocolSpaceSchedule", "task_name":"ProtocolSpace",
             "selected_task_id":"dot-v330-inventory", "pipeline_override":json.dumps(segments)}
    reward = tasks()[1]
    reward["selected_task_id"] = "dot-v330-activity-rewards-only"
    opts = json.loads(reward["pipeline_override"])
    for name in ("DailyEmailRewardSub","DailyClaimDeliveryJobsRewardSub","DailyProtocolPassRewardSub","DailyEventRewardSub"):
        opts[name] = {"enabled":False}
    reward["pipeline_override"] = json.dumps(opts)
    return [fight,reward]

def day():
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=4)).date().isoformat()

def guard(root, today, phase=PHASE):
    if (root / "STOP").exists():
        raise RuntimeError("STOP requested")
    files = root / "state"
    if (files / f"endfield-{today}.success.json").exists():
        raise RuntimeError("A verified Endfield daily already exists")
    attempts = {p for stamp in (today, today.replace('-', ''))
                for p in files.glob(f"endfield*{stamp}*.attempt.json*")}
    if phase == INVENTORY:
        allowed = files / f"endfield-{today}-{PHASE}.attempt.json"
        if attempts != {allowed}:
            raise RuntimeError("Need exactly one complete own maintenance phase before combat")
        receipt = Path(config(allowed)["run_dir"]).resolve() / "summary.json"
        receipt.relative_to((root / "runs").resolve())
        r = config(receipt)
        if (r.get("game") != "endfield" or r.get("phase") != PHASE or r.get("game_day") != today
            or r.get("maa_version") != VERSION or r.get("framework_version") != FRAMEWORK
            or r.get("automation_succeeded") is not True or r.get("safety_errors")):
            raise RuntimeError("Prior maintenance failed verification; no automatic combat")
    elif attempts:
        raise RuntimeError("A current-day Endfield phase already exists; no automatic replay")
    return files / f"endfield-{today}-{phase}.attempt.json"

def window_check(hwnd, expected_pid):
    user = ctypes.windll.user32
    user.SetProcessDPIAware()
    h = ctypes.c_void_p(hwnd)
    title, cls = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(256)
    pid = ctypes.c_ulong()
    user.GetWindowThreadProcessId(h, ctypes.byref(pid))
    user.GetWindowTextW(h, title, 256)
    user.GetClassNameW(h, cls, 256)
    from ctypes.wintypes import RECT
    r = RECT()
    if (pid.value != expected_pid or cls.value != "UnityWndClass" or title.value != "Endfield"
        or not user.IsWindowVisible(h) or user.IsIconic(h) or not user.GetClientRect(h, ctypes.byref(r))
        or (r.right, r.bottom) != (1280, 720)):
        raise RuntimeError("Expected visible 1280x720 Endfield window owned by the verified game PID")

def screenshot(api, route, destination):
    sub = "dot-" + uuid.uuid4().hex
    api(route + "/screenshot/subscribe", {"subscriber_id": sub, "interval_ms": 300})
    try:
        time.sleep(1.2)
        img = api(route + "/screenshot", binary=True)
    finally:
        api(route + "/screenshot/unsubscribe", {"subscriber_id": sub})
    if not img.startswith(PNG) or struct.unpack("!II", img[16:24]) != (1280, 720):
        raise RuntimeError("A valid native 1280x720 frame is required")
    destination.write_bytes(img)

def match_world(before, reference):
    from PIL import Image, ImageChops
    if not 0 <= time.time() - reference.stat().st_mtime <= 300:
        raise RuntimeError("Reviewed world frame older than five minutes")
    with Image.open(before) as actual, Image.open(reference) as reviewed:
        if actual.size != (1280, 720) or actual.size != reviewed.size:
            raise RuntimeError("Mismatched world frame size")
        # Compare the solid foreground icons, not the animated translucent key badges.
        for roi in ((181,22,205,49),(224,26,252,50),(273,27,298,50),(927,31,956,53),
                    (976,32,1005,53),(1028,31,1048,53),(1118,30,1147,48),(1218,20,1259,54)):
            def icon(img):
                return img.convert("L").crop(roi).point(lambda y: 255 if y >= 214 else 0)
            a, b = icon(actual), icon(reviewed)
            if b.histogram()[255] < 80 or ImageChops.difference(a,b).histogram()[255] > 18:
                raise RuntimeError("World HUD no longer matches the reviewed open-world frame")

def summary(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)

def validate_response(state, response, submitted):
    run = state.get("task_run_state", {})
    ids = response.get("taskIds", [])
    return (not state.get("is_running") and len(ids) == len(submitted)
            and all(type(i) is int and i > 0 for i in ids) and len(set(ids)) == len(ids)
            and set(run.get("pending_task_ids", [])) == set(ids)
            and run.get("overall_status") == "Succeeded"
            and all(run.get("statuses", {}).get(t["selected_task_id"]) == "succeeded"
                    and run.get("mappings", {}).get(str(i)) == t["selected_task_id"]
                    for i, t in zip(ids, submitted)))

def run(args):
    # Borrow the installed controller's existing ownership lock; never create a parallel ledger.
    import sys
    sys.path.insert(0, str(args.runtime))
    from runner import exclusive_lock
    from endfield_mxu_close import snapshot_process
    today = day()
    phase = args.phase
    selected = inventory_tasks(args.runtime, args.app) if phase == INVENTORY else tasks()
    with exclusive_lock(args.runtime / "state" / "pipeline.lock"):
        ledger = guard(args.runtime, today, phase)
        manifest = validate_app(args.app)
        window_check(args.hwnd, args.game_pid)
        game_process = snapshot_process(args.game_pid)
        settings = config(args.app / "config" / "mxu-MaaEnd.json")["settings"]
        if settings.get("webServerEnabled") is not True:
            raise RuntimeError("MaaEnd's loopback server is disabled")
        peer = discover(netstat_snapshot(), args.maa_pid, int(settings.get("webServerPort", 12701)))
        if peer["framework"] != FRAMEWORK:
            raise RuntimeError("MaaFramework version mismatch")
        api = functools.partial(localhost_json, peer["port"])
        if api("/system/is-elevated").get("elevated") is not True:
            raise RuntimeError("No already-authorized elevated MaaEnd")
        def states():
            return api("/maa/state")["instances"]
        if any(v.get("is_running") for v in states().values()):
            raise RuntimeError("Another MaaEnd task is running")
        run_dir = args.runtime / "runs" / ("endfield-v330-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
        run_dir.mkdir(parents=True)
        instance = "dot-safe-v330-" + uuid.uuid4().hex[:12]
        route = "/maa/instances/" + instance
        status = {"game": "endfield", "game_day": today, "phase": phase, "instance": instance,
                  "maa_version": VERSION, "framework_version": FRAMEWORK, "port": peer["port"],
                  "game_process": game_process, "started": False, "submission_attempted": False, "daily_reward_verified": False,
                  "automation_succeeded": False, "status": "preflight", "run_dir": str(run_dir)}
        out = run_dir / "summary.json"
        summary(out, status)
        log = args.app / "debug" / "go-service.log"
        size = log.stat().st_size if log.is_file() else 0
        def stop_if_requested():
            if (args.runtime / "STOP").exists() or day() != today:
                raise RuntimeError("STOP requested or game day changed")
        try:
            if instance in states():
                raise RuntimeError("Unexpected existing isolated instance")
            api(route, {}, method="PUT")
            api(route + "/connect", {"type": "Win32", "handle": args.hwnd, "screencap_method": 32,
                                      "mouse_method": 1, "keyboard_method": 1})
            api(route + "/resource/load", {"paths": [str(args.app / "resource")]})
            for _ in range(30):
                stop_if_requested()
                s = states()[instance]
                if s.get("connected") and s.get("resource_loaded"):
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Controller or resource not ready")
            screenshot(api, route, run_dir / "before.png")
            match_world(run_dir / "before.png", args.home_evidence)
            stop_if_requested()
            window_check(args.hwnd, args.game_pid)
            if snapshot_process(args.game_pid) != game_process:
                raise RuntimeError("Endfield process changed during preflight")
            if any(v.get("is_running") for v in states().values()):
                raise RuntimeError("Another MaaEnd task became active")
            body = {"tasks": selected, "agent_configs": manifest["agent"], "cwd": str(args.app),
                    "tcp_compat_mode": False, "controller_info": {"name": "Win32-Front", "type": "Win32"},
                    "pi_envs": {"PI_VERSION": VERSION, "PI_CLIENT_MAAFW_VERSION": FRAMEWORK,
                                 "PI_CONTROLLER": json.dumps(manifest["controller"][0]),
                                 "PI_RESOURCE": json.dumps(manifest["resource"][0]), "PI_CLIENT_LANGUAGE": "zh_cn"}}
            summary(run_dir / "request.json", body)
            with ledger.open("x", encoding="utf-8") as f:
                json.dump({"phase": phase, "run_dir": str(run_dir), "status": "submitting"}, f)
            status.update(submission_attempted=True, status="submitting"); summary(out, status)
            response = api(route + "/tasks/start", body)
            status.update(started=True, response=response, status="running"); summary(out, status)
            deadline = time.monotonic() + (2400 if phase == INVENTORY else 900)
            while True:
                stop_if_requested()
                if time.monotonic() > deadline:
                    raise RuntimeError("Task deadline exceeded, no replay")
                s = states()[instance]
                status["state"] = s; summary(out, status)
                if not s.get("is_running"):
                    break
                time.sleep(2)
            screenshot(api, route, run_dir / "after.png")
            new_log = b""
            if log.is_file():
                with log.open("rb") as f:
                    if log.stat().st_size >= size:
                        f.seek(size)
                    new_log = f.read()
            (run_dir / "go-service.log").write_bytes(new_log)
            errors = []
            for line in new_log.splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and (row.get("stop_task") is True or row.get("level") in {"error","fatal","panic"}):
                    errors.append(row)
            status.update(safety_errors=errors)
            status["automation_succeeded"] = validate_response(s,response,selected) and not errors
            status["status"] = "awaiting_visual_verification" if status["automation_succeeded"] else "failed"
        except Exception as e:
            status.update(status="failed", error=str(e))
            if status["submission_attempted"]:
                try:
                    api(route + "/tasks/stop", {})
                except Exception as e:
                    status["stop_error"] = str(e)
        finally:
            try:
                info = states().get(instance)
                if info is not None and not info.get("is_running"):
                    api(route, method="DELETE")
            except Exception as e:
                status["cleanup_error"] = str(e)
            summary(out, status)
            if status["submission_attempted"]:
                summary(ledger, {"phase": phase, "run_dir": str(run_dir), "status": status["status"]})
        return status

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--app", type=Path)
    p.add_argument("--runtime", type=Path)
    for arg in ("hwnd","game-pid","maa-pid"):
        p.add_argument("--"+arg,type=int)
    p.add_argument("--home-evidence", type=Path, help="Fresh locally reviewed open-world screenshot")
    p.add_argument("--phase", choices=[PHASE, INVENTORY, "close"], default=PHASE)
    p.add_argument("--completion-proof", type=Path, help="Hash-bound visually reviewed completion JSON for close")
    p.add_argument("--execute", action="store_true")
    args=p.parse_args()
    if args.phase == "close":
        if not args.execute:
            print(json.dumps({"mode":"plan_only","phase":"close","requires":"full same-day coverage and all 100 activity tiers confirmed","scope":"Endfield.exe graceful exit only"}))
            return 0
        if not all((args.app,args.runtime,args.hwnd,args.game_pid,args.maa_pid,args.completion_proof)):
            p.error("Closing requires app, runtime, exact live PIDs/HWND and completion proof")
        try:
            from endfield_mxu_close import finalize
            print(json.dumps(finalize(args)))
            return 0
        except (OSError, RuntimeError, KeyError, ValueError, TypeError) as e:
            print(json.dumps({"status":"blocked","game_closed":False,"error":str(e)}))
            return 2
    if not args.execute:
        selected = tasks() if args.phase == PHASE else (
            inventory_tasks(args.runtime, args.app) if args.app and args.runtime else ["ProtocolSpace", "activity rewards only"])
        print(json.dumps({"mode":"plan_only","maaend":VERSION,"framework":FRAMEWORK,"phase":args.phase,"tasks":selected}))
        return 0
    if not all((args.app,args.runtime,args.hwnd,args.game_pid,args.maa_pid,args.home_evidence)):
        p.error("Execution requires all live app and reviewed evidence arguments")
    try:
        done=run(args)
        print(json.dumps(done))
        return 0 if done["automation_succeeded"] else 2
    except (OSError, RuntimeError, KeyError, ValueError) as e:
        print(json.dumps({"status":"blocked","error":str(e)}))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
