"""Local evidence journal for supervised GF2 actions. Contains NO input/SDK backend."""
import argparse
import contextlib
import copy
import ctypes
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import struct
import uuid

from supervised_evidence import (Blocked, stamp, need, integer, sha, contained, image_size, current_window, pipeline_lock, seal, save, verify_record_evidence)

VERSION = "v2.8.6"
FRESH_SECONDS = 300




def now():
    return dt.datetime.now(dt.timezone.utc)


def game_day(moment=None):
    moment = moment or now()
    if moment.tzinfo is None:
        raise Blocked("timezone-aware time required")
    return (moment.astimezone(dt.timezone(dt.timedelta(hours=8))) - dt.timedelta(hours=4)).date().isoformat()














def checked_frame(root, review, phase, fresh=False, moment=None):
    moment = moment or now()
    need(isinstance(review, dict), "review must be an object")
    need(review.get("schema") == 1 and review.get("game") == "gf2", "wrong review schema/game")
    need(review.get("phase") == phase and review.get("version") == VERSION, "wrong phase/version")
    need(review.get("game_day") == game_day(moment), "wrong game day; do not replay history")
    need(review.get("supervised") is True, "explicit supervisor review required")
    observed = stamp(review.get("reviewed_at"))
    evidence = review.get("evidence", {})
    need(isinstance(evidence, dict), "evidence object required")
    captured = stamp(evidence.get("captured_at"))
    need(game_day(captured) == game_day(moment), "evidence from a different game day")
    need(captured <= observed <= moment, "future/out-of-order timestamps")
    need(isinstance(evidence.get("path"), str) and evidence["path"], "evidence path required")
    path = contained(root, evidence["path"])
    need(path.is_file() and path.stat().st_size <= 16 * 1024 * 1024, "missing/oversized evidence")
    data = path.read_bytes()
    need(evidence.get("sha256") == sha(data), "evidence hash mismatch")
    size = image_size(data)
    need(size in ((1280, 720), (1920, 1080)), "unreviewed evidence dimensions")
    if fresh:
        need((moment - captured).total_seconds() <= FRESH_SECONDS, "stale capture")
        need((moment - observed).total_seconds() <= FRESH_SECONDS, "stale review")
        modified = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)
        need(0 <= (moment - modified).total_seconds() <= FRESH_SECONDS, "stale/future image file")
    result = copy.deepcopy(review)
    result["evidence"].update(path=str(path.relative_to(Path(root).resolve())), image_size=list(size))
    extra = review.get("supporting_evidence", {})
    need(isinstance(extra, dict) and len(extra) <= 8, "invalid supporting evidence")
    result["supporting_evidence"] = {}
    for label, item in extra.items():
        need(isinstance(label, str) and isinstance(item, dict), "invalid evidence role")
        child = {k: v for k, v in review.items() if k != "supporting_evidence"}
        child["evidence"] = item
        result["supporting_evidence"][label] = checked_frame(root, child, phase, fresh=fresh, moment=moment)["evidence"]
    return result




def check_window(review, expected_exe, inspect=current_window):
    need(expected_exe is not None, "--game-exe is required for a fresh reservation")
    expected = Path(expected_exe).resolve()
    need(expected.name.lower() == "gf2_exilium.exe", "wrong game executable")
    actual = inspect()
    declared = review.get("window", {})
    need(isinstance(declared, dict), "window identity required")
    for key in ("hwnd", "pid"):
        need(integer(declared.get(key), 1) and declared[key] == actual.get(key), "window/process switched")
    need(actual.get("foreground") is True and declared.get("foreground") is True, "game is not foreground")
    need("少女前线2" in actual.get("title", "") and "自动化" not in actual.get("title", ""), "wrong game window title")
    need(actual.get("title") == declared.get("title"), "window title changed")
    need(Path(actual["executable"]).resolve() == expected == Path(declared.get("executable", "")).resolve(), "executable mismatch")
    need(actual.get("client_size") == declared.get("client_size") and actual["client_size"] in ([1280, 720], [1920, 1080]), "window dimensions changed")
    if review["evidence"]["image_size"] != actual["client_size"]:
        need(declared.get("scaled_evidence_confirmed") is True, "scaled evidence must be declared")
    return actual


