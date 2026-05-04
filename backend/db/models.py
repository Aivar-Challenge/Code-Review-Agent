"""
Database models using SQLAlchemy 2.0 async ORM.
"""
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, JSON
)
from sqlalchemy.orm import DeclarativeBase


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass


class Run(Base):
    """Represents a single code review run against a PR."""
    __tablename__ = "runs"

    id = Column(String, primary_key=True, default=_uuid)
    pr_url = Column(String, nullable=False)
    pr_number = Column(Integer)
    repo = Column(String)           # "owner/repo"
    owner = Column(String)
    commit_sha = Column(String)
    base_sha = Column(String)
    pr_title = Column(String)
    pr_author = Column(String)
    status = Column(String, default="queued")  # queued|running|completed|failed
    error_message = Column(Text)
    config = Column(JSON)           # run-specific config snapshot
    started_at = Column(DateTime, default=_now)
    completed_at = Column(DateTime)
    total_tokens = Column(Integer, default=0)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    findings_count = Column(Integer, default=0)
    posted_count = Column(Integer, default=0)
    suppressed_count = Column(Integer, default=0)
    github_review_id = Column(String)


class Finding(Base):
    """An individual issue found in the PR diff."""
    __tablename__ = "findings"

    id = Column(String, primary_key=True, default=_uuid)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    file_path = Column(String, nullable=False)
    line_number = Column(Integer)           # diff line number (1-based)
    diff_position = Column(Integer)         # GitHub diff position
    domain = Column(String, nullable=False) # correctness|security|performance|test_coverage
    confidence = Column(String, nullable=False)  # HIGH|MEDIUM|LOW
    title = Column(String)
    issue = Column(Text)
    why_it_matters = Column(Text)
    fix_suggestion = Column(Text)
    code_example = Column(Text)
    fingerprint = Column(String, unique=False, index=True)  # SHA256 hash
    suppressed = Column(Boolean, default=False)
    suppressed_reason = Column(String)
    posted = Column(Boolean, default=False)
    github_comment_id = Column(String)
    created_at = Column(DateTime, default=_now)


class SuppressionRule(Base):
    """Repo-specific suppression rules to skip known false positives."""
    __tablename__ = "suppression_rules"

    id = Column(String, primary_key=True, default=_uuid)
    repo = Column(String)           # "owner/repo" or "*" for global
    file_pattern = Column(String)   # glob pattern e.g. "tests/*"
    domain = Column(String)         # domain to suppress or "*"
    keyword = Column(String)        # keyword in title/issue to match
    reason = Column(String)
    created_at = Column(DateTime, default=_now)
    active = Column(Boolean, default=True)


class PostedComment(Base):
    """
    Tracks comments already posted on GitHub to enable idempotent re-runs.
    """
    __tablename__ = "posted_comments"

    id = Column(String, primary_key=True, default=_uuid)
    pr_url = Column(String, nullable=False, index=True)
    fingerprint = Column(String, nullable=False, index=True)
    github_comment_id = Column(String)
    file_path = Column(String)
    posted_at = Column(DateTime, default=_now)
    commit_sha = Column(String)
