"""MuMu-first planning and evidence journal. Never launches or controls a game."""
import argparse
import datetime as dt
import json
import re
import unicodedata
from pathlib import Path

from project_paths import config_path, require_execution
from runner import exclusive_lock, read_json
from supervised_evidence import Blocked, contained, image_size, integer, need, save, seal, sha, stamp

ROOT = Path(__file__).resolve().parent
TZ = dt.timezone(dt.timedelta(hours=8))
PACKAGES = {"arknights": "com.hypergryph.arknights", "gf2": "com.Sunborn.SnqxExilium",
            "endfield": "com.hypergryph.endfield"}
VERSIONS = {"arknights": "v6.22.0", "gf2": "v2.8.6", "endfield": "v3.1.0"}
VALIDATION = {"arknights": "established_maa_adb_requires_current_readiness",
              "gf2": "supervised_adb_validated_not_locked_or_unattended",
              "endfield": "android_path_not_login_or_workflow_validated"}
# item : (required scope attestations, required visible result attestations)
ITEMS = {
    "arknights": {
        "sanity-tl9": ("tl9 exact_current_open_stage auto_deploy natural_sanity_only",
                       "same_stage_clear sanity_delta_verified"),
        "sanity-event-stage": (
            "explicit_stage_and_window_authorized exact_current_open_stage auto_deploy natural_sanity_only prior_sanity_runs_reviewed",
            "same_stage_clear exact_completed_count sanity_delta_verified"),
        "public-recruit": ("operations_v2 high_priority_tags_protected refresh_policy_reviewed expedite_limit_reviewed",
                           "recruitment_slots_verified refresh_and_expedite_delta_verified"),
        "base": ("operations_v2 full_facility_rotation money_trade_drone_only",
                 "rotation_verified collection_verified drone_delta_verified"),
        "credit-claim": ("operations_v2 free_credit_collection_only", "credit_collection_verified"),
        "credit": ("operations_v2 recruitment_priority blacklist_respected no_forced_purchase",
                   "credit_delta_verified selected_items_verified"),
        "friend-visit": ("existing_friend_only no_social_changes", "friend_visit_verified"),
        "daily-rewards": ("daily_award_only no_originite", "daily_progress_and_claims_verified"),
        "close": ("configured_guest_app_only relevant_maa_worker_only", "guest_package_stopped helper_absent"),
    },
    "gf2": {
        "daily-free-box": ("daily_exact_box same_detail_free_zero one_daily_claim",
                           "daily_box_limit_exhausted claimed_rewards_verified paid_balance_unchanged"),
        "weekly-free-box": ("theme_selection weekly_exact_box same_detail_free_zero one_weekly_claim",
                            "same_weekly_offer_exhausted claimed_rewards_verified paid_balance_unchanged"),
        "squad-daily-supply": ("daily_refresh_supply selected_single_item existing_squad",
                               "selected_green_check independent_claim_log"),
        "squad-duty": ("current_duty_and_existing_team clear_objective no_extra_spend",
                       "stage_result deployment_and_rewards duty_completed_banner"),
        "squad-duty-supply": ("duty_trigger_supply selected_single_item existing_squad",
                              "selected_green_check independent_claim_log"),
        "dispatch-collect": ("original_dispatch_teams one_completed_batch", "team_results_and_rewards"),
        "dispatch-redispatch": ("original_roster_unchanged no_acceleration",
                                "all_reviewed_teams_in_progress timers_verified"),
        "dispatch-weekly-5": ("exact_weekly_tier_only", "selected_tier_claim_verified"),
        "dispatch-weekly-10": ("exact_weekly_tier_only", "selected_tier_claim_verified"),
        "dispatch-weekly-15": ("exact_weekly_tier_only", "selected_tier_claim_verified"),
        "dispatch-weekly-25": ("exact_weekly_tier_only", "selected_tier_claim_verified"),
        "dispatch-stored-puzzle": ("stored_puzzle_first_option no_consumables inventory_room_verified",
                                   "stored_puzzle_change_verified stamina_change_verified paid_balance_unchanged"),
        "dispatch-production": ("free_production_only no_other_dispatch_action", "production_rewards_verified"),
        "breakthrough-sweep": ("highest_sweepable_tier natural_or_levelup_stamina_only no_refill",
                               "exact_tier_and_sweep_number rewards_and_stamina_delta"),
        "event-material": ("active_reviewed_event highest_reviewed_sweepable_stage existing_special_keys_only no_refill",
                           "event_reward_result special_key_delta"),
        "tea": ("existing_free_tea_audited daily_free_attempt_available", "tea_daily_complete effect_verified"),
        "cooking": ("standard_recipe first_serving_free no_more_servings", "cooking_daily_complete reward_or_effect_verified"),
        "watering": ("existing_flower_only no_seeds_or_fertilizer", "watering_daily_complete"),
        "commission-rest-rewards": ("water_and_cooking_daily_rewards_only", "both_rest_rewards_accounted"),
        "prewar-signin": ("active_prewar_supply selected_current_day", "current_signin_claimed"),
        "daily-rewards": ("daily_activity_rewards_only", "daily_activity_goal_met all_reward_tiers_accounted"),
        "close": ("configured_guest_app_only relevant_maa_worker_only", "guest_package_stopped helper_absent"),
    },
    "endfield": {
        "friend-visit": ("existing_friend_only no_social_changes", "friend_visit_verified"),
        "base-rewards": ("approved_quick_collection only_approved_base_items", "base_collection_verified"),
        "protocol-space": ("reviewed_target_inventory single_reward no_medicine_or_double",
                           "stage_and_inventory_delta_verified"),
        **{f"environment-monitoring-{site}": ("approved_monitoring_sites current_site_state_reviewed",
                                               "approved_site_results_individually_verified")
           for site in ("first-reviewed", "second-reviewed")},
        **{f"{action}-{region}": checks
           for action, checks in {
               "stock-sell": ("elastic_approved_regions only_existing_elastic_policy no_upload", "ticket_delta_verified"),
               "stock-buy": ("elastic_approved_regions no_stable_purchase no_upload", "ticket_delta_verified"),
               "tail": ("prior_transfer_list same_region correct_claimable_state", "tail_status_and_balance_verified"),
               "recycle": ("remote_collection_only same_region", "recycle_rewards_verified"),
           }.items() for region in ("valleyiv", "wuling")},
        **{f"valley-gift-{gift}": ("exact_discount_minus_80 reviewed_single_valley_gift", "gift_and_balance_delta_verified")
           for gift in ("breeze-of-kjersch", "tidestone-specimen", "simonch-shawl", "frontiers-watch",
                        "aurylene-camera", "cosmic-gate-puzzle", "surfing-festival-ticket")},
        **{f"delivery-{site}": ("approved_warehouse_node current_order_and_reserve_review quick_transfer_only",
                               "node_results_and_settlement_state_verified")
           for site in ("originium-science-park", "origin-lodespring", "power-plateau", "wuling-city", "test-area")},
        "credit-claim": ("credit_claim_only", "credit_claim_delta_verified"),
        **{f"credit-{product}-{cycle}": ("exact_reviewed_target credit_price_and_daily_budget_reviewed",
                                       "credit_delta_and_target_verified")
           for cycle in range(5) for product in ("oroberyl", "arsenal-ticket")},
        **{f"credit-refresh-{cycle}": ("two_targets_reviewed exact_refresh_cost_and_daily_budget_reviewed",
                                       "credit_delta_and_refreshed_shelf_verified") for cycle in range(4)},
        "credit-final-review": ("last_shelf_and_both_targets_reviewed", "credit_budget_and_limit_outcome_reviewed"),
        "daily-rewards": ("daily_activity_rewards_only", "activity_100 all_reward_tiers_accounted"),
        "close": ("configured_guest_app_only relevant_maa_worker_only", "guest_package_stopped helper_absent"),
    },
}
WEEKLY = {"weekly-free-box", *(f"dispatch-weekly-{tier}" for tier in (5, 10, 15, 25))}
BEFORE_SWEEP = ("dispatch-stored-puzzle", "dispatch-production")
SKIP = {
    "sanity-tl9": {"stage_closed", "auto_deploy_unavailable", "no_eligible_resource"},
    "sanity-event-stage": {"stage_closed", "auto_deploy_unavailable", "no_eligible_resource"},
    "event-material": {"event_closed", "no_eligible_resource", "stage_unavailable"},
    "prewar-signin": {"event_closed", "not_yet_available"},
    "dispatch-stored-puzzle": {"nothing_stored", "would_overflow"},
    "dispatch-production": {"nothing_stored"},
    "weekly-free-box": {"not_available_in_current_week", "not_yet_available"},
    "dispatch-collect": {"nothing_to_collect"},
    "dispatch-redispatch": {"teams_already_in_progress"},
    "squad-duty-supply": {"no_matching_eligible_supply"},
    "tea": {"not_yet_available"},
    "watering": {"no_existing_flower"},
    "breakthrough-sweep": {"no_eligible_resource", "stage_unavailable"},
    **{f"dispatch-weekly-{tier}": {"tier_not_yet_unlocked"} for tier in (5, 10, 15, 25)},
}


