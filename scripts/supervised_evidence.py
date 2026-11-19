"""Shared offline evidence, durable journal and read-only foreground helpers."""
import contextlib, copy, ctypes, datetime as dt, hashlib, json, os, struct, uuid
from pathlib import Path

class Blocked(RuntimeError):
    pass


def stamp(value):
    try:
        result = dt.datetime.fromisoformat(value)
    except (ValueError, TypeError):
        raise Blocked("invalid evidence/review timestamp")
    if result.tzinfo is None:
        raise Blocked("timestamp must include timezone")
    return result


def need(condition, message):
    if not condition:
        raise Blocked(message)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def sha(data):
    return hashlib.sha256(data).hexdigest()


def contained(root, value):
    root = Path(root).resolve()
    p = Path(value)
    p = (p if p.is_absolute() else root / p).resolve()
    need(p.is_relative_to(root), "evidence/state path outside running copy")
    return p


def image_size(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) > 32 and data[12:16] == b"IHDR":
        need(data.endswith(b"IEND\xaeB\x60\x82"), "incomplete PNG")
        return struct.unpack(">II", data[16:24])
    need(data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9"), "PNG/JPEG evidence required")
    i = 2
    while i + 8 < len(data):
        need(data[i] == 255, "invalid JPEG segment")
        while i < len(data) and data[i] == 255:
            i += 1
        need(i < len(data), "truncated JPEG")
        tag = data[i]
        i += 1
        if tag in (0xD8, 0xD9) or 0xD0 <= tag <= 0xD7:
            continue
        length = int.from_bytes(data[i:i + 2], "big")
        need(length >= 2 and i + length <= len(data), "truncated JPEG segment")
        if tag in (0xC0, 0xC1, 0xC2):
            need(length >= 8, "invalid JPEG frame")
            return (int.from_bytes(data[i + 5:i + 7], "big"), int.from_bytes(data[i + 3:i + 5], "big"))
        need(tag != 0xDA, "JPEG frame header missing")
        i += length
    raise Blocked("image dimensions unavailable")


def current_window():
    """Read foreground identity only. Does not focus, resize, capture or send input."""
    need(os.name == "nt", "foreground verification requires Windows")
    from ctypes import wintypes as w
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user.GetForegroundWindow.restype = w.HWND
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    user.GetClientRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    hwnd = user.GetForegroundWindow()
    need(bool(hwnd), "no foreground window")
    pid = w.DWORD()
    need(bool(user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))), "window process unavailable")
    title = ctypes.create_unicode_buffer(512)
    user.GetWindowTextW(hwnd, title, len(title))
    rect = w.RECT()
    need(bool(user.GetClientRect(hwnd, ctypes.byref(rect))), "client dimensions unavailable")
    handle = kernel.OpenProcess(0x1000, False, pid.value)
    need(bool(handle), "cannot read foreground executable")
    try:
        name = ctypes.create_unicode_buffer(32768)
        length = w.DWORD(len(name))
        need(bool(kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(length))), "executable query failed")
    finally:
        kernel.CloseHandle(handle)
    need(user.GetForegroundWindow() == hwnd, "foreground changed while inspecting")
    return {"hwnd": int(hwnd), "pid": pid.value, "title": title.value,
            "executable": name.value, "client_size": [rect.right, rect.bottom], "foreground": True}


def seal(record):
    record = copy.deepcopy(record)
    record.pop("integrity_sha256", None)
    digest = sha(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf8"))
    return {**record, "integrity_sha256": digest}


@contextlib.contextmanager
def pipeline_lock(root):
    import msvcrt
    path = contained(root, "state/pipeline.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise Blocked("another daily pipeline is active")
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def save(path, record, exclusive=False):
    data = json.dumps(seal(record), ensure_ascii=False, indent=2).encode("utf8")
    if exclusive:
        with Path(path).open("xb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
    else:
        temp = Path(path).with_name(Path(path).name + ".tmp-" + uuid.uuid4().hex)
        with temp.open("xb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)


def verify_record_evidence(root, value):
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            path = contained(root, value["path"])
            need(path.is_file() and sha(path.read_bytes()) == value["sha256"], "recorded evidence missing or changed")
        for child in value.values():
            verify_record_evidence(root, child)
    elif isinstance(value, list):
        for child in value:
            verify_record_evidence(root, child)
