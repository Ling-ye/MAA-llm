import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from endfield_mxu_port import discover, owner_ports

TABLE = """
TCP 127.0.0.1:12701 0.0.0.0:0 LISTENING 27540
TCP 127.0.0.1:12702 0.0.0.0:0 LISTENING 17368
TCP 127.0.0.1:12703 127.0.0.1:51000 ESTABLISHED 17368
TCP 0.0.0.0:12704 0.0.0.0:0 LISTENING 17368
TCP 127.0.0.1:60100 0.0.0.0:0 LISTENING 17368
"""


class TestMXULoopback(unittest.TestCase):
    def test_only_target_owner_and_loopback_listeners(self):
        self.assertEqual(owner_ports(TABLE, 17368, 12701), [12702])

    def test_only_contacts_listener_owned_by_latest_pid(self):
        calls = []
        def request(port, path):
            calls.append((port, path))
            return {"initialized": True, "version": "v6.0.0-beta.3"}
        self.assertEqual(discover(TABLE, 17368, 12701, request),
                         {"port": 12702, "framework": "v6.0.0-beta.3"})
        self.assertEqual(calls, [(12702, "/maa/initialized")])

    def test_fails_closed_if_ambiguous_or_bad_response(self):
        table = TABLE + "TCP 127.0.0.1:12705 0.0.0.0:0 LISTENING 17368\n"
        with self.assertRaises(RuntimeError):
            discover(table, 17368, 12701, lambda *_: {"initialized": True, "version": "v1"})
        with self.assertRaises(RuntimeError):
            discover(TABLE, 17368, 12701, lambda *_: ["not an API"])

    def test_refuses_invalid_pid(self):
        with self.assertRaises(ValueError):
            owner_ports(TABLE, 0, 12701)