def check_installation(base, pins):
    need(base is not None, "--base is required for a reservation")
    base = Path(base)
    manifest = json.loads((base / "interface.json").read_text(encoding="utf-8-sig"))
    need(manifest.get("version") == VERSION, "unreviewed resource version; old adapters remain unchanged")
    for relative, digest in pins.items():
        need(sha((base / relative).read_bytes()) == digest, "reviewed upstream resource changed")


def ledger_path(root, phase, moment=None, period_key=None):
    key = period_key or game_day(moment)
    need(all(c.isdigit() or c == "-" for c in key), "invalid ledger period key")
    prefix = "gf2-week-" if period_key else "gf2-"
    return contained(root, Path("state") / f"{prefix}{key}.{phase}.attempt.json")




def read_ledger(path, phase, moment=None, period_key=None):
    record = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    need(record.get("integrity_sha256") == seal(record)["integrity_sha256"], "ledger integrity mismatch")
    need(record.get("schema") == 1 and record.get("game") == "gf2"
         and record.get("phase") == phase, "ledger binding mismatch")
    if period_key:
        need(record.get("period_key") == period_key, "wrong weekly period")
    else:
        need(record.get("game_day") == game_day(moment), "wrong ledger game day")
    return record






def status(root, policy):
    p = ledger_path(root, policy["phase"], period_key=policy.get("period_key"))
    if not p.exists():
        index = p.with_suffix(".observation.json")
        if index.exists():
            link = json.loads(index.read_text(encoding="utf8"))
            need(link.get("integrity_sha256") == seal(link)["integrity_sha256"], "observation index tampered")
            need(link.get("game") == "gf2" and link.get("phase") == policy["phase"]
                 and link.get("period_key") == policy.get("period_key"), "observation index scope mismatch")
            if link.get("game_day") == game_day():
                observation = contained(root, link["observation"])
                need(sha(observation.read_bytes()) == link["sha256"], "observation receipt changed")
                record = read_ledger(observation, policy["phase"], period_key=policy.get("period_key"))
                verify_record_evidence(root, record)
                return record
        return {"status": "not_recorded", "game_day": game_day(), "replay_safe": False,
                "note": "An empty local ledger does not prove the game action is available."}
    record = read_ledger(p, policy["phase"], period_key=policy.get("period_key"))
    verify_record_evidence(root, record)
    return record




