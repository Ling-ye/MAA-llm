"""Supervised daily free supply box journal; never clicks a purchase control."""
from pathlib import Path
import gf2_supervised_daily as journal

ROOT = Path(__file__).resolve().parent
PRODUCT = "每日补给箱"


def validate(frame, state):
    n = journal.need
    n(frame.get("location") == ["商城", "品质甄选", "周期礼包", "每日礼包"], "not the daily store scope")
    n(frame.get("selected_tab") == frame.get("detail_product") == PRODUCT, "selected/detail product is not the daily free box")
    n(frame.get("period") == "daily", "weekly/event offer rejected")
    n(frame.get("daily_free_description_confirmed") is True, "daily free description not verified")
    n(frame.get("dialog_unambiguous") is True and frame.get("reward_overlay_visible") is False, "ambiguous/covered detail")
    n(frame.get("same_detail_price_and_control") is True, "price and control must belong to the selected product")
    n(frame.get("paid_offer_selected") is False, "paid offer selected")
    n(type(frame.get("price")) in (int, float) and frame["price"] == 0, "nonzero/ambiguous price")
    n(frame.get("currency") == "free" and frame.get("price_text") in ("免费", "0", "0.00"), "not a true free/zero offer")
    n(journal.integer(frame.get("balance")), "visible store balance must be recorded")
    n(journal.integer(frame.get("progress")) and frame["progress"] <= 21 and frame.get("progress_goal") == 21, "daily progress not verified")
    if state == "ready":
        n(frame.get("limit_text") == "日限购1/1" and type(frame.get("remaining")) is int and frame["remaining"] == 1, "already claimed or wrong limit")
        n(frame.get("control_text") == "购买" and frame.get("control_enabled") is True, "wrong selected purchase control")
    else:
        n(frame.get("limit_text") == "日限购0/1" and type(frame.get("remaining")) is int and frame["remaining"] == 0, "post-claim limit missing")
        n(frame.get("control_text") == "已售罄" and frame.get("control_enabled") is False, "same free box is not visibly sold out")


def pair(before, after):
    journal.need(before["balance"] == after["balance"], "store balance changed; inspect possible spending")
    journal.need(after["progress"] == before["progress"] + 1, "daily progress mismatch; rollover requires new review")


POLICY = {
    "phase": "daily-free-gift",
    "product": PRODUCT,
    "pins": {"resource/base/pipeline/public/PrepareDailyTasks/shop.json":
             "9ad582ce93597e25cd3a2893fcabe0207fbc691801813764a701c4f31eb1958e"},
    "blocked": ["周礼包", "活动礼包", "每日晶条礼包", "付费", "重复购买", "坐标点击", "旧混合商城队列"],
    "after_submission": "Only a supervisor may inspect the same free-box tab. Never press purchase again.",
    "validate": validate,
    "pair": pair,
}

if __name__ == "__main__":
    raise SystemExit(journal.cli(ROOT, POLICY))
