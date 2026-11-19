"""Supervised dispatch collection, unchanged-team redispatch and weekly-tier journal."""
import argparse
import datetime as dt
import json
from pathlib import Path
import gf2_supervised_daily as j

ROOT = Path(__file__).resolve().parent
PINS = {"resource/base/pipeline/public/PublicAreaDailyTasks/dispatchCenter.json":
        "f42a40c3c433c84e1fcd1cbd7ab22f92c43152944700d76339cfd8078723e4a3"}
TIERS = (5, 10, 15, 25)
MISSIONS = {"遗迹探索", "紧急谈判", "前线支援", "物资运输", "绝境评测"}


def common(frame, weekly=False):
    j.need(frame.get("location") == ["公共区", "调度室"], "not the dispatch room")
    j.need(frame.get("dialog_unambiguous") is True, "ambiguous dispatch page")
    j.need(frame.get("paid_speedup") is False and frame.get("team_changes") is False, "paid acceleration/team edits prohibited")
    j.need(frame.get("intelligence_storage") is False and frame.get("resource_production") is False
           and frame.get("mystery_box") is False, "unrelated public-area collection prohibited")
    j.need(frame.get("weekly_goal") == 25 and j.integer(frame.get("weekly_count"))
           and frame["weekly_count"] <= 25, "weekly progress not reviewed")
    if weekly:
        j.need(frame.get("panel_title") == "本周派遣收益", "dispatch income/assessment is not weekly earnings")
    else:
        j.need(j.integer(frame.get("dispatch_currency")) or
               (frame.get("dispatch_currency") is None and frame.get("currency_not_visible") is True
                and frame.get("dispatch_state") == "result"),
               "dispatch currency must be recorded or explicitly unavailable on the result overlay")
        items = frame.get("missions")
        j.need(isinstance(items, list) and len(items) == 5 and len(set(items)) == 5
               and set(items) == MISSIONS, "the five existing missions must be individually identified")
        j.need(frame.get("existing_teams_reviewed") is True, "existing teams were not reviewed")


def collect(frame, state):
    common(frame)
    if state == "ready":
        j.need(frame.get("completed_teams") == 5 and frame.get("control_text") == "一键领取", "not five completed dispatches")
        j.need(frame.get("control_enabled") is True and frame.get("dispatch_state") == "completed_unclaimed", "already collected/in progress")
    else:
        j.need(frame.get("dispatch_state") == "result" and frame.get("panel_title") == "派遣完成", "collection result missing")
        j.need(frame.get("control_text") == "再次派遣" and frame.get("collected_teams") == 5,
               "collection and redispatch must be separate")
        j.need(frame.get("all_five_results_supervised") is True, "do not infer hidden result rows")


def collect_pair(before, after):
    j.need(set(before["missions"]) == set(after["missions"]), "dispatch set changed")
    j.need(j.integer(before["dispatch_currency"]) and j.integer(after["dispatch_currency"])
           and after["dispatch_currency"] >= before["dispatch_currency"], "collection currency evidence incomplete/decreased")
    j.need("post_room" in after.get("supporting_evidence", {}), "post-collection room evidence required")
    j.need(after["weekly_count"] >= before["weekly_count"], "unexpected weekly reset; inspect before continuing")


def redispatch(frame, state):
    common(frame)
    j.need(frame.get("same_original_teams") is True and frame.get("configuration_unchanged") is True, "original teams/configuration required")
    if state == "ready":
        j.need(frame.get("panel_title") == "派遣完成" and frame.get("control_text") == "再次派遣",
               "not the explicit redispatch control")
        j.need(frame.get("dispatch_state") == "result" and frame.get("control_enabled") is True, "already dispatched or unavailable")
        j.need(frame.get("no_cost_prompt") is True, "redispatch cost is ambiguous")
    else:
        j.need(frame.get("dispatch_state") == "in_progress" and frame.get("running_teams") == 5
               and frame.get("capacity") == 5, "five running teams required")
        timers = frame.get("countdown_by_mission", {})
        j.need(isinstance(timers, dict) and set(timers) == MISSIONS
               and all(isinstance(v, str) and v.strip() for v in timers.values()), "all five countdowns must be visible and recorded")
        j.need(frame.get("claim_available") is False, "collection still available; state is ambiguous")