def game_day(now):
    return (now.astimezone(TZ) - dt.timedelta(hours=4)).date().isoformat()


def period(item, now):
    # GF2's recipe archive shows a 05:00 CN reset for drinks, not the
    # generic 04:00 game-day boundary used for other items.
    if item == "tea":
        return (now.astimezone(TZ) - dt.timedelta(hours=5)).date().isoformat()
    day = game_day(now)
    if item not in WEEKLY:
        return day
    year, week, _ = dt.date.fromisoformat(day).isocalendar()
    return f"{year}-W{week:02d}"


def checklist(game):
    return [{"id": item, "period": "weekly" if item in WEEKLY else "daily",
             "before_checks": before.split(), "after_checks": after.split(),
             "allowed_skip_reasons": sorted(SKIP.get(item, ())),
             "first_review": list(BEFORE_SWEEP) if item == "breakthrough-sweep" else [],
             **({"optional_explicit_scope": True} if item == "sanity-event-stage" else {}),
             **({"reset_cn": "05:00", "before_roles": ["primary", "confirm"],
                 "after_roles": ["primary", "drink_effect"]} if item == "tea" else {})}
            for item, (before, after) in ITEMS[game].items()]


def route(game):
    return {"game": game, "transport": "mumu", "package": PACKAGES[game],
            "reviewed_maa_version": VERSIONS[game], "validation": VALIDATION[game],
            "native_fallback": False, "game_action_performed": False,
            "automatic_game_input": False, "checklist": checklist(game)}


