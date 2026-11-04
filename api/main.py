"""Control plane for VAS-to-SSSD migration waves (paper, Section IV-A).

Every request must send the header ``X-API-Token`` matching the
MIGRATION_API_TOKEN environment variable. Bind to 127.0.0.1 or put the API
behind an authenticating proxy: it can change logins on many servers at once.
"""
import hmac
import os
import re

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import runner, store

LIMIT_RE = re.compile(r"^[A-Za-z0-9_.:,*!&\-]+$")
HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-_]*$")

app = FastAPI(
    title="Enterprise Linux Migration Control Plane",
    description="Runs VAS-to-SSSD migration waves across RHEL fleets.",
    version="1.1.0",
)


@app.on_event("startup")
def _startup():
    store.init_db()


def require_token(x_api_token: str = Header(default="")):
    expected = os.environ.get("MIGRATION_API_TOKEN", "")
    if not expected:
        raise HTTPException(503, "MIGRATION_API_TOKEN is not set on the server.")
    if not hmac.compare_digest(x_api_token, expected):
        raise HTTPException(401, "Invalid or missing X-API-Token.")


class WaveRequest(BaseModel):
    name: str = Field(..., max_length=100, examples=["canary"])
    limit: str = Field(..., max_length=500, description="Ansible --limit pattern, e.g. an inventory group")
    dry_run: bool = Field(True, description="Run with --check. Set false to make changes.")


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.post("/waves", status_code=201, dependencies=[Depends(require_token)])
def define_wave(request: WaveRequest):
    """Define a wave of hosts. It does not run until started."""
    if not LIMIT_RE.match(request.limit):
        raise HTTPException(422, "limit contains characters that are not allowed.")
    return store.create_wave(request.name, request.limit, request.dry_run)


@app.get("/waves/{wave_id}", dependencies=[Depends(require_token)])
def get_wave(wave_id: str):
    wave = store.get_wave(wave_id)
    if wave is None:
        raise HTTPException(404, "Wave not found.")
    return wave


@app.post("/waves/{wave_id}/start", status_code=202, dependencies=[Depends(require_token)])
def start_wave(wave_id: str, background_tasks: BackgroundTasks):
    """Start a defined wave. Each wave can be started once."""
    if store.get_wave(wave_id) is None:
        raise HTTPException(404, "Wave not found.")
    if not store.claim_wave(wave_id):
        raise HTTPException(409, "Wave has already been started.")
    background_tasks.add_task(runner.run_wave, wave_id)
    return {"wave_id": wave_id, "status": "RUNNING"}


@app.get("/nodes/{host}", dependencies=[Depends(require_token)])
def get_node(host: str):
    """Current state of a host and the evidence recorded for it."""
    node = store.get_node(host)
    if node is None:
        raise HTTPException(404, "No state recorded for this host.")
    return node


@app.post("/nodes/{host}/rollback", status_code=202, dependencies=[Depends(require_token)])
def rollback_node(host: str, background_tasks: BackgroundTasks):
    """Roll a host back to VAS."""
    if not HOST_RE.match(host):
        raise HTTPException(422, "Invalid host name.")
    background_tasks.add_task(runner.run_rollback, host)
    return {"host": host, "status": "ROLLBACK_QUEUED"}
