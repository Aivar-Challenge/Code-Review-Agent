"""
GET /api/runs — List all runs with pagination.
DELETE /api/runs/{run_id} — Delete a run and its findings.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, desc, func

from backend.db.database import get_db
from backend.db.models import Run, Finding

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("")
async def list_runs(
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List all review runs, paginated."""
    query = select(Run).order_by(desc(Run.started_at))
    if status:
        query = query.where(Run.status == status)

    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    runs = result.scalars().all()

    # Count total
    count_result = await db.execute(select(func.count()).select_from(Run))
    total = count_result.scalar()

    return {
        "runs": [
            {
                "id": r.id,
                "pr_url": r.pr_url,
                "pr_number": r.pr_number,
                "repo": r.repo,
                "pr_title": r.pr_title,
                "pr_author": r.pr_author,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "findings_count": r.findings_count,
                "posted_count": r.posted_count,
                "suppressed_count": r.suppressed_count,
                "estimated_cost_usd": r.estimated_cost_usd,
                "error_message": r.error_message,
            }
            for r in runs
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.delete("/{run_id}")
async def delete_run(run_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a run and all associated findings."""
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    await db.execute(delete(Finding).where(Finding.run_id == run_id))
    await db.delete(run)
    await db.commit()
    return {"message": "Run deleted", "run_id": run_id}


@router.get("/stats/summary")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get aggregate statistics across all runs."""
    total_runs = (await db.execute(select(func.count()).select_from(Run))).scalar()
    completed_runs = (
        await db.execute(select(func.count()).select_from(Run).where(Run.status == "completed"))
    ).scalar()
    total_findings = (await db.execute(select(func.count()).select_from(Finding))).scalar()
    posted_findings = (
        await db.execute(select(func.count()).select_from(Finding).where(Finding.posted == True))
    ).scalar()
    total_cost = (await db.execute(select(func.sum(Run.estimated_cost_usd)).select_from(Run))).scalar()
    total_tokens = (await db.execute(select(func.sum(Run.total_tokens)).select_from(Run))).scalar()

    # Domain breakdown
    domain_counts = {}
    for domain in ["correctness", "security", "performance", "test_coverage"]:
        count = (
            await db.execute(
                select(func.count()).select_from(Finding).where(Finding.domain == domain)
            )
        ).scalar()
        domain_counts[domain] = count or 0

    return {
        "total_runs": total_runs,
        "completed_runs": completed_runs,
        "total_findings": total_findings,
        "posted_findings": posted_findings,
        "total_cost_usd": float(total_cost or 0),
        "total_tokens": int(total_tokens or 0),
        "domain_breakdown": domain_counts,
    }
