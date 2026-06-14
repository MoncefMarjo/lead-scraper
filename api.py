"""
api.py
FastAPI backend for B2B Lead Scraper
"""

import os
import uuid
import csv
import io
import threading
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from main import process_leads, discover_and_process

app = FastAPI(title="B2B Lead Scraper")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory job store ───────────────────────────────────────────────────────
jobs = {}


class Lead(BaseModel):
    name: str
    city: str = ""


class LeadList(BaseModel):
    leads: List[Lead]


class DiscoverRequest(BaseModel):
    naf_code: str
    postal_codes: List[str]
    target: int = 500


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def root():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/scrape")
def scrape(data: LeadList):
    job_id = str(uuid.uuid4())
    leads = [{"name": l.name, "city": l.city} for l in data.leads]
    jobs[job_id] = {"status": "running", "progress": 0, "total": len(leads), "file": None}

    def run():
        try:
            output_path = f"output_{job_id}.xlsx"
            process_leads(leads, output_path)
            jobs[job_id]["status"] = "done"
            jobs[job_id]["file"] = output_path
        except Exception as e:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)

    threading.Thread(target=run).start()
    return {"job_id": job_id}


@app.post("/scrape-csv")
async def scrape_csv(file: UploadFile = File(...)):
    contents = await file.read()
    decoded = contents.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(decoded))

    leads = []
    for row in reader:
        name = row.get("name") or row.get("nom") or row.get("Name") or ""
        city = row.get("city") or row.get("ville") or row.get("City") or ""
        if name.strip():
            leads.append({"name": name.strip(), "city": city.strip()})

    if not leads:
        raise HTTPException(status_code=400, detail="No valid leads found in CSV.")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "running", "progress": 0, "total": len(leads), "file": None}

    def run():
        try:
            output_path = f"output_{job_id}.xlsx"
            process_leads(leads, output_path)
            jobs[job_id]["status"] = "done"
            jobs[job_id]["file"] = output_path
        except Exception as e:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)

    threading.Thread(target=run).start()
    return {"job_id": job_id}


@app.post("/discover")
def discover(data: DiscoverRequest):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "running",
        "stage": "discovery",
        "progress": 0,
        "total": 0,
        "discovered": 0,
        "with_phone": 0,
        "current": "",
        "file": None,
    }

    def run():
        try:
            output_path = f"output_{job_id}.xlsx"
            discover_and_process(
                naf_code=data.naf_code,
                postal_codes=data.postal_codes,
                target=data.target,
                output_path=output_path,
                job=jobs[job_id],
            )
        except Exception as e:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)

    threading.Thread(target=run).start()
    return {"job_id": job_id}


@app.get("/status/{job_id}")
def status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/download/{job_id}")
def download(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not finished yet")
    file_path = job["file"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="leads_export.xlsx"
    )