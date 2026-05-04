"""
Config API — manage suppression rules and global settings.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel

from backend.db.database import get_db
from backend.db.models import SuppressionRule
from backend.config import settings

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/settings")
async def get_settings():
    """Get current agent configuration."""
    return {
        "llm_provider": settings.llm_provider,
        "default_model": settings.default_model,
        "max_tokens_per_chunk": settings.max_tokens_per_chunk,
        "min_confidence": settings.min_confidence,
        "dry_run": settings.dry_run,
        "github_token_configured": bool(settings.github_token),
        "openai_key_configured": bool(settings.openai_api_key),
    }


class SuppressionRuleCreate(BaseModel):
    repo: str = "*"
    file_pattern: str = ""
    domain: str = "*"
    keyword: str = ""
    reason: str = ""


@router.get("/suppressions")
async def list_suppressions(db: AsyncSession = Depends(get_db)):
    """List all suppression rules."""
    result = await db.execute(select(SuppressionRule).where(SuppressionRule.active == True))
    rules = result.scalars().all()
    return {
        "rules": [
            {
                "id": r.id,
                "repo": r.repo,
                "file_pattern": r.file_pattern,
                "domain": r.domain,
                "keyword": r.keyword,
                "reason": r.reason,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rules
        ]
    }


@router.post("/suppressions")
async def create_suppression(
    rule: SuppressionRuleCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a new suppression rule."""
    new_rule = SuppressionRule(
        repo=rule.repo,
        file_pattern=rule.file_pattern,
        domain=rule.domain,
        keyword=rule.keyword,
        reason=rule.reason,
        active=True,
    )
    db.add(new_rule)
    await db.commit()
    return {"id": new_rule.id, "message": "Suppression rule created"}


@router.delete("/suppressions/{rule_id}")
async def delete_suppression(rule_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a suppression rule."""
    result = await db.execute(
        select(SuppressionRule).where(SuppressionRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.active = False
    await db.commit()
    return {"message": "Suppression rule deactivated"}
