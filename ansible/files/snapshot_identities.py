#!/usr/bin/env python
"""Record how AD identities resolve on this host, for identity-drift checks.

Each output line is ``name:uid:gid:home:shell``. Run once before migration
(gather mode) and again after cutover with ``--users-from`` pointing at the
first snapshot, then diff the two files. Any difference is identity drift.

Compatible with Python 2.7 (RHEL 7) and Python 3 (RHEL 8/9).
"""
from __future__ import print_function

import argparse
import os
import pwd
import re
import subprocess
import sys
from datetime import datetime, timedelta

DATE_RE = re.compile(
    r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) (\w{3}) +(\d{1,2}) (\d\d:\d\d:\d\d) (\d{4})"
)
SKIP_ENTRIES = ("reboot", "shutdown", "wtmp", "btmp", "")


def local_users(path="/etc/passwd"):
    """Names defined in the local passwd file (never AD identities)."""
    names = set()
    try:
        with open(path) as handle:
            for line in handle:
                if line.strip() and not line.startswith("#"):
                    names.add(line.split(":", 1)[0])
    except IOError:
        pass
    return names


def recent_logins(days, last_output=None, now=None):
    """Users with a login recorded in wtmp within the last ``days`` days."""
    if last_output is None:
        try:
            last_output = subprocess.check_output(["last", "-w", "-F"])
            last_output = last_output.decode("utf-8", "replace")
        except (OSError, subprocess.CalledProcessError):
            return set()
    cutoff = (now or datetime.now()) - timedelta(days=days)
    users = set()
    for line in last_output.splitlines():
        parts = line.split()
        if not parts or parts[0] in SKIP_ENTRIES:
            continue
        match = DATE_RE.search(line)
        if not match:
            continue
        try:
            when = datetime.strptime(" ".join(match.groups()), "%b %d %H:%M:%S %Y")
        except ValueError:
            continue
        if when >= cutoff:
            users.add(parts[0])
    return users


def home_owners(home="/home"):
    """Owners of top-level home directories, plus the directory names."""
    users = set()
    try:
        entries = os.listdir(home)
    except OSError:
        return users
    for entry in entries:
        users.add(entry)
        try:
            users.add(pwd.getpwuid(os.stat(os.path.join(home, entry)).st_uid).pw_name)
        except (OSError, KeyError):
            pass
    return users


def resolve(name):
    """Return ``name:uid:gid:home:shell`` or None if the name does not resolve."""
    try:
        entry = pwd.getpwnam(name)
    except KeyError:
        return None
    return "%s:%d:%d:%s:%s" % (name, entry.pw_uid, entry.pw_gid, entry.pw_dir, entry.pw_shell)


def names_from_snapshot(path):
    with open(path) as handle:
        return [line.split(":", 1)[0] for line in handle if line.strip()]


def build_snapshot(candidates, keep_unresolved):
    lines = []
    for name in sorted(set(candidates)):
        resolved = resolve(name)
        if resolved:
            lines.append(resolved)
        elif keep_unresolved:
            lines.append("%s:UNRESOLVED" % name)
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="file to write the snapshot to")
    parser.add_argument("--days", type=int, default=60, help="login look-back window")
    parser.add_argument("--extra", default="", help="comma-separated extra user names")
    parser.add_argument("--users-from", help="re-resolve the names in an earlier snapshot")
    args = parser.parse_args(argv)

    if args.users_from:
        candidates = names_from_snapshot(args.users_from)
        keep_unresolved = True
    else:
        candidates = recent_logins(args.days) | home_owners()
        candidates |= set(n.strip() for n in args.extra.split(",") if n.strip())
        candidates -= local_users()
        keep_unresolved = False

    lines = build_snapshot(candidates, keep_unresolved)
    with open(args.out, "w") as handle:
        handle.write("\n".join(lines) + ("\n" if lines else ""))
    unresolved = sum(1 for line in lines if line.endswith(":UNRESOLVED"))
    print("identities=%d unresolved=%d" % (len(lines), unresolved))
    return 0


if __name__ == "__main__":
    sys.exit(main())