def record_action(root, policy, action, review=None, base=None, game_exe=None,
                  reason=None, moment=None, inspect_window=current_window, step=None):
    """Journal only. No click, key, navigation, task submission or game closure."""
    moment = moment or now()
    root = Path(root).resolve()
    phase = policy["phase"]
    period_key = policy.get("period_key")
    path = ledger_path(root, phase, moment, period_key)
    if "action_guard" in policy:
        policy["action_guard"](action, moment)
    if action == "reserve":
        need(not (root / "STOP").exists(), "STOP exists")
        check_installation(base, policy["pins"])
    with pipeline_lock(root):
        updates = ("verify", "mark-unknown", "record-step")
        if action in updates:
            need(path.exists(), "no original reservation")
            record = read_ledger(path, phase, moment, period_key)
            verify_record_evidence(root, record)
            need(record["status"] in ("manual_submission_reserved", "deployment_recorded", "in_progress_recorded"),
                 "terminal/unknown attempt cannot be replayed or overwritten")
        else:
            need(not path.exists(), "attempt already exists for this day/week and scope; no replay")
            record = {"schema": 1, "game": "gf2", "phase": phase, "version": VERSION,
                      "game_day": game_day(moment), "period_key": period_key, "created_at": moment.isoformat(),
                      "script_executed_game_action": False, "automation_live_validated": False,
                      "evidence_validation": "file_format_hash_and_supervisor_attestation_only", "events": []}
        if action == "mark-unknown":
            need(isinstance(reason, str) and reason.strip(), "--reason is required")
            record.update(status="submission_unknown", unknown_reason=reason)
        elif action == "record-step":
            need("validate_step" in policy and step in ("deployment", "in_progress"), "step not supported for this scope")
            expected = "manual_submission_reserved" if step == "deployment" else "deployment_recorded"
            need(record["status"] == expected, "step out of order or already recorded")
            frame = checked_frame(root, review, phase, moment=moment)
            policy["validate_step"](frame, step)
            previous = record.get("steps", {}).get("deployment", record["before"])
            check_pair(previous, frame)
            record.setdefault("steps", {})[step] = frame
            record["status"] = step + "_recorded"
        elif action == "record-manual":
            need(isinstance(review, dict) and review.get("source") == "external_supervisor", "manual source must be explicit")
            before = checked_frame(root, review.get("before"), phase, moment=moment)
            after = checked_frame(root, review.get("after"), phase, moment=moment)
            policy["validate"](before, "ready")
            policy["validate"](after, "completed")
            policy["pair"](before, after)
            check_pair(before, after)
            record.update(status="manual_completion_recorded", before=before, after=after,
                          source="external_supervisor", live_window_check=False)
        elif action == "observe-pending":
            need("validate_pending" in policy, "pending observation not supported")
            frame = checked_frame(root, review, phase, moment=moment)
            policy["validate_pending"](frame)
            record.update(status="pending_observed", after=frame, source="supervised_observation")
        else:
            frame = checked_frame(root, review, phase, fresh=action == "reserve", moment=moment)
            policy["validate"](frame, "ready" if action == "reserve" else "completed")
            if action == "reserve":
                need(not (root / "STOP").exists(), "STOP exists")
                window = check_window(frame, game_exe, inspect_window)
                # A second identity read prevents a window switch during preflight.
                need(check_window(frame, game_exe, inspect_window) == window, "foreground identity changed")
                record.update(status="manual_submission_reserved", before=frame, live_window_check=True,
                              note="Reserved once for a supervisor. Recheck the visible UI immediately before any manual action.")
            elif action == "verify":
                before = checked_frame(root, record["before"], phase, moment=moment)
                policy["validate"](before, "ready")
                policy["pair"](before, frame)
                check_pair(before, frame)
                record.update(status="manual_completion_recorded", after=frame, source="supervisor_after_reservation")
            elif action == "observe":
                record.update(status="already_completed_observed", after=frame, source="supervised_observation",
                              live_window_check=False)
            else:
                raise Blocked("unknown journal action")
        record["events"].append({"action": action, "at": moment.isoformat(), "status": record["status"]})
        if "period_guard" in policy:
            policy["period_guard"](root, policy, record.get("after", record.get("before")), moment)
        if action == "observe-pending":
            # An unavailable tier is evidence, never a spent/claimed attempt.
            observation = contained(root, Path("runs") / ("gf2-pending-" + uuid.uuid4().hex + ".json"))
            observation.parent.mkdir(parents=True, exist_ok=True)
            save(observation, record, exclusive=True)
            index = {"schema": 1, "game": "gf2", "phase": phase, "period_key": period_key,
                     "game_day": game_day(moment), "observation": str(observation.relative_to(root)),
                     "sha256": sha(observation.read_bytes())}
            save(path.with_suffix(".observation.json"), index)
            return seal(record)
        save(path, record, exclusive=action not in updates)
        return seal(record)


def check_pair(before, after):
    need(stamp(before["evidence"]["captured_at"]) < stamp(after["evidence"]["captured_at"]), "after evidence must follow before")
    need(before["evidence"]["sha256"] != after["evidence"]["sha256"], "before/after evidence must differ")


def cli(root, policy, argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    for flag in ("status", "reserve", "verify", "record-manual", "observe", "observe-pending", "mark-unknown", "record-step", "execute"):
        modes.add_argument("--" + flag, action="store_true")
    parser.add_argument("--review", type=Path)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--game-exe", type=Path)
    parser.add_argument("--reason")
    parser.add_argument("--step", choices=("deployment", "in_progress"))
    args = parser.parse_args(argv)
    try:
        if args.execute:
            raise Blocked("Automatic game input is not implemented or validated. No click or task was submitted. Use the supervised journal.")
        if args.status:
            out = status(root, policy)
        else:
            action = next((f for f in ("reserve", "verify", "record-manual", "observe", "observe-pending", "mark-unknown", "record-step")
                           if getattr(args, f.replace("-", "_"))), None)
            if action is None:
                out = {k: v for k, v in policy.items() if not callable(v)}
                out.update(game="gf2", version=VERSION, automatic_execution=False, live_validated=False,
                           default="offline_plan", manual_confirmation_required=True)
            else:
                review = None
                if action != "mark-unknown":
                    need(args.review is not None, "--review is required")
                    review = json.loads(args.review.read_text(encoding="utf-8-sig"))
                out = record_action(root, policy, action, review, args.base, args.game_exe, args.reason, step=args.step)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    except (Blocked, OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error), "script_executed_game_action": False}, ensure_ascii=False))
        return 2
