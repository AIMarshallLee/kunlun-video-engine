from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1", tags=["kunlun-video-engine"])


class VideoJobRequest(BaseModel):
    script: str = Field(min_length=10, max_length=20000)
    voice_id: str
    style: str = "极简商务涂鸦风"
    aspect_ratio: str = "9:16"
    mode: str = "infographic"
    scenes_per_image: int = Field(default=2, ge=1, le=4)
    task_name: str = ""
    pen_text: str = "昆仑增长"
    include_key_text: bool = True
    include_subtitles: bool = True
    stroke_detail: str = "detailed"
    metadata: dict[str, Any] = Field(default_factory=dict)


class VideoJobCreated(BaseModel):
    id: str
    status: str
    stage: str
    progress: int
    result_url: str | None = None
    output_path: str | None = None


KUNLUN_PRESETS: dict[str, dict[str, Any]] = {
    "short-video": {
        "style": "极简商务涂鸦风",
        "aspect_ratio": "9:16",
        "mode": "infographic",
        "scenes_per_image": 2,
        "pen_text": "昆仑增长",
        "include_key_text": True,
        "include_subtitles": True,
        "stroke_detail": "detailed",
    },
    "business-explainer": {
        "style": "极简商务涂鸦风",
        "aspect_ratio": "16:9",
        "mode": "infographic",
        "scenes_per_image": 2,
        "pen_text": "昆仑增长",
        "include_key_text": True,
        "include_subtitles": True,
        "stroke_detail": "detailed",
    },
    "high-impact": {
        "style": "爆款高热吸睛风",
        "aspect_ratio": "9:16",
        "mode": "standard",
        "scenes_per_image": 1,
        "pen_text": "昆仑增长",
        "include_key_text": True,
        "include_subtitles": True,
        "stroke_detail": "standard",
    },
}


def install_machine_api(ns: dict[str, Any]) -> None:
    """Bind the machine API to the existing cs-board runtime without duplicating the pipeline."""

    @router.get("/capabilities")
    def capabilities() -> dict[str, Any]:
        return {
            "service": "kunlun-video-engine",
            "api_version": "v1",
            "pipeline_version": ns["PIPELINE_VERSION"],
            "aspect_ratios": ["9:16", "16:9", "1:1"],
            "modes": ["standard", "infographic"],
            "presets": KUNLUN_PRESETS,
            "endpoints": {
                "create_job": "/api/v1/video-jobs",
                "get_job": "/api/v1/video-jobs/{job_id}",
                "voices": "/api/voices",
                "styles": "/api/styles",
                "health": "/api/health",
            },
        }

    @router.post("/video-jobs", response_model=VideoJobCreated)
    def create_video_job(payload: VideoJobRequest, request: Request) -> dict[str, Any]:
        script = payload.script.strip()
        if payload.mode not in {"standard", "infographic"}:
            raise HTTPException(400, "mode must be standard or infographic")
        if payload.aspect_ratio not in {"16:9", "9:16", "1:1"}:
            raise HTTPException(400, "unsupported aspect_ratio")

        LOCK = ns["LOCK"]
        JOBS = ns["JOBS"]
        MAX_ACTIVE_AND_QUEUED = ns["MAX_ACTIVE_AND_QUEUED"]
        JOBS_DIR: Path = ns["JOBS_DIR"]
        VOICE_QUEUE = ns["VOICE_QUEUE"]
        ensure_pipeline_workers = ns["ensure_pipeline_workers"]
        voice_record = ns["voice_record"]
        normalize_aspect_ratio = ns["normalize_aspect_ratio"]
        normalized_task_name = ns["normalized_task_name"]
        request_client_ip = ns["request_client_ip"]
        persist = ns["_persist_job_locked"]
        pipeline_version = ns["PIPELINE_VERSION"]

        with LOCK:
            pending = sum(1 for item in JOBS.values() if item.get("status") in {"queued", "running"})
        if pending >= MAX_ACTIVE_AND_QUEUED:
            raise HTTPException(429, f"当前已有 {pending} 个任务，请稍后再提交")

        voice_meta, voice_path = voice_record(payload.voice_id.strip())
        job_id = uuid.uuid4().hex[:12]
        job_dir = JOBS_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        reference_path = job_dir / f"reference{voice_path.suffix or '.wav'}"
        reference_path.write_bytes(voice_path.read_bytes())

        aspect_ratio = normalize_aspect_ratio(payload.aspect_ratio)
        task_name = normalized_task_name(payload.task_name, script, job_id)
        reference_mode = "infographic" if payload.mode == "infographic" else "standard"
        now = time.time()

        with LOCK:
            JOBS[job_id] = {
                "id": job_id,
                "status": "queued",
                "stage": "等待语音克隆",
                "progress": 1,
                "created_at": now,
                "started_at": now,
                "timings": {},
                "queue_stage": "voice",
                "queue_order": time.time_ns(),
                "client_ip": request_client_ip(request),
                "job_type": "infographic" if reference_mode == "infographic" else "generate",
                "style": payload.style,
                "aspect_ratio": aspect_ratio,
                "scenes_per_image": payload.scenes_per_image,
                "pipeline_version": pipeline_version if reference_mode == "infographic" else "standard_v1",
                "reference_mode": reference_mode,
                "character_count": 0,
                "voice_id": payload.voice_id.strip(),
                "voice_name": str(voice_meta.get("name") or ""),
                "visual_references": {},
                "task_name": task_name,
                "copy": script,
                "pen_text": payload.pen_text.strip()[:12],
                "include_key_text": payload.include_key_text,
                "include_subtitles": payload.include_subtitles,
                "stroke_detail": payload.stroke_detail if payload.stroke_detail in {"light", "standard", "detailed", "full"} else "detailed",
                "can_rerender": False,
                "current_phase": None,
                "phase_started_at": None,
                "total_elapsed": 0.0,
                "external_metadata": payload.metadata,
                "submitted_via": "machine_api_v1",
            }
            persist(job_id)

        VOICE_QUEUE.put((
            job_id,
            script,
            payload.style,
            reference_path,
            payload.scenes_per_image,
            payload.pen_text.strip()[:12],
            payload.include_key_text,
            payload.include_subtitles,
            payload.stroke_detail,
        ))
        ensure_pipeline_workers()
        return ns["job_snapshot"](job_id)

    @router.get("/video-jobs/{job_id}")
    def get_video_job(job_id: str) -> dict[str, Any]:
        JOBS = ns["JOBS"]
        LOCK = ns["LOCK"]
        with LOCK:
            if job_id not in JOBS:
                raise HTTPException(404, "任务不存在")
        return ns["job_snapshot"](job_id)
