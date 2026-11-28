"""Read-only discovery of the installed MaaEnd MXU loopback API.

A reachable MXU is transport evidence, not authorization for gameplay. Unknown
versions still require a separate resource and task safety review.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.request
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def owner_ports(netstat: str, pid: int, default: int, fallback_count: int = 10):
    if type(pid) is not int or pid <= 0 or not 1 <= default <= 65535:
        raise ValueError("Expected a positive verified MaaEnd PID and valid port")
    ports = set()
    for line in netstat.splitlines():
        cols = line.split()
        if len(cols) != 5 or cols[0] != "TCP" or cols[-1] != str(pid):
            continue
        host, sep, port = cols[1].rpartition(":")
        if host != "127.0.0.1" or not sep or cols[2] != "0.0.0.0:0" or not port.isascii() or not port.isdigit():
            continue
        port = int(port)
        if default <= port <= min(65535, default + fallback_count):
            ports.add(port)
    return sorted(ports)


def localhost_json(port, path, body=None, method=None, binary=False):
    if not 1 <= port <= 65535 or not path.startswith("/") or ".." in path or path.startswith("//"):
        raise ValueError("Expected a bounded loopback API route")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api{path}", data,
        {"Content-Type": "application/json"}, method=method,
    )
    with opener.open(req, timeout=12) as res:
        return res.read() if binary else json.load(res)


def discover(netstat: str, pid: int, default: int, request=localhost_json):
    matches = []
    for port in owner_ports(netstat, pid, default):
        try:
            v = request(port, "/maa/initialized")
            if isinstance(v, dict) and v.get("initialized") is True and isinstance(v.get("version"), str) and v["version"]:
                matches.append({"port": port, "framework": v["version"]})
        except (OSError, ValueError):
            pass  # An unhealthy listener does not prove its version.
    if len(matches) != 1:
        raise RuntimeError("Expected one healthy initialized MXU listener owned by the verified PID")
    return matches[0]


def netstat_snapshot():
    exe = Path(os.environ["SystemRoot"]) / "System32" / "netstat.exe"
    return subprocess.check_output([str(exe), "-ano", "-p", "TCP"], text=True, errors="replace", timeout=8)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--app", required=True, type=Path, help="Installed MaaEnd application directory")
    p.add_argument("--pid", required=True, type=int, help="Freshly verified PID of that MaaEnd process")
    args = p.parse_args()
    try:
        app = args.app.resolve(strict=True)
        manifest = json.loads((app / "interface.json").read_text(encoding="utf-8-sig"))
        config = json.loads((app / "config" / "mxu-MaaEnd.json").read_text(encoding="utf-8-sig"))
        settings = config["settings"]
        if settings.get("webServerEnabled") is not True:
            raise RuntimeError("MaaEnd loopback server is disabled; no settings changed")
        status = discover(netstat_snapshot(), args.pid, int(settings.get("webServerPort", 12701)))
        state = localhost_json(status["port"], "/maa/state")["instances"]
        print(json.dumps({"status": "transport_only", "maaend": manifest["version"],
                          "pid": args.pid, **status, "busy": any(x.get("is_running") for x in state.values())}))
        return 0
    except (OSError, KeyError, ValueError, RuntimeError) as e:
        print(json.dumps({"status": "blocked", "reason": str(e)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
