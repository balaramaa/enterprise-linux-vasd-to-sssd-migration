import importlib.util
import os
import pwd
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "ansible" / "files" / "snapshot_identities.py"
spec = importlib.util.spec_from_file_location("snapshot_identities", SCRIPT)
snap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snap)

LAST_OUTPUT = """\
alice    pts/0        10.0.0.5         Mon Oct  2 09:15:01 2023 - Mon Oct  2 10:00:00 2023  (00:44)
bob      pts/1        10.0.0.6         Tue Jun  6 08:00:00 2023 - Tue Jun  6 09:00:00 2023  (01:00)
reboot   system boot  4.18.0           Sun Oct  1 07:00:00 2023   still running

wtmp begins Thu Jun  1 00:00:00 2023
"""


class SnapshotTests(unittest.TestCase):
    def test_recent_logins_respects_window(self):
        users = snap.recent_logins(60, LAST_OUTPUT, now=datetime(2023, 10, 10))
        self.assertEqual(users, {"alice"})

    def test_resolve_known_and_unknown(self):
        me = pwd.getpwuid(os.getuid())
        self.assertEqual(
            snap.resolve(me.pw_name),
            "%s:%d:%d:%s:%s" % (me.pw_name, me.pw_uid, me.pw_gid, me.pw_dir, me.pw_shell))
        self.assertIsNone(snap.resolve("no-such-user-xyz"))

    def test_post_snapshot_flags_unresolved_names(self):
        me = pwd.getpwuid(os.getuid()).pw_name
        with tempfile.TemporaryDirectory() as d:
            pre = os.path.join(d, "pre")
            post = os.path.join(d, "post")
            with open(pre, "w") as f:
                f.write("%s:x\nno-such-user-xyz:1:1:/h:/bin/sh\n" % me)
            snap.main(["--users-from", pre, "--out", post])
            lines = open(post).read().splitlines()
        self.assertIn("no-such-user-xyz:UNRESOLVED", lines)
        self.assertTrue(any(l.startswith(me + ":") for l in lines))


if __name__ == "__main__":
    unittest.main()
