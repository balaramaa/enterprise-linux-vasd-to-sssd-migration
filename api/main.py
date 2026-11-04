from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import subprocess
import uuid

app = FastAPI(
    title="Enterprise Linux Migration Control Plane",
    description="Asynchronous API for managing automated VAS-to-SSSD migrations across RHEL fleets.",
    version="1.0.0"
)

class MigrationRequest(BaseModel):
    target_environment: str
    node_group: str
    dry_run: bool = True

jobs_db = {}

def run_ansible_job(job_id: str, node_group: str, dry_run: bool):
    try:
        jobs_db[job_id]["status"] = "RUNNING"
        cmd = ["ansible-playbook", "-i", "ansible/inventory.ini", "ansible/site.yml", "--limit", node_group]
        if dry_run:
            cmd.append("--check")
            
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        jobs_db[job_id]["status"] = "COMPLETED"
        jobs_db[job_id]["output"] = result.stdout
    except subprocess.CalledProcessError as e:
        jobs_db[job_id]["status"] = "FAILED"
        jobs_db[job_id]["error"] = e.stderr

@app.post("/api/v1/waves", status_code=202)
def trigger_migration_wave(request: MigrationRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs_db[job_id] = {
        "job_id": job_id,
        "target_environment": request.target_environment,
        "node_group": request.node_group,
        "status": "QUEUED"
    }
    background_tasks.add_task(run_ansible_job, job_id, request.node_group, request.dry_run)
    return {"message": "Migration wave initiated successfully.", "job_id": job_id}

@app.get("/api/v1/waves/status/{job_id}")
def get_wave_status(job_id: str):
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job ID not found.")
    return jobs_db[job_id]
