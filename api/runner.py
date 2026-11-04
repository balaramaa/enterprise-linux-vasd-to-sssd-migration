"""Run Ansible playbooks with ansible-runner and record per-node state."""
import tempfile
from pathlib import Path

from . import store

ANSIBLE_DIR = Path(__file__).resolve().parent.parent / "ansible"

# State a node reaches when a task in each role succeeds (paper, Fig. 1).
ROLE_STATE = {
    "preflight": "PREFLIGHT",
    "sssd_stage": "STAGED",
    "ad_join": "JOINED",
    "cutover": "CUTOVER",
    "validate": "VERIFIED",
    "rollback": "ROLLED_BACK",
    "vas_remove": "DECOMMISSIONED",
}


def handle_event(event, wave_id=None, db_path=None):
    """Translate one ansible-runner event into node state and evidence."""
    kind = event.get("event")
    data = event.get("event_data", {})
    host = data.get("host")
    if not host or kind not in ("runner_on_ok", "runner_on_failed", "runner_on_unreachable"):
        return True
    role = data.get("role")
    task = data.get("task")
    if kind == "runner_on_ok":
        state = ROLE_STATE.get(role)
        if state:
            store.record(host, state, role, task, "ok", wave_id, db_path)
    elif kind == "runner_on_failed" and data.get("ignore_errors"):
        store.record(host, ROLE_STATE.get(role, "UNKNOWN"), role, task, "ignored", wave_id, db_path)
    else:
        status = "unreachable" if kind == "runner_on_unreachable" else "failed"
        store.record(host, "FAILED", role, task, status, wave_id, db_path)
    return True


def _run(playbook, limit, dry_run, wave_id=None, db_path=None):
    import ansible_runner  # imported here so the rest of the API loads without it

    with tempfile.TemporaryDirectory() as private_dir:
        result = ansible_runner.run(
            private_data_dir=private_dir,
            project_dir=str(ANSIBLE_DIR),
            playbook=playbook,
            inventory=str(ANSIBLE_DIR / "inventory.ini"),
            limit=limit,
            cmdline="--check" if dry_run else None,
            envvars={"ANSIBLE_CONFIG": str(ANSIBLE_DIR / "ansible.cfg")},
            event_handler=lambda e: handle_event(e, wave_id, db_path),
            quiet=True,
        )
    return result.status == "successful" and result.rc == 0


def run_wave(wave_id, db_path=None):
    wave = store.get_wave(wave_id, db_path)
    try:
        ok = _run("site.yml", wave["limit_pattern"], wave["dry_run"], wave_id, db_path)
    except Exception:
        ok = False
    store.set_wave_status(wave_id, "COMPLETED" if ok else "FAILED", db_path)


def run_rollback(host, db_path=None):
    try:
        ok = _run("rollback.yml", host, dry_run=False, db_path=db_path)
    except Exception:
        ok = False
    if not ok:
        store.record(host, "FAILED", "rollback", "rollback playbook", "failed", db_path=db_path)
