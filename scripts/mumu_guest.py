"""Allowlisted MuMu guest screen/input. Never talks to the Windows desktop."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import time
import uuid
import zlib

from project_paths import config_path, require_execution, resolve_user_path
from runner import exclusive_lock
from supervised_evidence import Blocked, contained, need, seal, sha, stamp, save

ROOT = Path(__file__).resolve().parent
PACKAGES = {"arknights": "com.hypergryph.arknights", "gf2": "com.Sunborn.SnqxExilium"}
TTL = 60
UP_TO = 24 * 1024 * 1024
PNG = b"\x89PNG\r\n\x1a\n"


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def checked_png(data, anchor=None):
    """Integrity/decode check for Android's 8-bit RGB/RGBA non-interlaced PNG."""
    need(isinstance(data, bytes) and 45 < len(data) <= UP_TO and data.startswith(PNG),
         "guest PNG missing or oversized")
    off, dims, stride, chunks, ended = 8, None, 0, [], False
    seen_idat, left_idat = False, False
    while off + 12 <= len(data):
        length = struct.unpack_from(">I", data, off)[0]
        end = off + 12 + length
        need(end <= len(data), "truncated guest PNG")
        tag = data[off+4:off+8]
        raw = data[off+8:end-4]
        need(zlib.crc32(data[off+4:end-4]) == struct.unpack_from(">I", data, end-4)[0],
             "guest PNG checksum mismatch")
        if tag == b"IHDR":
            need(off == 8 and length == 13, "invalid guest PNG header")
            w, h, bits, color, comp, fil, intr = struct.unpack(">IIBBBBB", raw)
            need(320 <= w <= 3840 and 180 <= h <= 2160 and w*9 == h*16 and
                 bits == 8 and color in (2, 6) and comp == fil == intr == 0,
                 "expected 16:9 8-bit Android RGB/RGBA PNG")
            dims, stride = (w, h), 4 if color == 6 else 3
        elif tag == b"IDAT":
            need(dims and not left_idat, "invalid guest PNG data order")
            seen_idat = True
            chunks.append(raw)
        elif tag == b"IEND":
            need(length == 0 and seen_idat and end == len(data), "invalid guest PNG end")
            ended = True
            break
        elif seen_idat:
            left_idat = True
        off = end
    need(ended, "incomplete guest PNG")
    w, h = dims
    anchor_digest = None
    anchor_pixels = set()
    if anchor is not None:
        need(isinstance(anchor,(tuple,list)) and len(anchor)==4 and
             all(type(k) is int for k in anchor),"invalid navigation anchor")
        x1,y1,x2,y2 = anchor
        need(0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h and x2-x1 >= 80 and y2-y1 >= 48 and
             (x2-x1)*(y2-y1) <= (w*h)//4, "anchor must cover a focused, bounded visible UI region")
        anchor_digest = hashlib.sha256()
    line = 1 + w * stride
    max_raw = line*h
    view = zlib.decompressobj()
    inflated = view.decompress(b"".join(chunks), max_raw+1)
    need(len(inflated) == max_raw and view.eof and not view.unused_data and not view.unconsumed_tail,
         "guest PNG pixel stream could not be decoded")
    need(all(inflated[y*line] in (0, 1, 2, 3, 4) for y in range(h)), "invalid guest PNG row")
    # Identify flat/blank frames using actual RGB pixels, not ancillary metadata.
    # Once two sampled pixels differ, no need to unfilter the remaining rows.
    previous = bytearray(w*stride)
    first = None
    contrasting = False
    for y in range(h):
        mode = inflated[y*line]
        pixels = bytearray(inflated[y*line+1:(y+1)*line])
        if mode:
            for x in range(len(pixels)):
                a = pixels[x-stride] if x >= stride else 0
                b = previous[x]
                c = previous[x-stride] if x >= stride else 0
                if mode == 1:
                    k = a
                elif mode == 2:
                    k = b
                elif mode == 3:
                    k = (a+b)//2
                else:
                    pa, pb, pc = abs(b-c), abs(a-c), abs(a+b-2*c)
                    k = a if pa <= pb and pa <= pc else b if pb <= pc else c
                pixels[x] = (pixels[x]+k) & 255
        if anchor is not None and y1 <= y < y2:
            crop = pixels[x1*stride:x2*stride]
            anchor_digest.update(crop)
            if len(anchor_pixels)<2:
                anchor_pixels.update(bytes(crop[x:x+3]) for x in range(0,len(crop),stride))
        if not contrasting and y % max(1,h//32) == 0:
            for x in range(0,w,max(1,w//32)):
                rgb = bytes(pixels[x*stride:x*stride+3])
                if first is None:
                    first = rgb
                elif first != rgb:
                    if anchor is None:
                        return list(dims)
                    contrasting = True
                    break
        if anchor is not None and contrasting and y >= y2-1:
            break
        previous = pixels
    need(contrasting and len(anchor_pixels) > 1,
         "guest PNG flat or blank, or navigation anchor has no visible contrast")
    return list(dims),anchor_digest.hexdigest()


def run(argv, timeout=8):
    try:
        return subprocess.run(argv, capture_output=True, check=True, timeout=timeout,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
        raise Blocked("ADB/MuMu command failed or timed out; inspect, do not fall back to PC")


def config(game):
    # Lazy import avoids a cycle when mumu_daily checks a guest proof.
    from mumu_daily import binding
    b = binding(game)
    setting = load(config_path("mumu-supervised.json"))
    tools = setting.get("guest_tools", {})
    if not tools and game == "arknights":
        tools = load(config_path("arknights.json"))
    result = {}
    for key, basename in (("mumu_cli", "mumu-cli.exe"), ("adb_path", "adb.exe")):
        raw = tools.get(key)
        need(isinstance(raw,str) and raw.strip(), f"configure local reviewed guest_tools.{key}")
        path = resolve_user_path(raw)
        need(path.is_file() and path.name.lower() == basename, f"review configured local {basename}")
        result[key] = str(path)
    return {**b, **result}


def stop(root):
    need(not (root/"STOP").exists(), "STOP exists")


def package_from_component(value):
    return value.split("/",1)[0]


def one_component(raw, label):
    lines = [line for line in raw.decode("utf8", errors="replace").splitlines() if label in line]
    values = {m for line in lines for m in re.findall(r"(?<![A-Za-z0-9_.$])([A-Za-z][A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+)", line)}
    need(len(values) == 1, "guest foreground/focus ambiguous")
    return next(iter(values))


class Guest:
    def __init__(self, root, game, cfg, *, command=run):
        self.root, self.game, self.cfg, self.command = Path(root).resolve(), game, cfg, command
        self.package = PACKAGES[game]
        from project_paths import is_loopback_adb_serial
        need(is_loopback_adb_serial(cfg["serial"]) and type(cfg["vm_index"]) is int and cfg["vm_index"] >= 0,
             "missing exact configured loopback instance")

    def adb(self, *args):
        stop(self.root)
        # No default serial, implicit connect/start, host desktop, shell string or fallback.
        return self.command([self.cfg["adb_path"], "-s", self.cfg["serial"], *args])

    def identity(self):
        stop(self.root)
        data = json.loads(self.command([self.cfg["mumu_cli"], "info", "-v", str(self.cfg["vm_index"])]))
        need(isinstance(data,dict) and data.get("is_android_started") is True and
             f'{data.get("adb_host_ip")}:{data.get("adb_port")}' == self.cfg["serial"],
             "configured MuMu instance is not ready or maps to a different serial")
        need(self.adb("get-state").strip() == b"device", "ADB device is not already online")
        paths = self.adb("shell","pm","path",self.package).decode("utf8", errors="replace")
        need(any(s.startswith("package:/") for s in paths.splitlines()), "official guest package missing")
        resumed = one_component(self.adb("shell","dumpsys","activity","activities"), "topResumedActivity")
        focus = one_component(self.adb("shell","dumpsys","window","displays"), "mCurrentFocus")
        need(package_from_component(resumed) == package_from_component(focus) == self.package,
             "official target package is not both resumed and focused in guest")
        pid = self.adb("shell","pidof",self.package).decode("ascii").strip()
        boot = self.adb("shell","cat","/proc/sys/kernel/random/boot_id").decode("ascii").strip()
        need(re.fullmatch(r"[1-9][0-9]{0,9}",pid) and re.fullmatch(r"[0-9a-f-]{36}",boot),
             "guest process or boot identity ambiguous")
        need(str(uuid.UUID(boot)) == boot, "invalid guest boot identity")
        return {"game": self.game, "package": self.package, "serial": self.cfg["serial"],
                "vm_index": self.cfg["vm_index"], "activity": resumed, "focus": focus, "pid": int(pid),
                "boot": boot}

    def capture(self):
        before = self.identity()
        start = time.monotonic()
        data = self.adb("exec-out","screencap","-p")
        at = utcnow()
        size = checked_png(data)
        need(self.identity() == before, "guest instance or app changed during capture")
        need(time.monotonic()-start < TTL, "guest frame is no longer fresh")
        stop(self.root)
        return before, data, at, size


def rel(root,path):
    return path.relative_to(root).as_posix()


def record_frame(root, captured, anchor=None):
    identity, image, at, size = captured
    directory = contained(root,"evidence/guest")
    directory.mkdir(parents=True,exist_ok=True)
    tag = uuid.uuid4().hex
    picture = directory/(tag+".png")
    doc = directory/(tag+".json")
    with picture.open("xb") as out:
        out.write(image)
    body = {"schema": 1, "transport":"mumu-adb", "identity":identity, "captured_at":at.isoformat(),
            "frame":{"path":rel(root,picture),"sha256":sha(image),"raw_size":size}}
    if anchor is not None:
        _, digest = checked_png(image,anchor)
        body["navigation_anchor"] = {"rect":anchor,"pixel_sha256":digest}
    save(doc, body, exclusive=True)
    return {"probe": rel(root,doc), "frame": body["frame"], "captured_at": body["captured_at"],
            **({"navigation_anchor":body["navigation_anchor"]} if anchor is not None else {})}


def proof(root, receipt, game, bound, now):
    p = contained(root,receipt)
    need(p.is_relative_to(contained(root,"evidence/guest")) and p.suffix == ".json" and
         p.stat().st_size <= 64*1024, "guest probe must be a local generated receipt")
    body = load(p)
    need(seal(body) == body and body.get("schema") == 1 and body.get("transport") == "mumu-adb",
         "invalid guest probe integrity")
    identity = body["identity"]
    need(identity.get("game") == game and identity.get("package") == PACKAGES[game] and
         identity.get("serial") == bound["serial"] and identity.get("vm_index") == bound["vm_index"] and
         all(package_from_component(identity[key])==PACKAGES[game] for key in ("activity","focus")) and
         type(identity.get("pid")) is int and identity["pid"] > 0 and
         str(uuid.UUID(identity["boot"])) == identity["boot"], "guest probe identity mismatched")
    age = (now-stamp(body["captured_at"])).total_seconds()
    need(0 <= age <= TTL, "guest probe expired; capture new evidence")
    image = contained(root,body["frame"]["path"])
    need(image.is_relative_to(p.parent) and image.suffix == ".png" and image.stat().st_size <= UP_TO,
         "guest probe has an unexpected image path")
    raw = image.read_bytes()
    need(sha(raw) == body["frame"]["sha256"] and checked_png(raw) == body["frame"]["raw_size"],
         "guest probe PNG changed")
    if "navigation_anchor" in body:
        anchor=body["navigation_anchor"]
        _, digest=checked_png(raw,anchor["rect"])
        need(digest == anchor["pixel_sha256"],"guest navigation anchor changed")
    return body


def unresolved(root):
    return contained(root, "state/guest-steps/gf2-last.json")


def guard_replay(root):
    if unresolved(root).exists():
        prior = load(unresolved(root))
        need(seal(prior) == prior and prior.get("status") in ("captured_unverified","acknowledged_no_replay"),
             "previous guest input unconfirmed; no new gesture/attempt until reconciled")


def acknowledge(root, guest, receipt, reason, reviewed, authorize):
    need(guest.game == "gf2" and reviewed and isinstance(reason,str) and reason.strip(),
         "acknowledgment needs GF2, a reviewed new frame and a factual reason")
    authorize(guest.game)
    with exclusive_lock(root/"state/pipeline.lock"):
        stop(root)
        prior = load(unresolved(root))
        need(seal(prior)==prior and prior.get("status") in ("reserved_no_replay","unknown_after_submission"),
             "no unresolved guest submission")
        new = proof(root,receipt,guest.game,guest.cfg,utcnow())
        need(new["integrity_sha256"] != prior["probe_sha256"] and
             stamp(new["captured_at"]) > stamp(prior["submitted_at"]) and
             guest.identity() == new["identity"], "review the target's newly verified current frame")
        if prior.get("item"):
            from mumu_daily import load_record
            current = load_record(root,"gf2",prior["item"],utcnow())
            need(current and current.get("status") in ("unknown","verified"),
                 "reconcile the daily item first; keep an unknown attempt unreplayable")
        stop(root)
        save(unresolved(root), {**prior,"status":"acknowledged_no_replay","reason":reason.strip(),
                                "acknowledged_probe": new["integrity_sha256"]})
        return {"status":"acknowledged_no_replay","game_action_performed":False}


def gesture(root, guest, action, receipt, xy, *, reviewed, navigation, item, authorize=require_execution):
    need(guest.game == "gf2" and reviewed, "only explicitly reviewed GF2 guest gestures are enabled")
    need(bool(navigation) != bool(item), "choose non-spending navigation or a reserved daily item")
    authorize(guest.game)
    with exclusive_lock(root/"state/pipeline.lock"):
        stop(root)
        expected = proof(root,receipt,guest.game,guest.cfg,utcnow())
        guard_replay(root)
        if item:
            from mumu_daily import ITEMS, load_record
            need(item in ITEMS["gf2"], "unknown daily item")
            row = load_record(root,"gf2",item,utcnow())
            before = row.get("before", {}) if row else {}
            need(row and row.get("status") == "reserved" and before.get("binding") ==
                 {"vm_index":guest.cfg["vm_index"],"serial":guest.cfg["serial"]},
                 "mutating daily item requires its existing matching reservation")
            if before.get("guest_identity"):
                need(before["guest_identity"] == expected["identity"],
                     "guest identity changed since item reservation")
        else:
            from mumu_daily import ITEMS, load_record
            need(not any((load_record(root,"gf2",name,utcnow()) or {}).get("status") == "reserved"
                         for name in ITEMS["gf2"]), "finish the reserved GF2 item before unscoped navigation")
        current = guest.capture()
        ident, image, _, size = current
        need(ident == expected["identity"] and size == expected["frame"]["raw_size"],
             "guest state or frame changed; capture and review again")
        anchor = expected.get("navigation_anchor")
        if anchor is not None:
            need(navigation and not item, "pixel anchor is for non-spending navigation only")
            _, current_digest = checked_png(image,anchor["rect"])
            need(current_digest == anchor["pixel_sha256"],
                 "reviewed navigation anchor changed; capture a new frame")
        else:
            need(sha(image) == expected["frame"]["sha256"],
                 "guest state or frame changed; capture and review again")
        age = (utcnow()-stamp(expected["captured_at"])).total_seconds()
        need(0 <= age <= TTL,"guest probe expired; capture new evidence")
        w,h = size
        n = 2 if action == "tap" else 5
        need(len(xy) == n and all(type(k) is int for k in xy), "invalid raw gesture arguments")
        points = xy[:2] if action == "tap" else xy[:4]
        need(all(0 <= k < (w if i%2==0 else h) for i,k in enumerate(points)),
             "gesture outside guest frame")
        need(action == "tap" or 100 <= xy[4] <= 3000, "swipe duration outside reviewed bound")
        if anchor is not None:
            x1,y1,x2,y2 = anchor["rect"]
            need(all(x1 <= x < x2 and y1 <= y < y2 for x,y in zip(points[::2],points[1::2])),
                 "gesture must stay inside reviewed navigation anchor")
        used = contained(root,"state/guest-steps/"+expected["integrity_sha256"]+".json")
        used.parent.mkdir(parents=True,exist_ok=True)
        stop(root)
        submission = {"status":"reserved_no_replay", "action":action, "game":guest.game,
                      "item":item, "probe_sha256":expected["integrity_sha256"],
                      "submitted_at":utcnow().isoformat()}
        save(used, submission, exclusive=True)
        save(unresolved(root), submission)
        try:
            need(guest.identity() == ident, "official app changed just before input")
            guest.adb("shell","input",action,*(str(i) for i in xy))
            time.sleep(0.5)
            later = guest.capture()
            need(later[0] == ident, "target changed after guest input")
            outcome = record_frame(root,later)
            save(unresolved(root),{**submission,"status":"captured_unverified","after_probe":outcome["probe"]})
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError, Blocked, zlib.error):
            # The durable pre-input latch stays non-replayable even if updating it fails.
            try:
                save(unresolved(root),{**submission,"status":"unknown_after_submission"})
            except OSError:
                pass
            return {"status":"unknown_after_submission", "game_action_performed":None, "do_not_retry":True}
        return {**outcome,"status":"input_sent_effect_unverified","game_action_performed":True}


def main(argv=None, *, root=ROOT, load_config=config, command=run, authorize=require_execution):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("probe","tap","swipe","acknowledge"))
    p.add_argument("--game", choices=(*PACKAGES,"endfield"), required=True)
    p.add_argument("--probe-proof")
    p.add_argument("--reviewed-frame", action="store_true")
    choice = p.add_mutually_exclusive_group()
    choice.add_argument("--navigation",action="store_true",help="supervised non-spending navigation only")
    choice.add_argument("--item",help="existing reserved daily item")
    p.add_argument("--xy",type=int,nargs="+")
    p.add_argument("--anchor",type=int,nargs=4,metavar=("X1","Y1","X2","Y2"),
                   help="probe an area for reviewed non-spending navigation only")
    p.add_argument("--reason")
    a=p.parse_args(argv)
    try:
        need(a.game in PACKAGES,"Endfield PC is not a MuMu guest; no ADB route enabled")
        root=Path(root).resolve()
        stop(root)
        guest=Guest(root,a.game,load_config(a.game),command=command)
        if a.action == "probe":
            need(not (a.probe_proof or a.reviewed_frame or a.navigation or a.item or a.xy or a.reason),
                 "probe never accepts input arguments")
            result={**record_frame(root,guest.capture(),a.anchor),"status":"guest_frame_ready_not_game_verification",
                    "game_action_performed":False}
        elif a.action == "acknowledge":
            need(a.probe_proof and not (a.xy or a.item or a.navigation or a.anchor),
                 "acknowledgment takes a fresh probe and reason, never input")
            result=acknowledge(root,guest,a.probe_proof,a.reason,a.reviewed_frame,authorize)
        else:
            need(a.probe_proof and a.xy and not (a.reason or a.anchor), "gesture requires reviewed probe and raw coordinates")
            result=gesture(root,guest,a.action,a.probe_proof,a.xy,reviewed=a.reviewed_frame,
                           navigation=a.navigation,item=a.item,authorize=authorize)
        print(json.dumps(result,ensure_ascii=False))
        return 3 if result.get("status") == "unknown_after_submission" else 0
    except (Blocked, OSError, ValueError, TypeError, KeyError, RuntimeError, AttributeError, zlib.error) as exc:
        print(json.dumps({"status":"blocked","reason":str(exc),"game_action_performed":False},ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
