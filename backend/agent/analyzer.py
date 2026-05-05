"""
Analysis orchestrator — coordinates parallel domain analysis,
synthesis pass, deduplication, and comment posting.

This is the main entry point for a code review run.
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Callable, Awaitable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.config import settings
from backend.db.models import Run, Finding
from backend.db.database import AsyncSessionLocal
from backend.agent.github_client import GitHubClient
from backend.agent.diff_parser import parse_diff, get_diff_stats
from backend.agent.chunker import chunk_all_files
from backend.agent.deduplicator import Deduplicator, compute_fingerprint
from backend.agent.comment_poster import CommentPoster
from backend.agent.cost_tracker import CostTracker
from backend.agent.domains.correctness import analyze_correctness
from backend.agent.domains.security import analyze_security
from backend.agent.domains.performance import analyze_performance
from backend.agent.domains.test_coverage import analyze_test_coverage
from backend.agent.domains.synthesis import run_synthesis_pass

logger = logging.getLogger("agent.analyzer")

LogFn = Callable[[str, str], Awaitable[None]]


class ReviewConfig:
    """Configuration for a single review run."""
    def __init__(self, raw: dict):
        self.domains = raw.get("domains", {
            "correctness": True,
            "security": True,
            "performance": True,
            "test_coverage": True,
        })
        self.min_confidence: str = raw.get("min_confidence", settings.min_confidence)
        self.dry_run: bool = raw.get("dry_run", settings.dry_run)
        self.max_tokens_per_chunk: int = raw.get("max_tokens_per_chunk", settings.max_tokens_per_chunk)
        self.model: str = raw.get("model", settings.default_model)
        self.synthesis_pass: bool = raw.get("synthesis_pass", True)
        self.github_token: str | None = raw.get("github_token") or settings.github_token


async def run_review(
    pr_url: str,
    config_dict: dict | None = None,
    run_id: str | None = None,
    log_fn: LogFn | None = None,
) -> dict:
    """
    Full code review pipeline for a PR URL.
    Returns a summary dict with findings, cost, and run metadata.
    """
    config = ReviewConfig(config_dict or {})
    run_id = run_id or str(uuid.uuid4())

    async def log(msg: str, level: str = "info"):
        logger.info(msg)
        if log_fn:
            await log_fn(msg, level)

    await log(f"🚀 Starting review run {run_id}")
    await log(f"PR: {pr_url}")

    async with AsyncSessionLocal() as db:
        # Parse PR URL
        async with GitHubClient(token=config.github_token) as gh:
            try:
                owner, repo, pr_number = gh.parse_pr_url(pr_url)
                repo_full = f"{owner}/{repo}"
            except ValueError as e:
                await log(f"❌ Invalid PR URL: {e}", "error")
                return {"error": str(e), "run_id": run_id}

            # Create run record
            run = Run(
                id=run_id,
                pr_url=pr_url,
                pr_number=pr_number,
                repo=repo_full,
                owner=owner,
                status="running",
                config=config_dict or {},
                started_at=datetime.utcnow(),
            )
            db.add(run)
            await db.commit()

            try:
                # ── Step 1: Fetch PR metadata ─────────────────────────────
                await log("📡 Fetching PR metadata...")
                pr_meta = await gh.get_pull_request(owner, repo, pr_number)
                commit_sha = pr_meta["head"]["sha"]
                base_sha = pr_meta["base"]["sha"]

                run.commit_sha = commit_sha
                run.base_sha = base_sha
                run.pr_title = pr_meta.get("title", "")
                run.pr_author = pr_meta.get("user", {}).get("login", "")
                await db.commit()

                await log(f"✅ PR #{pr_number}: \"{run.pr_title}\" by @{run.pr_author}")
                await log(f"   Head: {commit_sha[:8]} | Base: {base_sha[:8]}")

                # ── Step 2: Fetch diff and files ──────────────────────────
                await log("📥 Fetching PR diff...")
                raw_diff = await gh.get_pr_diff(owner, repo, pr_number)
                pr_files = await gh.get_pr_files(owner, repo, pr_number)

                file_diffs = parse_diff(raw_diff)
                stats = get_diff_stats(file_diffs)

                await log(
                    f"📊 Diff stats: {stats['files_changed']} files, "
                    f"{stats['total_changes']} changes ({stats['lines_added']} added)"
                )

                if stats["total_changes"] == 0:
                    await log("ℹ️ No changes to analyze", "info")
                    run.status = "completed"
                    await db.commit()
                    return {"run_id": run_id, "findings": [], "status": "no_changes"}

                # ── Step 3: Semantic chunking ─────────────────────────────
                await log(f"✂️ Chunking diff (max {config.max_tokens_per_chunk} tokens/chunk)...")
                chunks = chunk_all_files(
                    file_diffs,
                    max_tokens=config.max_tokens_per_chunk,
                    model=config.model,
                )
                await log(f"   Created {len(chunks)} semantic chunks")

                # Context for test coverage: all changed file paths
                all_files_context = "\n".join(
                    f"  - {f['filename']} ({f['status']}, +{f.get('additions', 0)}/-{f.get('deletions', 0)})"
                    for f in pr_files
                )

                # ── Step 4: Parallel domain analysis ─────────────────────
                await log("🔍 Running parallel domain analysis...")
                cost_tracker = CostTracker(model=config.model)
                all_findings: list[dict] = []

                async def run_domain_on_chunk(chunk, domain: str) -> list[dict]:
                    try:
                        if domain == "correctness":
                            findings, resp = await analyze_correctness(chunk, config.model)
                        elif domain == "security":
                            findings, resp = await analyze_security(chunk, config.model)
                        elif domain == "performance":
                            findings, resp = await analyze_performance(chunk, config.model)
                        elif domain == "test_coverage":
                            findings, resp = await analyze_test_coverage(
                                chunk, all_files_context, config.model
                            )
                        else:
                            return []

                        cost_tracker.record(domain, resp.prompt_tokens, resp.completion_tokens)
                        await log(
                            f"   [{domain}] {chunk.file_path} chunk {chunk.chunk_index+1}: "
                            f"{len(findings)} findings ({resp.total_tokens} tokens)",
                            "debug",
                        )

                        # Attach file context to each finding
                        for f in findings:
                            f.setdefault("file_path", chunk.file_path)
                            f.setdefault("diff_position", None)

                        return findings

                    except Exception as e:
                        await log(f"   ⚠️ Error in {domain} on {chunk.file_path}: {e}", "warning")
                        return []

                # Build tasks for enabled domains × chunks
                tasks = []
                for chunk in chunks:
                    for domain, enabled in config.domains.items():
                        if enabled:
                            tasks.append(run_domain_on_chunk(chunk, domain))

                await log(f"   Dispatching {len(tasks)} analysis tasks...")
                chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in chunk_results:
                    if isinstance(result, list):
                        all_findings.extend(result)
                    elif isinstance(result, Exception):
                        await log(f"   ⚠️ Task error: {result}", "warning")

                await log(f"   Raw findings before dedup: {len(all_findings)}")

                # ── Step 5: Synthesis pass ────────────────────────────────
                if config.synthesis_pass and len(chunks) > 1:
                    await log("🔄 Running synthesis pass for cross-chunk issues...")
                    changed_files_summary = "\n".join(
                        f"  {f.filename} ({f.status})" for f in file_diffs[:30]
                    )
                    synth_findings, synth_resp = await run_synthesis_pass(
                        all_findings, changed_files_summary, config.model
                    )
                    cost_tracker.record(
                        "synthesis", synth_resp.prompt_tokens, synth_resp.completion_tokens
                    )
                    # Attach file path from findings if missing
                    for sf in synth_findings:
                        if not sf.get("file_path") and file_diffs:
                            sf["file_path"] = file_diffs[0].filename
                    all_findings.extend(synth_findings)
                    await log(f"   Synthesis found {len(synth_findings)} cross-file issues")

                # ── Step 6: Fetch existing GitHub comments ────────────────
                await log("🔍 Fetching existing GitHub review comments...")
                existing_comments = await gh.get_existing_review_comments(owner, repo, pr_number)
                await log(f"   {len(existing_comments)} existing comments found")

                # ── Step 7: Deduplication ─────────────────────────────────
                await log("♻️ Running deduplication...")
                dedup = Deduplicator(db, pr_url)
                await dedup.load(existing_comments, repo_full)

                # ── Step 8: Persist findings to DB ────────────────────────
                await log("💾 Persisting findings to database...")
                finding_records: list[Finding] = []
                for raw in all_findings:
                    confidence = raw.get("confidence", "LOW")
                    file_path = raw.get("file_path", "")
                    domain = raw.get("domain", "")
                    title = raw.get("title", "")
                    issue = raw.get("issue", "")
                    line_number = raw.get("line_number")
                    diff_position = raw.get("diff_position")

                    fp = compute_fingerprint(file_path, line_number, domain, title, issue)

                    # Check suppression
                    is_sup, sup_reason = dedup.is_suppressed(file_path, domain, title, issue)
                    # Check duplicate
                    is_dup, dup_reason = dedup.is_duplicate(fp, title, issue, file_path)

                    suppressed = is_sup or is_dup
                    suppressed_reason = sup_reason or dup_reason if suppressed else None

                    finding = Finding(
                        run_id=run_id,
                        file_path=file_path,
                        line_number=line_number,
                        diff_position=diff_position,
                        domain=domain,
                        confidence=confidence,
                        title=title,
                        issue=issue,
                        why_it_matters=raw.get("why_it_matters", ""),
                        fix_suggestion=raw.get("fix_suggestion", ""),
                        code_example=raw.get("code_example", ""),
                        fingerprint=fp,
                        suppressed=suppressed,
                        suppressed_reason=suppressed_reason,
                    )
                    db.add(finding)
                    raw["id"] = finding.id
                    raw["fingerprint"] = fp
                    finding_records.append(finding)

                await db.commit()

                # ── Step 9: Post comments ─────────────────────────────────
                poster = CommentPoster(
                    github_client=gh,
                    deduplicator=dedup,
                    owner=owner,
                    repo=repo,
                    pr_number=pr_number,
                    commit_sha=commit_sha,
                    dry_run=config.dry_run,
                    min_confidence=config.min_confidence,
                )

                postable = [
                    f for f in all_findings
                    if not f.get("suppressed_reason") and f.get("file_path")
                ]
                await log(f"📬 Posting {len(postable)} findings (after dedup/suppression)...")
                post_results = await poster.post_findings(postable, log_fn=log)

                # Update DB with posted status
                posted_count = sum(1 for r in post_results if r.posted)
                suppressed_count = sum(1 for r in post_results if r.reason in ("duplicate", "suppressed", "low_confidence"))

                for fr in finding_records:
                    for pr_res in post_results:
                        if pr_res.finding_id == fr.id:
                            fr.posted = pr_res.posted
                            if pr_res.github_comment_id:
                                fr.github_comment_id = pr_res.github_comment_id
                            break

                # ── Step 10: Finalize run ─────────────────────────────────
                cost_report = cost_tracker.report()
                cost_tracker.log_report()

                run.status = "completed"
                run.completed_at = datetime.utcnow()
                run.total_tokens = cost_report["total_tokens"]
                run.prompt_tokens = cost_report["total_prompt_tokens"]
                run.completion_tokens = cost_report["total_completion_tokens"]
                run.estimated_cost_usd = cost_report["estimated_cost_usd"]
                run.findings_count = len(all_findings)
                run.posted_count = posted_count
                run.suppressed_count = suppressed_count
                await db.commit()

                await log(f"✅ Review complete!")
                await log(
                    f"   {len(all_findings)} findings total | "
                    f"{posted_count} posted | "
                    f"{suppressed_count} suppressed/deduped"
                )
                await log(f"   Cost: ${cost_report['estimated_cost_usd']:.4f} ({cost_report['total_tokens']:,} tokens)")

                return {
                    "run_id": run_id,
                    "status": "completed",
                    "pr_url": pr_url,
                    "pr_number": pr_number,
                    "repo": repo_full,
                    "commit_sha": commit_sha,
                    "findings_count": len(all_findings),
                    "posted_count": posted_count,
                    "suppressed_count": suppressed_count,
                    "dry_run": config.dry_run,
                    "cost": cost_report,
                    "diff_stats": stats,
                }

            except Exception as e:
                logger.exception(f"Review run {run_id} failed: {e}")
                await log(f"❌ Run failed: {e}", "error")
                run.status = "failed"
                run.error_message = str(e)
                run.completed_at = datetime.utcnow()
                await db.commit()
                return {"run_id": run_id, "status": "failed", "error": str(e)}
