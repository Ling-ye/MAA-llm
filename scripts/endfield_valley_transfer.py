"""Valley depot supervision journal. Never starts tasks, packs cargo or clicks UI."""
import argparse
import datetime as dt
import json
from pathlib import Path
import supervised_evidence as e

ROOT = Path(__file__).resolve().parent
NODES = {"OriginiumSciencePark": "源石研究园", "OriginLodespring": "矿脉源区", "PowerPlateau": "供能高地"}
ITEMS = {"精选养愈胶囊", "蓝铁装备原件"}
VERSION = "v3.1.0"
OPEN = ("manual_pack_reserved", "quote_recorded", "manual_transfer_reserved")


def now():
    return dt.datetime.now(dt.timezone.utc)


def day(moment=None):
    value = moment or now()
    e.need(value.tzinfo is not None, "timezone required")
    return (value.astimezone(dt.timezone(dt.timedelta(hours=8))) - dt.timedelta(hours=4)).date().isoformat()


def path(root, node, moment=None):
    e.need(node in NODES, "only the three Valley depots are in scope")
    return e.contained(root, f"state/endfield-valley-{day(moment)}-{node}.attempt.json")


def check_frame(root, frame, node, moment, fresh=False):
    e.need(isinstance(frame, dict) and frame.get("schema") == 1 and frame.get("game") == "endfield", "wrong review schema")
    e.need(frame.get("version") == VERSION and frame.get("framework") == "v5.16.1", "unreviewed version")
    e.need(frame.get("game_day") == day(moment) and frame.get("supervised") is True, "current game day and supervision required")
    e.need(frame.get("region") == "valleyiv" and frame.get("node") == node
           and frame.get("node_name") == NODES[node], "region/depot identity mismatch")
    e.need(frame.get("dialog_unambiguous") is True and frame.get("node_order_bound") is True, "ambiguous node/order binding")
    e.need(isinstance(frame.get("order_reference"), str) and frame["order_reference"].strip(), "visible order reference required")
    e.need(frame.get("navigation_or_acceptance") is False and frame.get("tail_claim_action") is False, "navigation/acceptance/tail claim prohibited")
    reviewed = e.stamp(frame.get("reviewed_at"))
    extra = frame.get("supporting_evidence", {})
    e.need(isinstance(extra, dict) and len(extra) <= 8, "invalid extra evidence")
    for image in [frame.get("evidence", {}), *extra.values()]:
        e.need(isinstance(image, dict) and isinstance(image.get("path"), str), "image evidence required")
        p = e.contained(root, image["path"])
        e.need(p.is_file() and p.stat().st_size <= 16*1024*1024, "missing/oversized image")
        data = p.read_bytes()
        e.need(e.sha(data) == image.get("sha256") and e.image_size(data) == (1280, 720), "image hash/size mismatch")
        captured = e.stamp(image.get("captured_at"))
        e.need(day(captured) == day(moment) and captured <= reviewed <= moment, "wrong image day or timestamp order")
        if fresh:
            modified = dt.datetime.fromtimestamp(p.stat().st_mtime, dt.timezone.utc)
            e.need(0 <= (moment-captured).total_seconds() <= 300 and (moment-reviewed).total_seconds() <= 300
                   and 0 <= (moment-modified).total_seconds() <= 300, "stale review/evidence")
    return frame


def cargo(frame):
    e.need(frame.get("item_name") in ITEMS and frame.get("item_hover_verified") is True, "material identity not confirmed by hover")
    e.need(frame.get("quantity_and_stock_same_item") is True, "quantity/stock not bound to the selected material")
    for key in ("quantity", "stock_quantity", "capacity", "item_volume"):
        e.need(e.integer(frame.get(key)), "missing numeric cargo/stock information")
    e.need(1 <= frame["quantity"] <= 6000 and 1 <= frame["capacity"] <= 100000 and frame["item_volume"] >= 1,
           "cargo exceeds the reviewed limits")
    e.need(frame["quantity"] * frame["item_volume"] == frame["capacity"], "cargo is not exactly full; do not refill/retry")
    e.need("item_identity" in frame.get("supporting_evidence", {}), "material hover evidence required")
    e.need(frame.get("stock_basis") in ("available_before_packing", "remaining_after_packing"), "stock basis unclear")
    if frame["order_state"] == "ready_to_pack":
        e.need(frame["stock_basis"] == "available_before_packing" and frame["stock_quantity"] >= frame["quantity"], "low stock cannot fill this order")
    else:
        e.need(frame["stock_basis"] == "remaining_after_packing" and frame.get("packed_quantity") == frame["quantity"],
               "existing quote must refer to already packed cargo, not another packing attempt")