def redispatch_pair(before, after):
    j.need(set(before["missions"]) == set(after["missions"]), "mission set changed")
    if before["dispatch_currency"] is None:
        j.need(before.get("currency_not_visible") is True, "missing before balance must be explicit")
        after["resource_delta_verified"] = False
    else:
        j.need(before["dispatch_currency"] == after["dispatch_currency"], "redispatch consumed currency")
        after["resource_delta_verified"] = True


def calendar_week(moment=None):
    day = dt.date.fromisoformat(j.game_day(moment))
    return (day - dt.timedelta(days=day.weekday())).isoformat()


def weekly(frame, state, tier, key):
    common(frame, weekly=True)
    j.need(frame.get("period_key") == key and frame.get("tier") == tier, "wrong week/tier")
    j.need(type(frame.get("tier")) is int and tier in TIERS, "unsupported milestone")
    j.need(frame.get("same_tier_control_confirmed") is True, "claim control not bound to selected tier")
    if state == "ready":
        j.need(frame["weekly_count"] >= tier and frame.get("tier_state") == "claimable"
               and frame.get("control_text") == "领取" and frame.get("control_enabled") is True,
               "weekly tier is locked/already claimed/ambiguous")
    elif state == "pending":
        j.need(frame["weekly_count"] < tier and frame.get("tier_state") == "locked"
               and frame.get("control_text") == "未完成" and frame.get("control_enabled") is False,
               "not a locked tier observation")
    else:
        j.need(frame["weekly_count"] >= tier and frame.get("tier_state") == "claimed"
               and frame.get("green_check") is True and frame.get("control_enabled") is False,
               "same-tier claimed check required")


def period_guard(root, policy, frame, moment):
    """Calendar grouping never by itself unlocks another game's weekly claim."""
    key = policy["period_key"]
    j.need(key == calendar_week(moment), "week bucket is not current")
    path = j.contained(root, "state/gf2-dispatch-weekly-period.json")
    old = None
    if path.exists():
        old = json.loads(path.read_text(encoding="utf8"))
        j.need(old.get("integrity_sha256") == j.seal(old)["integrity_sha256"], "weekly period record tampered")
    if old and old.get("period_key") != key:
        # Require a separate fresh reset observation before opening the new bucket.
        j.need(frame.get("cycle_reset_reviewed") is True and frame.get("weekly_count") == 0
               and frame.get("claimed_tiers") == [], "new calendar week alone is not proof of game reset")
        j.checked_frame(root, frame, policy["phase"], fresh=True, moment=moment)
    if not old or old.get("period_key") != key:
        data = {"schema": 1, "game": "gf2", "period_key": key, "observed_at": moment.isoformat(),
                "calendar_key_is_not_automatic_reset_proof": True,
                "reset_reviewed": bool(old), "evidence": frame["evidence"]}
        j.save(path, data, exclusive=old is None)


POLICIES = {
    "collect": {"phase": "dispatch-collect", "pins": PINS, "validate": collect, "pair": collect_pair,
                "scope": "Only collect the five completed teams; do not redispatch in the same action."},
    "redispatch": {"phase": "dispatch-redispatch", "pins": PINS, "validate": redispatch, "pair": redispatch_pair,
                   "scope": "Only the existing unchanged teams; no paid acceleration."},
}


def weekly_policy(tier, moment=None):
    j.need(type(tier) is int and tier in TIERS, "weekly tier must be 5/10/15/25")
    key = calendar_week(moment)
    def pair(before, after):
        j.need(before["tier"] == after["tier"] and before["period_key"] == after["period_key"], "weekly tier/period changed")
    return {"phase": f"dispatch-weekly-{tier}", "period_key": key, "pins": PINS,
            "validate": lambda frame, state: weekly(frame, state, tier, key),
            "validate_pending": lambda frame: weekly(frame, "pending", tier, key),
            "pair": pair, "period_guard": period_guard,
            "scope": "One weekly milestone; locked observation does not occupy a claim attempt.",
            "weekly_new_claim_live_validated": False}


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--phase", choices=("collect", "redispatch", "weekly"), required=True)
    parser.add_argument("--tier", type=int, choices=TIERS)
    args, remaining = parser.parse_known_args(argv)
    if args.phase == "weekly" and args.tier is None:
        parser.error("--phase weekly requires --tier")
    policy = weekly_policy(args.tier) if args.phase == "weekly" else POLICIES[args.phase]
    return j.cli(ROOT, policy, remaining)


if __name__ == "__main__":
    raise SystemExit(main())
