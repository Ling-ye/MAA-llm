"""Read-only audit for supervised GF2 additions, independent from legacy queues."""
import json
from pathlib import Path
import gf2_supervised_daily as journal
from gf2_daily_free_gift import POLICY as GIFT
from gf2_squad_daily import POLICIES as SQUAD
from gf2_dispatch_daily import POLICIES as DISPATCH, TIERS, weekly_policy
from gf2_heatdeath_supply import POLICY as EVENT

ROOT = Path(__file__).resolve().parent


def audit(root=ROOT):
    policies = [GIFT, *SQUAD.values(), *DISPATCH.values(), *(weekly_policy(n) for n in TIERS), EVENT]
    stages = []
    for policy in policies:
        try:
            record = journal.status(root, policy)
            state = record["status"]
            if state == "pending_observed":
                policy["validate_pending"](record["after"])
            elif state in ("manual_completion_recorded", "already_completed_observed"):
                policy["validate"](record["after"], "completed")
            stages.append({"phase": policy["phase"], "period_key": policy.get("period_key"),
                           "status": state,
                           "recorded_review": state in ("manual_completion_recorded", "already_completed_observed", "pending_observed"),
                           "action_claimed_by_script": False})
        except (journal.Blocked, OSError, ValueError, KeyError, TypeError) as error:
            stages.append({"phase": policy["phase"], "status": "blocked_evidence",
                           "recorded_review": False, "reason": str(error)})
    return {"game": "gf2", "game_day": journal.game_day(), "stages": stages,
            "all_requested_scopes_recorded": all(s["recorded_review"] for s in stages),
            "live_state_checked": False, "script_game_actions_executed": False}


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["all_requested_scopes_recorded"] else 2)
