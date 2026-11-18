"""Bounded MAA adapter. Default is plan-only; no game or DLL loaded until --execute."""
from __future__ import annotations
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

from project_paths import config_path, require_execution, resolve_user_path
ROOT = Path(__file__).resolve().parent
TZ = dt.timezone(dt.timedelta(hours=8))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_config(path):
    c = read_json(path)
    for key in ("maa_dir", "adb_path", "mumu_cli"):
        if c.get(key): c[key] = str(resolve_user_path(c[key]))
    return c


def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def now():
    return dt.datetime.now(TZ).isoformat(timespec="seconds")


def game_day(value=None):
    # Arknights CN game day resets at 04:00 China time.
    value = value or dt.datetime.now(TZ)
    return (value.astimezone(TZ) - dt.timedelta(hours=4)).date().isoformat()


def bounded_int(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")
    return value


def make_plan(c):
    if c.get("recruit", {}).get("enabled") or c.get("infrast", {}).get("enabled") or c.get("mall", {}).get("shopping"):
        raise ValueError("Recruit/base/shopping must use the single ark_operations_v2 entry")
    if c.get("game") != "arknights":
        raise ValueError("Only arknights adapter is implemented; no generic shell fallbacks")
    if not re.fullmatch(r"127\.0\.0\.1:\d{1,5}", c["serial"]):
        raise ValueError("Only explicit loopback ADB serial is allowed")
    bounded_int(c["vm_index"], 0, 100, "vm_index")
    bounded_int(c["task_timeout_seconds"], 30, 3600, "task timeout")
    plan = [{"type": "StartUp", "params": {"client_type": "Official", "start_game_enabled": True}}]
    f = c.get("fight", {})
    if f.get("enabled"):
        if f.get("stage") != "TL-9":
            raise ValueError("Fight requires an explicit verified stage")
        plan.append({"type": "Fight", "params": {
            "stage": f["stage"], "times": bounded_int(f["times"], 1, 100, "fight times"),
            "medicine": 0, "medicine_expire_days": 0, "stone": 0,
            "series": 1, "client_type": "Official",
            "report_to_penguin": False, "report_to_yituliu": False}})
    r = c.get("recruit", {})
    if r.get("enabled"):
        plan.append({"type": "Recruit", "params": {
            "select": [4], "confirm": [3, 4],
            "times": bounded_int(r["times"], 1, 4, "recruit times"),
            "refresh": False, "expedite": False, "set_time": True,
            "preserve_tags": ["高级资深干员", "资深干员", "支援机械"],
            "report_to_penguin": False, "report_to_yituliu": False}})
    if c.get("infrast", {}).get("enabled"):
        plan.append({"type": "Infrast", "params": {
            "mode": 20000, "facility": ["Mfg", "Trade", "Reception"],
            "drones": "_NotUse", "replenish": False,
            "reception_clue_exchange": False, "reception_send_clue": False}})
    m = c.get("mall", {})
    if m.get("enabled"):
        plan.append({"type": "Mall", "params": {
            "visit_friends": True, "shopping": m.get("shopping") is True,
            "buy_first": ["招聘许可", "龙门币"],
            "blacklist": ["家具零件", "碳"],
            "force_shopping_if_credit_full": False, "credit_fight": False}})
    a = c.get("award", {})
    if a.get("enabled"):
        plan.append({"type": "Award", "params": {
            "award": True, "mail": a.get("mail") is True, "recruit": False,
            "orundum": False, "mining": False, "specialaccess": False,
            "signinevent": False}})
    return plan


@contextlib.contextmanager
def exclusive_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    f = path.open("a+b")
    try:
        if f.tell() == 0:
            f.write(b"0")
            f.flush()
        f.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise RuntimeError("Another daily pipeline holds the lock")
    try:
        yield
    finally:
        f.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def call(argv, timeout=30):
    return subprocess.run(argv, capture_output=True, check=True, timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def screenshot(c, target):
    # Direct binary pipe, no PowerShell encoding corruption; bounded ADB read.
    result = call([c["adb_path"], "-s", c["serial"], "exec-out", "screencap", "-p"], 20)
    if not result.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("ADB did not return PNG")
    Path(target).write_bytes(result.stdout)


def preflight(c, launch):
    for key in ("adb_path", "mumu_cli"):
        if not Path(c[key]).is_file():
            raise FileNotFoundError(c[key])
    if not (Path(c["maa_dir"]) / "MaaCore.dll").is_file():
        raise FileNotFoundError("MaaCore.dll missing")
    data = json.loads(call([c["mumu_cli"], "info", "-v", str(c["vm_index"])]).stdout)
    if not data.get("is_android_started"):
        if not launch:
            raise RuntimeError("Emulator not started; explicit --launch-emulator required")
        call([c["mumu_cli"], "control", "-v", str(c["vm_index"]), "launch"])
        for _ in range(18):
            time.sleep(5)
            data = json.loads(call([c["mumu_cli"], "info", "-v", str(c["vm_index"])]).stdout)
            if data.get("is_android_started"):
                break
        else:
            raise TimeoutError("Emulator boot timeout")
    actual = f'{data.get("adb_host_ip")}:{data.get("adb_port")}'
    if actual != c["serial"]:
        raise RuntimeError(f"ADB serial changed: {actual}; refusing other device")
    call([c["adb_path"], "connect", c["serial"]])
    for _ in range(6):
        try:
            state = call([c["adb_path"], "-s", c["serial"], "get-state"], 5).stdout.strip()
            if state == b"device":
                break
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        time.sleep(2)
    else:
        raise RuntimeError("ADB offline after bounded retry")
    package = call([c["adb_path"], "-s", c["serial"], "shell", "pm", "path", "com.hypergryph.arknights"]).stdout
    if b"package:" not in package:
        raise RuntimeError("Official Arknights package missing")


def task_success(events, task_type):
    return any(e.get("msg") == 10002 and e.get("details", {}).get("taskchain") == task_type for e in events) and not any(e.get("msg") in (0, 1, 10000, 10004) for e in events)


def worker(config, taskfile, directory):
    c = load_config(config)
    plan = make_plan(c)
    task = read_json(taskfile)
    if c.get("ready") is not True or task not in plan:
        raise RuntimeError("Worker readiness or task allowlist rejected")
    require_execution("arknights")
    base = Path(c["maa_dir"])
    directory = Path(directory)
    sys.path.insert(0, str(base / "Python"))
    os.chdir(base)
    from asst.asst import Asst
    from asst.utils import InstanceOptionType
    if not Asst.load(base, user_dir=directory):
        raise RuntimeError("MAA resource load failed")
    events = []
    @Asst.CallBackType
    def callback(msg, details, arg):
        try:
            item = {"time": now(), "msg": msg, "details": json.loads(details.decode("utf-8"))}
            events.append(item)
            with (directory / "events.jsonl").open("a", encoding="utf-8") as out:
                out.write(json.dumps(item, ensure_ascii=False) + "\n")
        except Exception:
            events.append({"msg": 0, "details": {"error": "callback_decode_or_write_failed"}})
    asst = Asst(callback)
    try:
        version = asst.get_version()
        if version != c["expected_version"]:
            raise RuntimeError(f"MAA version mismatch: {version}")
        if not asst.set_instance_option(InstanceOptionType.touch_type, "maatouch"):
            raise RuntimeError("touch setup failed")
        if not asst.connect(c["adb_path"], c["serial"], "General"):
            raise RuntimeError("MAA ADB connect failed")
        if not asst.append_task(task["type"], task["params"]):
            raise RuntimeError("MAA rejected task")
        if not asst.start():
            raise RuntimeError("MAA failed to start")
        deadline = time.monotonic() + c["task_timeout_seconds"] - 15
        while asst.running():
            if (ROOT / "STOP").exists():
                raise RuntimeError("STOP requested")
            if time.monotonic() > deadline:
                raise TimeoutError("task exceeded time budget")
            if any(e.get("msg") in (0, 1, 10000) for e in events):
                raise RuntimeError("MAA reported task failure")
            time.sleep(.5)
        ok = task_success(events, task["type"])
        atomic_json(directory / "result.json", {"ok": ok, "version": version, "task": task["type"], "at": now()})
        return 0 if ok else 2
    finally:
        asst.stop()


def run(args):
    c = load_config(args.config)
    plan = make_plan(c)
    if not args.execute:
        print(json.dumps({"mode": "plan_only", "game": c["game"], "ready": c.get("ready", False), "tasks": plan}, ensure_ascii=False, indent=2))
        return 0
    if c.get("ready") is not True:
        raise RuntimeError("Not ready: complete login/resources and inspect home screen before enabling config")
    stage_proof = None
    if c.get("fight", {}).get("enabled"):
        if not getattr(args, "stage_reviewed", False):
            raise RuntimeError("Verify TL-9 is open and auto-deployable this game day; --stage-reviewed required")
        from ark_operations_v2 import home_proof
        stage_proof = home_proof(getattr(args, "stage_evidence", None))
    with exclusive_lock(ROOT / "state" / "pipeline.lock"):
        if (ROOT / "STOP").exists():
            raise RuntimeError("STOP file exists; inspect reason before removing it")
        day = game_day()
        journal = ROOT / "state" / f'arknights-{day}.json'
        if journal.exists():
            old = read_json(journal)
            if old.get("status") == "automation_completed_unverified":
                print("Already ran this game day; no repeated actions")
                return 0
            raise RuntimeError(f"Previous attempt exists ({old.get('status')}); review evidence, do not auto-retry side effects")
        run_dir = ROOT / "runs" / (dt.datetime.now(TZ).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
        run_dir.mkdir(parents=True)
        record = {"game": "arknights", "day": day, "started": now(), "status": "running", "run_dir": str(run_dir), "tasks": [], "daily_reward_verified": False}
        record["stage_review"] = stage_proof
        config_snapshot = run_dir / "config.json"
        atomic_json(config_snapshot, c)
        record["config_sha256"] = hashlib.sha256(config_snapshot.read_bytes()).hexdigest()
        atomic_json(journal, record)
        try:
            preflight(c, args.launch_emulator)
            screenshot(c, run_dir / "before.png")
            for i, task in enumerate(plan):
                if (ROOT / "STOP").exists():
                    raise RuntimeError("STOP requested")
                directory = run_dir / f'{i:02}-{task["type"]}'
                directory.mkdir()
                taskfile = directory / "task.json"
                atomic_json(taskfile, task)
                item = {"type": task["type"], "status": "running", "started": now()}
                record["tasks"].append(item)
                atomic_json(journal, record)
                with (directory / "worker.log").open("wb") as log:
                    p = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", "--config", str(config_snapshot), "--taskfile", str(taskfile), "--directory", str(directory)], stdout=log, stderr=subprocess.STDOUT, timeout=c["task_timeout_seconds"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                resultfile = directory / "result.json"
                if p.returncode != 0 or not resultfile.exists() or read_json(resultfile).get("ok") is not True:
                    item["status"] = "failed_or_uncertain"
                    raise RuntimeError(f'{task["type"]} did not positively complete; no automatic replay')
                item.update(status="maa_completed", ended=now())
                screenshot(c, directory / "after.png")
                atomic_json(journal, record)
            record["status"] = "automation_completed_unverified"
            record["note"] = "MAA callbacks completed; human/vision must verify daily reward page. Disabled tasks are not completed."
        except Exception as exc:
            record.update(status="blocked_or_partial", error=str(exc))
            try:
                screenshot(c, run_dir / "blocked.png")
            except Exception as capture_error:
                record["capture_error"] = str(capture_error)
            return 2
        finally:
            record["ended"] = now()
            atomic_json(journal, record)
            atomic_json(run_dir / "summary.json", record)
            print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(config_path("arknights.json")))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--launch-emulator", action="store_true")
    parser.add_argument("--stage-reviewed", action="store_true")
    parser.add_argument("--stage-evidence")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--taskfile", help=argparse.SUPPRESS)
    parser.add_argument("--directory", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.execute: require_execution("arknights")
        sys.exit(worker(args.config, args.taskfile, args.directory) if args.worker else run(args))
    except Exception as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