def path_for(root, game, item, now):
    return contained(root, f"state/mumu/{game}/{period(item, now)}/{item}.json")


def load_record(root, game, item, now):
    path = path_for(root, game, item, now)
    if not path.exists():
        return None
    record = read_json(path)
    need(seal(record) == record and record.get("schema") == 1 and
         (record.get("game"), record.get("item"), record.get("period")) ==
         (game, item, period(item, now)), "unreadable or mismatched receipt; do not retry")
    need(record.get("status") in ("reserved", "verified", "observed_already_done",
         "observed_ineligible", "unknown"), "invalid state; do not retry")
    from supervised_evidence import verify_record_evidence
    verify_record_evidence(root, record)
    return record


def reported_state(root, game, now):
    rows = []
    for entry in checklist(game):
        item = entry["id"]
        try:
            record = load_record(root, game, item, now)
            row = {"id": item, "period": period(item, now),
                   "status": record["status"] if record else "unreviewed"}
            if record and "reason" in record:
                row["reason"] = record["reason"]
        except (Blocked, OSError, ValueError, TypeError, KeyError):
            row = {"id": item, "period": period(item, now), "status": "blocked_invalid_receipt"}
        rows.append(row)
    return {**route(game), "day": game_day(now), "items": rows}


def binding(game):
    path = config_path("mumu-supervised.json")
    binding = read_json(path)["emulators"][game]
    serial = binding.get("serial")
    match = isinstance(serial, str) and re.fullmatch(r"127\.0\.0\.1:([0-9]{1,5})", serial)
    need(binding.get("enabled") is True and match and 1 <= int(match[1]) <= 65535 and
         integer(binding.get("vm_index")), "configure and review an enabled exact local MuMu instance")
    for other, item in read_json(path)["emulators"].items():
        if other != game:
            need(item.get("serial") != serial and item.get("vm_index") != binding["vm_index"],
                 "MuMu identity must be dedicated; one instance or serial configured twice")
    return {"serial": serial, "vm_index": binding["vm_index"]}


