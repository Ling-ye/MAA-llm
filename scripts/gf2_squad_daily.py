"""Separate supervised journals for daily squad supply and daily duty."""
import argparse
from pathlib import Path
import gf2_supervised_daily as journal

ROOT = Path(__file__).resolve().parent
PINS = {"resource/base/pipeline/public/PrepareDailyTasks/PlatoonTasks.json":
        "b8908765a2da666b77daed930fea01e8ba0004a630a2bf596e371903fc7768ce"}


def common(frame, page):
    n = journal.need
    n(frame.get("location") == ["班组", page], "wrong squad page; store/event/frontline rejected")
    n(frame.get("period") == "daily" and frame.get("dust_frontline") is False, "daily squad scope only")
    n(frame.get("joined_existing_squad") is True, "joining/applying to a squad is not authorized")
    n(frame.get("dialog_unambiguous") is True, "ambiguous squad page")
    n(frame.get("paid_resources") is False and frame.get("social_or_role_change") is False, "spending/social/role change prohibited")


def supply(frame, state):
    common(frame, "补给")
    n = journal.need
    n(frame.get("supply_name") == "每日补给·五" and frame.get("source_text") == "每日刷新", "unreviewed supply or source")
    n(frame.get("selection") == "single_verified_item" and frame.get("claim_all") is False, "claim only the reviewed daily item")
    n(isinstance(frame.get("item_reference"), str) and frame["item_reference"].strip(), "supply identity required")
    n(frame.get("identity_disambiguated") is True, "duplicate supply names need visual identity/expiry review")
    if state == "ready":
        n(frame.get("control_text") == "领取" and frame.get("control_enabled") is True, "no selected daily claim control")
        n(frame.get("selected_item_claimed") is False and frame.get("unclaimed_daily_items") == 1, "ambiguous/previously claimed supply")
    else:
        n(frame.get("selected_item_claimed") is True and frame.get("green_check") is True, "daily supply claim not confirmed")
        n(frame.get("control_enabled") is False and frame.get("unclaimed_daily_items") == 0, "a claim is still available or status unknown")
        n(frame.get("current_day_claim_record_visible") is True, "dated squad claim record required")


def supply_pair(before, after):
    journal.need(before["item_reference"] == after["item_reference"], "different daily supply item")


def duty(frame, state):
    common(frame, "要务")
    n = journal.need
    n(frame.get("duty_name") == "每日要务IV" and frame.get("enemy_level") == 39, "unreviewed daily duty tier")
    n(frame.get("objective") == "全部歼灭", "unreviewed battle objective")
    if state == "ready":
        n(frame.get("battle_state") == "not_started" and frame.get("control_text") == "开始作战", "not the initial duty stage")
        n(frame.get("entry_cost_reviewed_free") is True and frame.get("fee_or_currency_prompt") is False, "battle cost unknown or paid")
        n(frame.get("daily_completed_banner") is False, "daily duty already completed")
    else:
        n(frame.get("battle_state") == "completed" and frame.get("daily_completed_banner") == "每日要务已完成", "return-page completion not verified")
        n(frame.get("result_text") == "任务完成" and frame.get("result_stage") == "DW-4 每日要务IV", "battle result not bound to daily duty")
        n(frame.get("reward_confirmed") is True, "battle rewards not confirmed")
        extra = frame.get("supporting_evidence", {})
        n(all(key in extra for key in ("deployment", "battle_result", "reward")), "deployment/result/reward evidence required")
        n(frame.get("deployed_count") == 5 and frame.get("deployed_capacity") == 5
          and frame.get("formation_supervised") is True, "deployment was not reviewed")


def duty_step(frame, step):
    common(frame, "要务")
    journal.need(frame.get("duty_name") == "每日要务IV", "wrong daily duty")
    if step == "deployment":
        journal.need(frame.get("battle_state") == "deployment" and frame.get("control_text") == "作战开始", "not the deployment stage")
        journal.need(frame.get("deployed_count") == 5 and frame.get("deployed_capacity") == 5
                     and frame.get("formation_supervised") is True, "formation must be reviewed; no automatic rearrangement")
        journal.need(frame.get("fee_or_currency_prompt") is False, "unexpected battle cost")
    else:
        journal.need(frame.get("battle_state") == "in_progress"
                     and frame.get("battle_running_observed") is True, "battle progress not observed")


def duty_pair(before, after):
    journal.need(before["duty_name"] == after["duty_name"], "different daily duty")
    evidence = after["supporting_evidence"]
    order = [before["evidence"], evidence["deployment"], evidence["battle_result"], evidence["reward"], after["evidence"]]
    times = [journal.stamp(item["captured_at"]) for item in order]
    journal.need(all(a < b for a, b in zip(times, times[1:])), "battle evidence order invalid")
    journal.need(len({item["sha256"] for item in order}) == len(order), "battle evidence must cover distinct stages")


POLICIES = {
    "supply": {"phase": "squad-daily-supply", "pins": PINS, "validate": supply, "pair": supply_pair,
               "scope": "Only the reviewed daily-refresh supply; never claim all or frontline supplies."},
    "duty": {"phase": "squad-daily-duty", "pins": PINS, "validate": duty, "pair": duty_pair, "validate_step": duty_step,
             "scope": "Supervised daily duty IV only; initial, deployment, in-progress and completed states are separate.",
             "upstream_installed_duty_entry_verified": False},
}


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--phase", choices=tuple(POLICIES), required=True)
    args, remaining = parser.parse_known_args(argv)
    return journal.cli(ROOT, POLICIES[args.phase], remaining)


if __name__ == "__main__":
    raise SystemExit(main())