def ready(frame):
    e.need(frame.get("order_state") in ("ready_to_pack", "quoted_unpublished"), "unknown/partial/published order cannot be resubmitted")
    cargo(frame)
    e.need(frame.get("already_published") is False and frame.get("paid_resources") is False, "already published or paid action")
    e.need(frame.get("control_enabled") is True, "control unavailable")
    if frame["order_state"] == "ready_to_pack":
        e.need(frame.get("existing_quote") is False and frame.get("control_text") == "下一步", "existing quote must be reused; next step creates an offer")
        e.need(frame.get("next_step_has_side_effect") is True, "next step is not a harmless preview")
    else:
        e.need(frame.get("existing_quote") is True and frame.get("quote_bound_to_cargo") is True, "quote/cargo binding missing")
        e.need(frame.get("control_text") == "快速转交" and frame.get("control_color") == "white", "only the explicit white quick-transfer control is permitted")
        e.need(frame.get("yellow_start_transport_selected") is False, "yellow start transport is prohibited")


def posted(frame):
    e.need(frame.get("panel_title") == "我转交的委托" and frame.get("order_state") == "posted_waiting", "transferred-order page required")
    e.need(frame.get("publish_text") == "已发布" and frame.get("acceptance_text") == "等待接单中", "published and waiting must both be confirmed")
    e.need(frame.get("tail_payment_received") is False and frame.get("tail_state") == "pending_acceptance", "waiting is not paid tail income")
    e.need(isinstance(frame.get("expiry_text"), str) and frame["expiry_text"].strip(), "record actual expiry text or explicitly not shown")
    e.need(frame.get("deposit_observed") is False or e.integer(frame.get("deposit_amount")), "deposit must be separately observed")
    if frame.get("deposit_observed") is True:
        e.need("deposit" in frame.get("supporting_evidence", {}), "deposit evidence required")


def same_order(before, after, require_cargo=False):
    for key in ("node", "region", "order_reference"):
        e.need(before[key] == after[key], "order identity changed")
    if require_cargo:
        for key in ("item_name", "quantity", "capacity", "item_volume"):
            e.need(before[key] == after[key], "cargo changed after the reserved review")
    e.need(e.stamp(before["evidence"]["captured_at"]) < e.stamp(after["evidence"]["captured_at"])
           and before["evidence"]["sha256"] != after["evidence"]["sha256"], "new ordered evidence required")


def legacy_guard(root, node, moment):
    state = Path(root)/"state"
    names = [f"endfield-extras-{day(moment)}-delivery.valleyiv.{node}.0.attempt.json*",
             f"endfield-regional-{day(moment)}-delivery-jobs-valleyiv.attempt.json*"]
    e.need(not any(list(state.glob(name)) for name in names), "legacy node/region attempt exists; do not replay")
    # Existing ad-hoc summaries can be named after midnight: inspect their recorded game day.
    for run in (Path(root)/"runs").glob("endfield-extra-*"):
        files = [run] if run.is_file() else list(run.glob("*.json"))
        for f in files:
            if f.suffix != ".json": continue
            try: value = json.loads(f.read_text(encoding="utf-8-sig"))
            except (ValueError, OSError):
                raise e.Blocked("unreadable legacy extra receipt; inspect before reserving")
            value_day = value.get("game_day", value.get("day"))
            e.need(value_day != day(moment), "same-day legacy extra receipt exists; inspect instead of replaying")
            if not value_day:
                e.need(day(moment).replace("-", "") not in str(f), "same-day unclassified legacy receipt")


def live_preflight(root, node, frame, moment, base, game_exe, inspect):
    e.need(not (Path(root)/"STOP").exists(), "STOP exists")
    legacy_guard(root, node, moment)
    e.need(base is not None, "--base required")
    manifest = json.loads((Path(base)/"interface.json").read_text(encoding="utf-8-sig"))
    e.need(manifest.get("version") == VERSION, "MaaEnd installation version changed")
    e.need(game_exe is not None and Path(game_exe).name.lower() == "endfield.exe", "exact game executable required")
    expected = Path(game_exe).resolve()
    def check():
        actual = inspect(); declared = frame.get("window", {})
        e.need(actual.get("foreground") is True and declared.get("foreground") is True, "game not foreground")
        for key in ("hwnd", "pid"):
            e.need(e.integer(declared.get(key), 1) and declared[key] == actual.get(key), "window/process changed")
        e.need("终末地" in actual.get("title", "") and "MAA" not in actual.get("title", "").upper(), "wrong game title")
        e.need(actual.get("title") == declared.get("title") and actual.get("client_size") == declared.get("client_size") == [1280, 720], "title/client area mismatch")
        e.need(Path(actual.get("executable", "")).resolve() == expected == Path(declared.get("executable", "")).resolve(), "executable mismatch")
        return actual
    first = check();e.need(check() == first, "foreground switched during reservation")


def read_record(target, node, moment):
    value = json.loads(target.read_text(encoding="utf8"))
    e.need(value.get("integrity_sha256") == e.seal(value)["integrity_sha256"], "ledger integrity mismatch")
    e.need(value.get("game") == "endfield" and value.get("node") == node and value.get("game_day") == day(moment), "ledger scope mismatch")
    return value


