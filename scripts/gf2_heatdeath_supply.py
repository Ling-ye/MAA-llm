"""Journal-only supervision of the reviewed Heat Death supply-mode event."""
from pathlib import Path
import gf2_supervised_daily as j

ROOT = Path(__file__).resolve().parent
EVENT = "热寂悖论"
END = j.stamp("2026-11-24T08:59:00+08:00")
SHOP_END = "2026-11-30T04:59:00+08:00"


def action_guard(action, moment):
    if action == "reserve":
        j.need(moment < END, "reviewed combat event has ended; exchange availability is not combat availability")


def common(frame):
    j.need(frame.get("event") == EVENT and frame.get("mode") == "物资模式", "exact event and supply mode required")
    j.need(frame.get("event_end") == END.isoformat(), "combat deadline must match the reviewed event")
    j.need(frame.get("dialog_unambiguous") is True, "ambiguous event page")
    j.need(frame.get("currency") == "准入密钥" and frame.get("key_scope") == "event_supply_only",
           "dedicated event key required; ordinary stamina/potions are prohibited")
    j.need(frame.get("key_inventory_cap") == 6 and j.integer(frame.get("keys")) and frame["keys"] <= 6,
           "key inventory not reviewed")
    for key in ("refill", "exchange", "ordinary_stamina_spent", "paid_currency_spent", "challenge_or_story"):
        j.need(frame.get(key) is False, "refill/exchange/stamina/payment/other modes prohibited")


def validate(frame, state):
    common(frame)
    j.need(frame.get("stage_id") == "DF-1-5" and frame.get("stage_name") == "于乱流中 V", "unreviewed event stage")
    j.need(frame.get("highest_unlocked_reviewed") is True and frame.get("all_three_objectives_complete") is True,
           "stage unlock/objectives not reviewed")
    j.need(frame.get("event_state") == "open" and j.stamp(frame["evidence"]["captured_at"]) < END,
           "event closed/unknown or evidence after combat deadline")
    if state == "ready":
        j.need(frame.get("panel_title") == "自律准备" and frame.get("control_text") == "确认"
               and frame.get("control_enabled") is True, "exact self-discipline confirmation required")
        j.need(j.integer(frame.get("selected_runs"), 1) and frame["selected_runs"] == frame["keys"],
               "select only all currently verified existing keys")
        j.need(j.integer(frame.get("ui_max_runs"), 1) and frame["selected_runs"] <= frame["ui_max_runs"] <= 6,
               "batch exceeds the actual reviewed UI limit")
        j.need(frame.get("cost_per_run") == 1 and type(frame.get("cost_per_run")) is int
               and type(frame.get("total_key_cost")) is int and frame["total_key_cost"] == frame["selected_runs"],
               "same confirmation must show the exact key total")
        j.need(frame.get("same_confirmation_cost_and_count") is True, "count/cost not bound to the same confirmation")
        extra = frame.get("supporting_evidence", {})
        j.need(all(name in extra for name in ("event_home", "key_details", "stage")), "event/key/stage evidence chain required")
        times = [j.stamp(extra[k]["captured_at"]) for k in ("event_home", "stage", "key_details")]
        times.append(j.stamp(frame["evidence"]["captured_at"]))
        j.need(all(a < b for a, b in zip(times, times[1:])), "event evidence chain out of order")
    else:
        j.need(frame["keys"] == 0 and frame.get("batch_state") == "completed", "zero keys and completed batch required")
        j.need(j.integer(frame.get("completed_runs"), 1), "completed batch count missing")
        j.need(frame.get("reward_name") == "火控残片" and j.integer(frame.get("reward_quantity"), 1)
               and j.integer(frame.get("reward_inventory")), "reward name/quantity/inventory must be reviewed")
        j.need(all(k in frame.get("supporting_evidence", {}) for k in ("reward", "reward_name")), "reward evidence required")


def pair(before, after):
    j.need(before["selected_runs"] == after["completed_runs"]
           and before["keys"] - before["total_key_cost"] == after["keys"], "batch/key outcome mismatch")
    sequence = [before["evidence"], after["supporting_evidence"]["reward"],
                after["supporting_evidence"]["reward_name"], after["evidence"]]
    times = [j.stamp(e["captured_at"]) for e in sequence]
    j.need(all(a < b for a, b in zip(times, times[1:])) and len({e["sha256"] for e in sequence}) == len(sequence),
           "confirmation/reward/final key evidence must be distinct and ordered")


def pending(frame):
    common(frame)
    state = frame.get("event_state")
    if state == "closed":
        j.need(frame.get("closed_entry_reviewed") is True, "closed event entry must be observed")
    else:
        j.need(state == "open" and frame["keys"] == 0 and frame.get("no_keys_reviewed") is True,
               "skip only a confirmed closed event or zero existing keys; unknown state must stop")


POLICY = {"phase": "heatdeath-supply-202611", "pins": {}, "validate": validate, "pair": pair,
          "validate_pending": pending, "action_guard": action_guard,
          "event": EVENT, "mode": "物资模式", "stage": "DF-1-5 于乱流中 V", "event_end": END.isoformat(),
          "exchange_end_is_not_play_end": SHOP_END, "installed_event_backend_verified": False,
          "scope": "Supervisor journal only. Existing dedicated keys; no refill, exchange, ordinary stamina or game input."}


if __name__ == "__main__":
    raise SystemExit(j.cli(ROOT, POLICY))
