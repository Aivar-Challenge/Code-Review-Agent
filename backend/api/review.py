"""
POST /api/review — Trigger a code review run.
GET /api/review/{run_id} — Get run status and findings.
"""
import asyncio
import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Any

from backend.db.database import get_db
from backend.db.models import Run, Finding
from backend.agent.analyzer import run_review

logger = logging.getLogger("api.review")

router = APIRouter(prefix="/api/review", tags=["review"])

# In-memory log store for WebSocket streaming
# run_id -> list of log entries
_run_logs: dict[str, list[dict]] = {}
_run_log_queues: dict[str, list[asyncio.Queue]] = {}


def get_log_queue(run_id: str) -> asyncio.Queue:
    q = asyncio.Queue()
    _run_log_queues.setdefault(run_id, []).append(q)
    return q


async def _broadcast_log(run_id: str, msg: str, level: str = "info"):
    entry = {"message": msg, "level": level}
    _run_logs.setdefault(run_id, []).append(entry)
    for q in _run_log_queues.get(run_id, []):
        await q.put(entry)


class ReviewRequest(BaseModel):
    pr_url: str
    config: dict[str, Any] = {}


class ReviewResponse(BaseModel):
    run_id: str
    status: str
    message: str


@router.post("", response_model=ReviewResponse)
async def start_review(
    request: ReviewRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Start a code review run asynchronously."""
    run_id = str(uuid.uuid4())
    _run_logs[run_id] = []

    async def _log_fn(msg: str, level: str = "info"):
        await _broadcast_log(run_id, msg, level)

    async def _run():
        await run_review(
            pr_url=str(request.pr_url),
            config_dict=request.config,
            run_id=run_id,
            log_fn=_log_fn,
        )
        # Signal completion to all WebSocket listeners
        for q in _run_log_queues.get(run_id, []):
            await q.put({"message": "__DONE__", "level": "system"})

    background_tasks.add_task(_run)

    return ReviewResponse(
        run_id=run_id,
        status="queued",
        message=f"Review started. Monitor at /api/review/{run_id}",
    )


@router.get("/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    """Get run status, findings, and cost report."""
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    findings_result = await db.execute(
        select(Finding).where(Finding.run_id == run_id)
    )
    findings = findings_result.scalars().all()

    return {
        "run_id": run.id,
        "status": run.status,
        "pr_url": run.pr_url,
        "pr_number": run.pr_number,
        "repo": run.repo,
        "pr_title": run.pr_title,
        "pr_author": run.pr_author,
        "commit_sha": run.commit_sha,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "error_message": run.error_message,
        "config": run.config,
        "findings_count": run.findings_count,
        "posted_count": run.posted_count,
        "suppressed_count": run.suppressed_count,
        "cost": {
            "total_tokens": run.total_tokens,
            "prompt_tokens": run.prompt_tokens,
            "completion_tokens": run.completion_tokens,
            "estimated_cost_usd": run.estimated_cost_usd,
        },
        "findings": [
            {
                "id": f.id,
                "file_path": f.file_path,
                "line_number": f.line_number,
                "diff_position": f.diff_position,
                "domain": f.domain,
                "confidence": f.confidence,
                "title": f.title,
                "issue": f.issue,
                "why_it_matters": f.why_it_matters,
                "fix_suggestion": f.fix_suggestion,
                "code_example": f.code_example,
                "fingerprint": f.fingerprint,
                "suppressed": f.suppressed,
                "suppressed_reason": f.suppressed_reason,
                "posted": f.posted,
                "github_comment_id": f.github_comment_id,
            }
            for f in findings
        ],
        "logs": _run_logs.get(run_id, []),
    }


@router.get("/{run_id}/logs")
async def get_run_logs(run_id: str):
    """Get all logs for a run."""
    return {"run_id": run_id, "logs": _run_logs.get(run_id, [])}


# Export log store for WebSocket access
def get_run_logs_store():
    return _run_logs


def get_log_queues_store():
    return _run_log_queues
