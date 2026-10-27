import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from bikeshare.agent import run_bikeshare_agent

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = ROOT / "reports/hw07/raw/snapshots"
MAX_CSV_BYTES = 8 * 1024 * 1024
router = APIRouter(prefix="/api/bikeshare", tags=["bikeshare ReAct agent"])
JOBS: dict[str, dict] = {}


def _worker(job_id: str, csv_text: str, url: str, label: str) -> None:
    job = JOBS[job_id]
    try:
        job["result"] = run_bikeshare_agent(csv_text, url, on_event=job["events"].append, snapshot_dir=SNAPSHOT_DIR, label=label)
        job["status"] = "done"
    except Exception as exc:  # surfaced to the page instead of a hung spinner
        job["status"], job["error"] = "error", f"{type(exc).__name__}: {exc}"


@router.post("/run")
async def run(csv: UploadFile = File(...), url: str = Form(...)):
    raw = await csv.read()
    if not raw or len(raw) > MAX_CSV_BYTES:
        raise HTTPException(status_code=422, detail=f"CSV must be between 1 byte and {MAX_CSV_BYTES // 1024 // 1024} MB")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="pricing URL must start with http:// or https://")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="CSV must be UTF-8 text") from None
    job_id = uuid.uuid4().hex[:10]
    JOBS[job_id] = {"status": "running", "events": [], "result": None, "error": None}
    label = Path(csv.filename or "upload").stem[:60]
    threading.Thread(target=_worker, args=(job_id, text, url.strip(), label), daemon=True).start()
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
def job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="unknown job")
    j = JOBS[job_id]
    return {"status": j["status"], "events": list(j["events"]), "result": j["result"], "error": j["error"]}
