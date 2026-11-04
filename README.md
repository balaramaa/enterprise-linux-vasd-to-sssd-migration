# Enterprise Linux Automated Migration Framework: VAS to SSSD

An open-source orchestration framework designed to transition large-scale Red Hat Enterprise Linux (RHEL 7/8/9) server fleets from commercial One Identity Authentication Services (VAS, `vasd`) to native, open-source System Security Services Daemon (SSSD) with zero identity drift and near-zero downtime.

## Features
* **Asynchronous Control Plane:** Built with FastAPI and Celery to manage concurrent multi-node wave migrations with bounded blast radius.
* **Idempotent Automation:** Modular Ansible roles ensuring strict state transitions, automated pre-flight checks, and rollback safety gates.
* **Bit-for-Bit Identity Preservation:** Enforces `ldap_id_mapping = False` to guarantee identical UID, GID, home directory, and shell resolutions before and after cutover.

## Quick Start
1. Configure host targets in `ansible/inventory.ini`.
2. Install control plane requirements and launch API:
   ```bash
   pip install -r api/requirements.txt
   uvicorn api.main:app --host 0.0.0.0 --port 8000

1.	Execute migration via Ansible or the REST API:
ansible-playbook -i ansible/inventory.ini ansible/site.yml

---

### File 2: `api/requirements.txt`
```text
fastapi==0.110.0
uvicorn==0.28.0
pydantic==2.6.4
ansible-runner==2.3.6
celery==5.3.6
psycopg2-binary==2.9.9
