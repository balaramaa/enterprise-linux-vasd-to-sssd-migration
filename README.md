# Enterprise Linux Automated Migration Framework: VAS to SSSD

An open-source orchestration framework for moving Red Hat Enterprise Linux (RHEL 7, 8, and 9) server fleets from commercial One Identity Authentication Services (VAS, `vasd`) to the native, open-source System Security Services Daemon (SSSD), with zero identity drift and near-zero disruption.

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24043076.svg)](https://doi.org/10.5281/zenodo.24043076)

This repository is the reference implementation for the paper:

> B. Alti, "Transitioning Enterprise Linux Authentication at Scale: Migrating from Commercial VAS to Native SSSD Architecture with Near-Zero Disruption," Zenodo, preprint, 2026. [doi:10.5281/zenodo.24043076](https://doi.org/10.5281/zenodo.24043076)

## Features

- **Per-host state machine with automatic rollback.** Any failure during join, cutover, or validation rolls the host back to VAS.
- **Bit-for-bit identity preservation.** SSSD reads the POSIX attributes already in AD (`ldap_id_mapping = False`). A zero-tolerance diff confirms every user resolves to the same UID, GID, home directory, and shell as before.
- **Wave orchestration.** Hosts run in batches, and a wave halts automatically if more than 2% of hosts fail.
- **Control-plane API.** FastAPI endpoints define and start waves, report per-host state with evidence, and trigger rollback.

## How it works

Each host moves through six states. A failed gate in Joined, Cutover, or Verified sends the host to Rollback, which restores VAS.

```
Pre-flight → Staged → Joined → Cutover → Verified → Decommissioned
                        \         |         /
                         └─── Rollback ────┘   (restores VAS)
```

| State | Role | What it does |
| --- | --- | --- |
| Pre-flight | `preflight` | Checks OS, clock skew, disk, DC reachability, break-glass account, and VAS health. Backs up NSS/PAM/Kerberos config and snapshots identities. |
| Staged | `sssd_stage` | Installs SSSD and renders `sssd.conf`. SSSD stays stopped. |
| Joined | `ad_join` | Stops VAS and joins AD with `adcli`, reusing the existing computer object. Verifies the keytab. |
| Cutover | `cutover` | Switches NSS and PAM to SSSD, keeps FILE ticket caches, and starts SSSD. |
| Verified | `validate` | Checks the domain is online, diffs identities, and runs access and sudo checks. |
| Decommissioned | `vas_remove` | Removes VAS, only after validation plus the soak period. |
| Rollback | `rollback` | Restores the saved config, rejoins VAS, and restarts `vasd`. |

## Requirements

- **Target hosts:** RHEL 7, 8, or 9, currently joined to AD with VAS, with `chrony` for time sync.
- **Active Directory:** users must carry RFC 2307 attributes (`uidNumber`, `gidNumber`, `homeDirectory`, `loginShell`). If they don't, UIDs will change. Back-fill AD first.
- **Control node:** Python 3.9+ and Ansible (`ansible-core` 2.14–2.16).

## Repository layout

```
ansible/
  ansible.cfg
  inventory.ini              One group per wave: canary, non_prod, production, dr
  group_vars/all/main.yml    Settings (domain, access control, thresholds)
  group_vars/all/vault.yml.example
  site.yml                   Migration playbook with automatic rollback
  rollback.yml               Manual rollback
  decommission.yml           Removes VAS after the soak period
  files/snapshot_identities.py
  roles/                     preflight, sssd_stage, ad_join, cutover,
                             validate, rollback, vas_remove
api/                         FastAPI control plane
tests/                       Unit tests
```

## Quick start

1. **Configure.** Edit `ansible/inventory.ini` and `ansible/group_vars/all/main.yml`. Set `ad_domain`, `break_glass_user`, and an explicit access-control choice (`sssd_access_provider`, `ad_gpo_access_control`).

2. **Add credentials.**

   ```bash
   cd ansible
   cp group_vars/all/vault.yml.example group_vars/all/vault.yml
   # edit vault.yml, then:
   ansible-vault encrypt group_vars/all/vault.yml
   ```

3. **Dry-run the canary wave**, then run it for real:

   ```bash
   ansible-playbook site.yml --limit canary --check --ask-vault-pass
   ansible-playbook site.yml --limit canary --ask-vault-pass
   ```

4. **Run the next waves** (`non_prod`, `production`, `dr`) the same way.

5. **After the soak period** (default 7 days), remove VAS:

   ```bash
   ansible-playbook decommission.yml --limit canary --ask-vault-pass
   ```

## Control-plane API (optional)

```bash
pip install -r api/requirements.txt
export MIGRATION_API_TOKEN="$(openssl rand -hex 32)"
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Every request needs the header `X-API-Token: $MIGRATION_API_TOKEN`.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/waves` | Define a wave: `{"name": "canary", "limit": "canary", "dry_run": true}` |
| `POST` | `/waves/{id}/start` | Start a defined wave |
| `GET` | `/waves/{id}` | Wave status |
| `GET` | `/nodes/{host}` | Host state and recorded evidence |
| `POST` | `/nodes/{host}/rollback` | Roll a host back to VAS |

To use the API with vault-encrypted variables, set `ANSIBLE_VAULT_PASSWORD_FILE` before starting it.

The reference implementation stores state in SQLite and runs waves as in-process background tasks, so it needs no extra services. For a large fleet, replace `api/store.py` with a PostgreSQL-backed store and run waves on a task queue such as Celery, as described in the paper.

## Running the tests

```bash
python3 -m unittest discover -s tests -t .
```

## Safety notes

- **Start small.** Always run the `canary` group first, and dry-run with `--check` before each wave.
- **Keep a break-glass account.** Pre-flight refuses to continue without one.
- **Protect the API.** It can change logins on many servers at once. Keep it on `127.0.0.1` or behind authentication.
- **Rollback rejoins VAS.** `adcli` resets the machine password, so rollback needs VAS join credentials, not just a service restart.
- **RHEL 7** uses `authconfig` instead of `authselect`. Cutover checks that `nsswitch.conf` no longer references VAS on every version.

## Disclaimer

This is an independent project. It is not affiliated with, endorsed by, or supported by One Identity, Red Hat, or the author's employer. Product names are trademarks of their respective owners. Test in a non-production environment before use. Use at your own risk.

## Citation

If you use this framework, please cite the paper:

```bibtex
@misc{alti2026vas2sssd,
  author    = {Alti, Balaramakrishna},
  title     = {Transitioning Enterprise Linux Authentication at Scale: Migrating from Commercial {VAS} to Native {SSSD} Architecture with Near-Zero Disruption},
  year      = {2026},
  publisher = {Zenodo},
  note      = {Preprint},
  doi       = {10.5281/zenodo.24043076},
  url       = {https://doi.org/10.5281/zenodo.24043076}
}
```

## License

Released under the [MIT License](LICENSE).