def evidence(root, ev, now):
    seen = stamp(ev.get("captured_at"))
    age = (now - seen).total_seconds()
    need(0 <= age <= 300, "guest frame stale or from the future")
    path = contained(root, ev["path"])
    need(path.is_relative_to(contained(root, "evidence")) and path.suffix.lower() == ".png",
         "bind actual guest PNG under evidence/")
    need(path.stat().st_size <= 24 * 1024 * 1024, "guest frame too large")
    raw = path.read_bytes()
    need(raw.startswith(b"\x89PNG\r\n\x1a\n") and sha(raw) == ev.get("sha256"), "guest PNG changed")
    w, h = image_size(raw)
    need(w > 0 and h > 0 and w * 9 == h * 16, "need reviewed 16:9 guest frame")
    return {"path": path.relative_to(root.resolve()).as_posix(), "sha256": sha(raw),
            "captured_at": seen.isoformat()}


def all_true(review, fields):
    need(isinstance(review, dict) and all(review.get(x) is True for x in fields.split()),
         "missing explicit review: " + ", ".join(x for x in fields.split()
                                                  if not isinstance(review, dict) or review.get(x) is not True))


def frame(root, review, game, item, now, bound, *, close_result=False):
    need((review.get("game"), review.get("item"), review.get("day"), review.get("transport")) ==
         (game, item, game_day(now), "mumu"), "review game/item/day/transport mismatch")
    need(review.get("package") == PACKAGES[game] and review.get("maa_version") == VERSIONS[game] and
         review.get("serial") == bound["serial"] and type(review.get("vm_index")) is int and
         review.get("vm_index") == bound["vm_index"], "wrong guest serial/instance/package/version")
    need(review.get("desktop_state") in ("locked", "unlocked", "unknown"), "declare observed host lock state")
    if game != "arknights":
        need(review["desktop_state"] == "unlocked", "guest workflow not validated for locked/unknown host")
    if game == "endfield":
        raise Blocked("Endfield Android login/workflow not validated; plan/status only until reviewed adapter approval")
    all_true(review, "supervised exact_mumu_instance_reviewed adb_device official_package_reviewed decoded_fresh_guest_frame no_unhandled_prompt cross_transport_history_reviewed")
    if not close_result:
        all_true(review, "correct_account_home_reviewed expected_foreground_package_reviewed")
    else:
        all_true(review, "correct_guest_after_close_reviewed")
    if item in WEEKLY:
        need(review.get("reviewed_period") == period(item, now), "weekly period mismatch")
        all_true(review, "actual_weekly_cycle_reviewed")
    need(isinstance(review.get("facts"), dict), "review facts required")
    shots = review.get("screens")
    need(isinstance(shots, dict) and 1 <= len(shots) <= 8 and "primary" in shots, "guest evidence required")
    for key in shots:
        need(re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", key), "invalid evidence role")
    by_role = {key: evidence(root, value, now) for key, value in shots.items()}
    need(len({e["sha256"] for e in by_role.values()}) == len(by_role), "duplicate evidence roles")
    return {"at": now.isoformat(), "binding": bound, "day": game_day(now),
            "desktop_state": review["desktop_state"], "package": review["package"],
            "maa_version": review["maa_version"], "facts": review["facts"], "screens": by_role}


def specific_review(item, stage, data, record):
    f = data["facts"]
    before = record["before"]["facts"] if record and stage == "verify" else None
    if item == "tea":
        tea_period = period(item, stamp(data["at"]))
        need(all(period(item, stamp(shot["captured_at"])) == tea_period for shot in data["screens"].values()),
             "tea evidence crosses actual 05:00 reset")
        need(f.get("recipe") == "红枣茶" and type(f.get("recipe_level")) is int and f["recipe_level"] == 4,
             "only the reviewed Lv4 red-date tea is covered")
        if stage == "reserve":
            need("confirm" in data["screens"] and f.get("confirmation_recipe") == f["recipe"]
                 and f.get("cost_reviewed_free") is True and f.get("fee_or_premium_prompt") is False
                 and type(f.get("free_uses_remaining")) is int and f["free_uses_remaining"] == 1,
                 "same named tea confirmation with one free use and no cost required")
        else:
            effect = f.get("effect_text")
            normalized = re.sub(r"[\s，,。]", "", unicodedata.normalize("NFKC", effect)) if isinstance(effect, str) else ""
            need("drink_effect" in data["screens"] and f.get("effect_type") == "饮品加成"
                 and normalized == "每消耗10情报拼图可获取2~3数据链路"
                 and f.get("cup_active_reviewed") is True and f.get("tea_task_progress") == "1/1",
                 "actual drink effect plus completed tea task required; cooking effect is not proof")
            if before:
                need(before.get("recipe") == f["recipe"], "result is not bound to the reserved beverage")
    if item == "sanity-event-stage":
        stage_id, mode = f.get("stage"), f.get("mode")
        need(isinstance(stage_id, str) and re.fullmatch(r"[A-Z]{1,5}-[1-9][0-9]{0,2}", stage_id)
             and stage_id != "TL-9" and mode == "native-auto-deploy"
             and isinstance(f.get("event"), str) and bool(f["event"].strip()),
             "exact normal event stage and native auto-deploy only; TL-9 has a separate item")
        opened, closed = stamp(f.get("battle_starts_at")), stamp(f.get("battle_ends_at"))
        at = stamp(data["at"])
        need(opened < closed and closed - opened <= dt.timedelta(days=31),
             "short explicit battle window required, not shop deadline")
        if stage == "reserve":
            need("event_window" in data["screens"] and opened <= at < closed,
                 "fresh stage/window screenshots required before actual battle deadline")
            need(0 <= (at - stamp(data["screens"]["event_window"]["captured_at"])).total_seconds() <= 300,
                 "event evidence is stale")
            need(integer(f.get("sanity_per_run"), 1) and integer(f.get("planned_runs"), 1)
                 and f["planned_runs"] <= 100 and integer(f.get("natural_sanity_before"), 1)
                 and f["planned_runs"] * f["sanity_per_run"] <= f["natural_sanity_before"]
                 and f.get("refill_or_retry") is False,
                 "bounded count and sufficient current natural sanity required, no refills")
        else:
            need("result" in data["screens"] and opened <= at and integer(f.get("completed_runs"), 1)
                 and integer(f.get("observed_sanity_spent"), 1),
                 "visible completion, run count and observed natural sanity cost required")
            if before:
                need(all(f.get(k) == before.get(k) for k in
                         ("stage", "mode", "event", "battle_starts_at", "battle_ends_at"))
                     and f["completed_runs"] == before["planned_runs"]
                     and f["observed_sanity_spent"] == f["completed_runs"] * before["sanity_per_run"],
                     "wrong stage/window/count/cost; inspect partial result without retry")
    if item == "daily-free-box":
        need(f.get("location") == ["商城", "品质甄选", "周期礼包", "每日礼包"] and
             f.get("product") == "每日补给箱" and f.get("price_text") == "免费" and
             type(f.get("price")) is int and f["price"] == 0 and integer(f.get("paid_balance")),
             "wrong daily free box, price or balance")
        if stage == "reserve":
            need(f.get("limit") == "日限购1/1" and f.get("control") == "购买", "daily box not eligible")
        else:
            need(f.get("limit") == "日限购0/1" and f.get("control") == "已售罄", "same daily box not exhausted")
            if before:
                need(f["paid_balance"] == before["paid_balance"] and "reward" in data["screens"],
                     "balance changed or reward overlay evidence missing")
    if item == "event-material":
        need(f.get("event") == "热寂悖论" and f.get("stage") == "DF-1-5 于乱流中 V" and
             f.get("material_mode") is True, "only the reviewed event/material stage is allowed")
        if stage == "reserve":
            need(stamp(data["at"]) < dt.datetime(2026, 11, 24, 8, 59, tzinfo=TZ),
                 "reviewed event battle deadline passed; no alternative event")
    if item == "squad-duty-supply":
        need(f.get("location") == ["班组", "补给", "分配中"] and f.get("product") == "要务补给·一"
             and f.get("source") == "委托触发" and isinstance(f.get("item_reference"), str)
             and bool(f["item_reference"].strip()), "wrong or ambiguous squad duty supply")
        need(f.get("claim_all") is False, "never claim all squad supply")
        if stage == "reserve":
            all_true(f, "selected_claim_available")
        else:
            need({"primary", "log"} <= data["screens"].keys(), "independent squad claim log frame required")
            if before:
                need(f["item_reference"] == before["item_reference"], "different squad supply item")
    if item in ("dispatch-stored-puzzle", "dispatch-production"):
        need(f.get("location") == ["委托", "每日订单", "调度室"], "wrong dispatch production/storage page")
        if item == "dispatch-stored-puzzle":
            need(f.get("selected_method") == "快速取出调度室储存情报拼图", "only the stored first option is allowed")
            for name in ("stored", "stamina", "stamina_capacity", "paid_balance"):
                need(integer(f.get(name)), "numeric storage, stamina, capacity and balance required")
            if stage == "reserve":
                need(f["stored"] > 0 and f["stamina"] + f["stored"] <= f["stamina_capacity"],
                     "stored withdrawal would overflow or nothing to withdraw")
            elif before:
                need(f["stored"] == 0 and f["stamina"] == before["stamina"] + before["stored"] and
                     f["stamina_capacity"] == before["stamina_capacity"] and
                     f["paid_balance"] == before["paid_balance"], "unexpected stored puzzle/stamina/balance delta")
        else:
            need(f.get("selected_method") == "资源生产" and f.get("price") == 0 and
                 type(f.get("price")) is int and integer(f.get("stored")), "only free storage production")
            if stage == "reserve":
                need(f["stored"] > 0, "nothing to collect")
            else:
                need(f["stored"] == 0 and "reward" in data["screens"], "production receipt and empty store required")
    if item == "weekly-free-box":
        need(f.get("location") == ["商城", "品质甄选", "臻品礼包", "主题精选"]
             and f.get("product") == "周周乐补给箱" and f.get("price_text") == "免费"
             and type(f.get("price")) is int and f["price"] == 0 and integer(f.get("paid_balance")),
             "wrong weekly box, price or balance")
        if stage == "reserve":
            need(f.get("limit") == "周限购1/1" and f.get("control") == "购买" and
                 f.get("progress") == f.get("goal") and integer(f.get("goal"), 1), "incorrect weekly-box eligibility")
        else:
            need(f.get("remaining") == 0 and type(f.get("remaining")) is int, "same weekly box not exhausted")
            if before:
                need(f["paid_balance"] == before["paid_balance"] and "reward" in data["screens"],
                     "balance changed or reward overlay evidence missing")
    if item.startswith("dispatch-weekly-"):
        need(type(f.get("tier")) is int and f["tier"] == int(item.rsplit("-", 1)[-1]),
             "wrong weekly dispatch tier")


def mutate(root, game, item, action, review, reason, now, *, authorize=require_execution, bind=binding):
    root = Path(root).resolve()
    need(item in ITEMS[game], "unknown item")
    authorize(game)
    need(not (root/"STOP").exists(), "STOP exists")
    if game == "endfield":
        raise Blocked("Endfield Android login/workflow not validated; plan/status only")
    with exclusive_lock(root/"state/pipeline.lock"):
        need(not (root/"STOP").exists(), "STOP exists")
        previous = load_record(root, game, item, now)
        path = path_for(root, game, item, now)
        if action == "mark-unknown":
            need(previous and previous["status"] == "reserved" and isinstance(reason, str)
                 and bool(reason.strip()), "mark-unknown requires a pending reservation and reason")
            previous.update(status="unknown", reason=reason.strip(), finished_at=now.isoformat())
            save(path, previous)
            return {"status": "unknown", "game_action_performed": False}
        obs = frame(root, review, game, item, now, bind(game),
                    close_result=(item == "close" and action != "reserve"))
        facts = obs["facts"]
        scope, result_checks = ITEMS[game][item]
        if action == "reserve":
            need(not previous or previous["status"] == "observed_ineligible",
                 "existing attempt or prior completion; inspect and do not replay")
            for other_game in ITEMS:
                for other_item in ITEMS[other_game]:
                    if (other_game, other_item) == (game, item):
                        continue
                    other = load_record(root, other_game, other_item, now)
                    need(not other or other["status"] != "reserved",
                         "another supervised item still reserved; finish or mark unknown first")
            all_true(facts, scope + " current_exact_item_eligible")
            if item == "breakthrough-sweep":
                for required in BEFORE_SWEEP:
                    r = load_record(root, game, required, now)
                    need(r and r["status"] in ("verified", "observed_already_done", "observed_ineligible"),
                         "review stored puzzle and production independently before sweeping")
            specific_review(item, action, obs, None)
            data = {"schema": 1, "game": game, "item": item, "period": period(item, now),
                    "status": "reserved", "before": obs, "history": previous.get("history", []) if previous else []}
        elif action == "verify":
            need(previous and previous["status"] == "reserved", "no matching reservation; never create success retroactively")
            start = previous["before"]
            need(start["binding"] == obs["binding"] and (item == "tea" or start["day"] == obs["day"]),
                 "reservation context changed")
            start_screens = start["screens"].values()
            for shot in obs["screens"].values():
                need(stamp(shot["captured_at"]) > stamp(start["at"]) and
                     shot["sha256"] not in {old["sha256"] for old in start_screens},
                     "fresh, distinct post-action evidence required")
            all_true(facts, result_checks)
            specific_review(item, action, obs, previous)
            data = {**previous, "status": "verified", "after": obs}
        elif action == "observe":
            need(not previous or previous["status"] == "observed_ineligible",
                 "existing attempt or terminal result cannot be replaced")
            outcome = review.get("observation")
            if outcome == "already_done":
                all_true(facts, scope + " " + result_checks + " prior_completion_visually_confirmed")
                specific_review(item, action, obs, None)
                status = "observed_already_done"
            else:
                allowed = set(SKIP.get(item, ()))
                need(outcome == "ineligible" and review.get("reason") in allowed, "unapproved skip or unknown state")
                all_true(facts, "exact_ineligibility_visually_confirmed")
                status = "observed_ineligible"
            data = {"schema": 1, "game": game, "item": item, "period": period(item, now),
                    "status": status, "observation": obs, "history": previous.get("history", []) if previous else []}
            if status == "observed_ineligible":
                data["reason"] = review["reason"]
                data["history"].append({"status": status, "reason": data["reason"], "screens": obs["screens"]})
        else:
            raise Blocked("unknown action")
        path.parent.mkdir(parents=True, exist_ok=True)
        save(path, data, exclusive=previous is None)
        return {"game": game, "item": item, "period": data["period"], "status": data["status"],
                "game_action_performed": False, "operator_must_recheck_live_scope": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "status", "reserve", "verify", "observe", "mark-unknown"))
    parser.add_argument("--game", choices=PACKAGES, required=True)
    parser.add_argument("--item")
    parser.add_argument("--review", type=Path)
    parser.add_argument("--reason")
    args = parser.parse_args(argv)
    try:
        now = dt.datetime.now(dt.timezone.utc)
        if args.action == "plan":
            result = route(args.game)
        elif args.action == "status":
            result = reported_state(ROOT, args.game, now)
        else:
            review = read_json(args.review) if args.review else {}
            result = mutate(ROOT, args.game, args.item, args.action, review, args.reason, now)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (Blocked, OSError, ValueError, KeyError, TypeError, RuntimeError, AttributeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "game_action_performed": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