def status(root=ROOT, node=None, moment=None):
    moment = moment or now();rows=[]
    for key in ([node] if node else NODES):
        target=path(root,key,moment)
        if not target.exists(): rows.append({"node":key,"status":"not_recorded","replay_safe":False});continue
        r=read_record(target,key,moment);e.verify_record_evidence(root,r)
        rows.append({"node":key,"status":r["status"],"order_state":r.get("latest",{}).get("order_state"),
                     "tail_payment_received":False,"script_executed_game_action":False})
    return {"game":"endfield","game_day":day(moment),"nodes":rows,"live_state_checked":False}


def record(root,node,action,review=None,base=None,game_exe=None,reason=None,moment=None,inspect=e.current_window):
    moment=moment or now();target=path(root,node,moment)
    with e.pipeline_lock(root):
        updating=action in ("record-quote","reserve-transfer","verify","mark-unknown")
        if updating:
            e.need(target.exists(),"original reservation missing")
            r=read_record(target,node,moment)
            e.verify_record_evidence(root,r)
            e.need(r["status"] in OPEN,"terminal/unknown attempt cannot be replayed")
        else:
            e.need(not list(target.parent.glob(target.name+'*')),"node already attempted this game day")
            r={"schema":1,"game":"endfield","game_day":day(moment),"node":node,"version":VERSION,
               "script_executed_game_action":False,"automation_live_validated":False,"tail_payment_received":False,"events":[]}
        if action=="mark-unknown":
            e.need(isinstance(reason,str) and reason.strip(),"reason required")
            r.update(status="submission_unknown",reason=reason)
        else:
            frame=check_frame(root,review,node,moment,fresh=action in ("reserve","reserve-transfer"))
            if action in ("reserve","reserve-transfer"):
                ready(frame)
                if action=="reserve-transfer":
                    e.need(r["status"]=="quote_recorded" and frame["order_state"]=="quoted_unpublished","quote reservation out of order")
                    same_order(r["latest"],frame,True)
                live_preflight(root,node,frame,moment,base,game_exe,inspect)
                r["status"]="manual_pack_reserved" if frame["order_state"]=="ready_to_pack" else "manual_transfer_reserved"
                r.setdefault("before",frame)
            elif action=="record-quote":
                e.need(r["status"]=="manual_pack_reserved" and frame.get("order_state")=="quoted_unpublished","quote step out of order; do not pack an existing quote")
                ready(frame);same_order(r["latest"],frame,True)
                e.need(r["latest"]["stock_quantity"]-r["latest"]["quantity"]==frame["stock_quantity"],"stock delta does not match the reserved cargo")
                r["status"]="quote_recorded"
            elif action in ("verify","observe"):
                posted(frame)
                if action=="verify":
                    e.need(r["status"]=="manual_transfer_reserved","transfer was not reserved")
                    same_order(r["latest"],frame)
                r["status"]="manual_transferred_pending" if action=="verify" else "already_transferred_observed"
            elif action=="observe-blocked":
                e.need(frame.get("order_state") in ("low_stock","partially_packed","unknown"),"explicit blocked order state required")
                e.need(isinstance(frame.get("blocked_reason"),str) and frame["blocked_reason"].strip(),"blocked reason required")
                r["status"]="blocked_observed"
            else: raise e.Blocked("unsupported journal action")
            r["latest"]=frame
        r["events"].append({"action":action,"at":moment.isoformat(),"status":r["status"],"evidence":review if review else None})
        e.save(target,r,exclusive=not updating)
        return e.seal(r)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node',choices=tuple(NODES));m=parser.add_mutually_exclusive_group()
    actions=('status','reserve','record-quote','reserve-transfer','verify','observe','observe-blocked','mark-unknown','execute')
    for action in actions:m.add_argument('--'+action,action='store_true')
    parser.add_argument('--review',type=Path);parser.add_argument('--base',type=Path);parser.add_argument('--game-exe',type=Path);parser.add_argument('--reason')
    args=parser.parse_args(argv)
    try:
        if args.execute:raise e.Blocked('No automatic game input backend. Supervised journal only; no task submitted.')
        action=next((a for a in actions if getattr(args,a.replace('-','_'))),None)
        if action=='status':out=status(ROOT,args.node)
        elif action is None:
            out={'game':'endfield','nodes':NODES,'automatic_execution':False,'default':'offline_plan',
                 'steps':['inspect node/order/material/stock','reserve before packing next step','reuse an existing quote','reserve transfer once','manually use white quick transfer','verify published and waiting'],
                 'forbidden':['yellow start transport','navigation','tail claim','repack an existing quote','retry unknown submission']}
        else:
            e.need(args.node is not None,'--node required')
            review=None
            if action!='mark-unknown':
                e.need(args.review is not None,'--review required');review=json.loads(args.review.read_text(encoding='utf-8-sig'))
            out=record(ROOT,args.node,action,review,args.base,args.game_exe,args.reason)
        print(json.dumps(out,ensure_ascii=False,indent=2));return 0
    except (e.Blocked,OSError,ValueError,KeyError,TypeError) as error:
        print(json.dumps({'status':'blocked','reason':str(error),'script_executed_game_action':False},ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())
