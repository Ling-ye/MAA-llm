"""Deterministic CN public-recruit refill policy. This module sends no game input."""
import argparse
import itertools
import json
from pathlib import Path

from project_paths import config_path, install_path
from supervised_evidence import Blocked, integer, need, sha

TOP = "高级资深干员"
SENIOR = "资深干员"
ROBOT = "支援机械"
POLICY = {
    "stars": [3, 4, 5], "duration_minutes": 540, "slots": 4, "permit_per_slot": 1,
    "preserve": [TOP], "refresh": False, "expedite": False,
}


def read_policy():
    policy = json.loads(config_path("ark-recruit-refill.json").read_text(encoding="utf-8-sig"))
    need(policy == POLICY and type(policy.get("refresh")) is bool and type(policy.get("expedite")) is bool
         and all(type(policy[k]) is int for k in ("duration_minutes", "slots", "permit_per_slot"))
         and all(type(star) is int for star in policy["stars"]), "unsafe or unsupported refill policy")
    return policy


def read_pool(path=None):
    path = Path(path) if path is not None else install_path("arknights") / "resource/recruitment.json"
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8-sig"))
    ops = data.get("operators") if isinstance(data, dict) else None
    need(isinstance(ops, list) and len(ops) >= 30, "incomplete CN recruitment pool")
    ids, names, operators = set(), set(), []
    for row in ops:
        need(isinstance(row, dict), "invalid operator record")
        ident, name, rarity, tags = (row.get(k) for k in ("id", "name", "rarity", "tags"))
        need(isinstance(ident, str) and ident and ident not in ids and isinstance(name, str) and name
             and type(rarity) is int and 1 <= rarity <= 6 and isinstance(tags, list) and tags
             and all(isinstance(t, str) and t and t == t.strip() for t in tags),
             "invalid recruitment roster entry")
        ids.add(ident)
        names.add((name, rarity))
        need((TOP in tags) == (rarity == 6) and (SENIOR in tags) == (rarity == 5),
             "unexpected CN top/senior rarity mapping")
        operators.append((rarity, name, frozenset(tags)))
    need({("琴柳", 6), ("桑葚", 5), ("罗比菈塔", 4)} <= names,
         "local CN pool predates the 2026-11-01 recruitment update")
    need({1, 2, 3, 4, 5, 6} <= {o[0] for o in operators}, "CN pool missing a rarity")
    return operators, sha(raw)


def decide(tags, permit_count, pool, policy):
    operators, digest = pool
    known = set().union(*(row[2] for row in operators))
    need(isinstance(tags, list) and len(tags) == 5 and all(isinstance(t, str) and t in known for t in tags)
         and len(set(tags)) == 5, "need exactly five distinct visible CN tags")
    need(integer(permit_count), "visible ordinary permit count required")
    common = {"pool_sha256": digest, "refresh": False, "expedite": False}
    if TOP in tags:
        return {**common, "action": "hold-six-star"}
    if permit_count < policy["permit_per_slot"]:
        return {**common, "action": "hold-no-permit"}
    eligible = [row for row in operators if row[0] in policy["stars"]]
    # At 9h, 1/2-star operators are excluded. Six stars require Top Senior,
    # which was already handled; a rare non-Top-Senior pool result is not a reason to hold.
    ranked = []
    for size in range(4):
        for selection in itertools.combinations([tag for tag in tags if tag != ROBOT], size):
            p = [row for row in eligible if set(selection) <= row[2]]
            if p:
                ranked.append((min(row[0] for row in p), selection, sorted(row[1] for row in p)))
    need(bool(ranked), "no applicable ordinary recruitment pool")
    tier, selection, candidates = min(ranked, key=lambda x: (-x[0], len(x[1]), tuple(tags.index(tag) for tag in x[1])))
    return {**common, "action": "start", "minimum_stars_if_tags_hold": tier,
            "selected_tags": list(selection), "candidate_count": len(candidates),
            "candidates": candidates if selection else [],
            "duration_minutes": policy["duration_minutes"], "permit_cost": policy["permit_per_slot"]}


def slot_number(item):
    return int(item[-1]) if item in {f"recruit-refill-slot-{i}" for i in range(1, 5)} else None


def review_slot(slot, stage, data, record, *, get_pool=read_pool, get_policy=read_policy):
    f, screens = data["facts"], data["screens"]
    need(type(f.get("slot")) is int and f["slot"] == slot, "wrong recruitment slot")
    if stage == "verify":
        b = record["before"]["facts"]
        need("overview" in screens and f.get("slot_state") == "running"
             and f.get("selected_tags") == b["selected_tags"]
             and integer(f.get("remaining_seconds"), 8 * 3600 + 50 * 60)
             and f["remaining_seconds"] <= b["duration_minutes"] * 60,
             "same slot, same selected tags and live 9h timer required")
        need(integer(f.get("permit_count")) and f["permit_count"] == b["permit_count"] - 1
             and integer(f.get("lmd")) and f["lmd"] == b["lmd"] - b["quoted_lmd"]
             and f.get("refresh_or_expedite_used") is False,
             "ordinary permit/LMD delta or no-refresh/no-expedite proof missing")
        return
    need(stage == "reserve" and {"overview", "confirm"} <= screens.keys()
         and f.get("slot_state") == "empty" and f.get("expedite_phase_ended") is True
         and f.get("paid_prompt") is False, "empty slot and post-expedite confirmation evidence required")
    result = decide(f.get("tags"), f.get("permit_count"), get_pool(), get_policy())
    need(result["action"] == "start", "unsafe or ineligible slot: " + result["action"])
    need(f.get("selected_tags") == result["selected_tags"]
         and f.get("duration_minutes") == result["duration_minutes"]
         and f.get("permit_cost") == result["permit_cost"]
         and type(f.get("duration_minutes")) is int and type(f.get("permit_cost")) is int
         and integer(f.get("lmd")) and integer(f.get("quoted_lmd")) and f["quoted_lmd"] <= f["lmd"],
         "visible tags, time and budget must match the deterministic plan")
    f["refill_plan"] = result


def review_skip(slot, reason, data):
    f = data["facts"]
    need(type(f.get("slot")) is int and f["slot"] == slot and "overview" in data["screens"],
         "same-slot overview required")
    if reason == "already_running":
        need(f.get("slot_state") == "running" and integer(f.get("remaining_seconds"), 1), "slot is not running")
        return
    need("confirm" in data["screens"] and f.get("slot_state") == "empty", "review exact empty slot")
    result = decide(f.get("tags"), f.get("permit_count"), read_pool(), read_policy())
    need(result["action"] == {"top_senior_hold": "hold-six-star", "no_permit": "hold-no-permit"}.get(reason),
         "skip does not match the current visible tags and permit count")
    f["refill_plan"] = result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", type=Path, help="installed MAA CN resource/recruitment.json")
    parser.add_argument("--tags", nargs=5, required=True)
    parser.add_argument("--permits", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(decide(args.tags, args.permits, read_pool(args.pool), read_policy()), ensure_ascii=False))
        return 0
    except (Blocked, OSError, ValueError) as e:
        parser.exit(2, f"Blocked: {e}\n")


if __name__ == "__main__":
    raise SystemExit(main())
