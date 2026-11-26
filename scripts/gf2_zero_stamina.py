"""Pure validation for opt-in individual GF2 activity goals; no game input."""
import hashlib
import json
import re

from supervised_evidence import integer, need, stamp

PREFIX = "activity-"
SCOPE = (
    "exact_activity_and_stage_authorized actual_game_cost_reviewed "
    "one_attempt_only no_auto_repeat no_refill no_purchase"
)
RESULT = "same_activity_and_stage_result clear_and_reward_verified debit_and_quota_reviewed"
MODES = {"event-stage", "permanent-challenge", "event-material-sweep"}
MATERIAL_SCOPE = {
    "mode": "event-material-sweep", "activity": "直播重连世界海", "stage": "KF-1-5 打榜任务V",
    "difficulty": "物资模式", "cycle": "2026-12-15T08:59:00+08:00",
    "attempt": 1, "quota_type": "existing-ticket",
}
QUOTAS = {"first-clear", "free-attempt", "existing-ticket"}


def key_format(item):
    return isinstance(item, str) and re.fullmatch(r"activity-[a-f0-9]{24}", item) is not None


def text_id(value):
    return (isinstance(value, str) and 0 < len(value) <= 90 and value == value.strip()
            and value.isprintable() and not any(c in value for c in "\\/"))


def scope_key(scope):
    need(isinstance(scope, dict) and set(scope) == {
        "mode", "activity", "stage", "difficulty", "cycle", "attempt", "quota_type"
    }, "exact mode/activity/stage/difficulty/current cycle/quota/attempt required")
    need(scope.get("mode") in MODES and scope.get("quota_type") in QUOTAS,
         "only reviewed event stages or permanent challenges are covered")
    need(all(text_id(scope[k]) for k in ("activity", "stage", "difficulty", "cycle")),
         "exact visible activity, stage, difficulty and cycle labels required")
    need(integer(scope["attempt"]) and 1 <= scope["attempt"] <= 999, "invalid exact attempt number")
    if scope["quota_type"] == "first-clear":
        need(scope["attempt"] == 1, "first clear is never replayed")
    if scope["mode"] == "event-material-sweep":
        need(scope == MATERIAL_SCOPE, "material sweep must match the reviewed exact event stage and cutoff")
    # Quota type is intentionally not part of the identity: relabeling cannot replay an attempt.
    identity = {k: v for k, v in scope.items() if k != "quota_type"}
    raw = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return PREFIX + hashlib.sha256(raw).hexdigest()[:24]


def activity_review(item, action, data, record):
    f, shots = data["facts"], data["screens"]
    scope = f.get("activity_scope")
    need(scope_key(scope) == item, "scope does not match this activity receipt")
    need(data.get("guest_identity") and {"primary", "quota"} <= shots.keys(),
         "exact GF2 probe, stage frame, and independent quota evidence required")
    now = stamp(data["at"])
    opened, closed = stamp(f.get("window_start")), stamp(f.get("window_end"))
    need(opened <= now < closed and all(opened <= stamp(s["captured_at"]) < closed for s in shots.values()),
         "activity window closed or evidence outside its reviewed window")
    need(type(f.get("stamina_cost")) is int and f["stamina_cost"] == 0 and integer(f.get("stamina")),
         "visible zero stamina cost and current stamina counter required")
    need(f.get("purchase_or_refill_prompt") is False, "purchase/refill prompt or unknown spending state")
    category = scope["quota_type"]
    remaining = f.get("quota_remaining")
    need(integer(remaining) and 0 <= remaining <= 999, "exact available attempts/tickets required")
    if category == "existing-ticket":
        need(text_id(f.get("ticket")) and type(f.get("ticket_per_attempt")) is int
             and f["ticket_per_attempt"] == 1 and f.get("use_existing_ticket_authorized") is True,
             "exact named one-ticket cost and separate authorization required")
    else:
        need(f.get("ticket") is None and type(f.get("ticket_per_attempt")) is int
             and f["ticket_per_attempt"] == 0, "no ticket use on the free path")
    units = 1
    if scope["mode"] == "event-material-sweep":
        need(closed == stamp(MATERIAL_SCOPE["cycle"]) and f.get("all_three_stage_objectives") is True,
             "reviewed combat deadline and three-star auto-resolve eligibility required")
        need(f["ticket"] == "真爱勋章" and type(f.get("ticket_capacity")) is int
             and f["ticket_capacity"] == 6 and remaining <= f["ticket_capacity"],
             "actual event ticket and six-ticket storage cap required")
        units = f.get("selected_runs")
        need(integer(units) and 1 <= units <= 3 and f.get("exact_batch_authorized") is True,
             "need one separately reviewed batch, maximum three owned tickets")
        if action == "reserve":
            need(f.get("confirmation_title") == "自律准备" and
                 f.get("confirmation_control") == "确认" and f.get("confirmation_enabled") is True,
                 "exact enabled self-discipline confirmation required")
        else:
            need("reward" in shots and f.get("reward_name") == "粉丝点赞" and
                 type(f.get("reward_quantity")) is int and f["reward_quantity"] == 1000 * units,
                 "expected live reward and exact quantity must match requested sweep count")
    if action == "reserve":
        point = f.get("entry_tap_xy")
        need(isinstance(point, list) and len(point) == 2 and all(integer(x) for x in point),
             "reserve the exact on-screen confirmation point")
        need(f.get("explicitly_selected_current_attempt") is True and remaining >= units and
             (category != "first-clear" or (remaining == 1 and f.get("first_clear_pending") is True)),
             "need an available and individually selected free attempt")
        return
    need(action == "verify" and record is not None, "activity goals require fresh before/after review")
    b = record["before"]["facts"]
    need(scope == b["activity_scope"] and (opened, closed) ==
         (stamp(b["window_start"]), stamp(b["window_end"])) and
         (f.get("ticket"), f["ticket_per_attempt"], f.get("selected_runs")) ==
         (b.get("ticket"), b["ticket_per_attempt"], b.get("selected_runs")),
         "result is not the same activity/window/stage/cost")
    need(f["stamina"] >= b["stamina"] and f.get("no_stamina_use_verified") is True,
         "stamina decreased or zero use not verified")
    need(remaining == b["quota_remaining"] - units and
         f.get("result") == ("sweep-complete" if scope["mode"] == "event-material-sweep" else "clear") and
         (category != "first-clear" or f.get("first_clear_pending") is False),
         "same stage clear and exactly the reviewed attempt/ticket debit required")
