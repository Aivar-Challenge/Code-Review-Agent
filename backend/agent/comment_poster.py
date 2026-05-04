"""
Comment poster — formats and posts findings to GitHub Review API.
Handles confidence gating (HIGH → REQUEST_CHANGES, MEDIUM → COMMENT).
Supports dry-run mode.
"""
import logging
from dataclasses import dataclass

from backend.agent.github_client import GitHubClient
from backend.agent.deduplicator import Deduplicator

logger = logging.getLogger("agent.poster")

DOMAIN_EMOJI = {
    "correctness": "🐛",
    "security": "🔐",
    "performance": "⚡",
    "test_coverage": "🧪",
}

CONFIDENCE_BADGE = {
    "HIGH": "🔴 **HIGH CONFIDENCE** — This is a blocking issue.",
    "MEDIUM": "🟡 **MEDIUM CONFIDENCE** — This is a suggestion.",
}


def format_comment_body(finding: dict) -> str:
    """Format a finding into a rich GitHub comment body."""
    domain = finding.get("domain", "correctness")
    confidence = finding.get("confidence", "MEDIUM")
    title = finding.get("title", "Issue found")
    issue = finding.get("issue", "")
    why = finding.get("why_it_matters", "")
    fix = finding.get("fix_suggestion", "")
    code_example = finding.get("code_example", "")

    emoji = DOMAIN_EMOJI.get(domain, "⚠️")
    badge = CONFIDENCE_BADGE.get(confidence, "")

    lines = [
        f"## {emoji} [{domain.upper()}] {title}",
        "",
        badge,
        "",
        "### 🔍 What the issue is",
        issue,
        "",
        "### ❗ Why it matters",
        why,
        "",
        "### ✅ Suggested fix",
        fix,
    ]

    if code_example:
        lines.extend([
            "",
            "```",
            code_example,
            "```",
        ])

    lines.extend([
        "",
        "---",
        "*Posted by [Code Review Agent](https://github.com) · "
        f"Domain: `{domain}` · Confidence: `{confidence}`*",
    ])

    return "\n".join(lines)


@dataclass
class PostResult:
    finding_id: str
    posted: bool
    dry_run: bool
    reason: str  # posted | duplicate | suppressed | low_confidence | dry_run
    github_comment_id: str | None = None


class CommentPoster:
    def __init__(
        self,
        github_client: GitHubClient,
        deduplicator: Deduplicator,
        owner: str,
        repo: str,
        pr_number: int,
        commit_sha: str,
        dry_run: bool = False,
        min_confidence: str = "MEDIUM",
    ):
        self.gh = github_client
        self.dedup = deduplicator
        self.owner = owner
        self.repo = repo
        self.pr_number = pr_number
        self.commit_sha = commit_sha
        self.dry_run = dry_run
        self.min_confidence = min_confidence

        self._confidence_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        self._pending_high: list[dict] = []
        self._pending_medium: list[dict] = []

    def _passes_confidence_gate(self, confidence: str) -> bool:
        return (
            self._confidence_order.get(confidence, 0)
            >= self._confidence_order.get(self.min_confidence, 2)
        )

    def _get_position(self, finding: dict) -> int | None:
        """Get GitHub diff position for anchoring the comment."""
        # Prefer explicit diff_position, fall back to line_number
        pos = finding.get("diff_position")
        if pos and isinstance(pos, int) and pos > 0:
            return pos
        ln = finding.get("line_number")
        if ln and isinstance(ln, int) and ln > 0:
            return ln
        return None

    async def post_findings(
        self,
        findings: list[dict],
        log_fn=None,
    ) -> list[PostResult]:
        """
        Post all eligible findings to GitHub.
        Groups HIGH findings into REQUEST_CHANGES and MEDIUM into COMMENT.
        """
        results: list[PostResult] = []

        for finding in findings:
            finding_id = finding.get("id", "")
            confidence = finding.get("confidence", "LOW")
            file_path = finding.get("file_path", "")
            title = finding.get("title", "")
            issue = finding.get("issue", "")
            domain = finding.get("domain", "")

            # LOW confidence gate
            if not self._passes_confidence_gate(confidence):
                msg = f"Suppressed (LOW confidence): [{domain}] {title} in {file_path}"
                logger.debug(msg)
                if log_fn:
                    await log_fn(msg, level="debug")
                results.append(PostResult(finding_id, False, self.dry_run, "low_confidence"))
                continue

            # Compute fingerprint for dedup
            from backend.agent.deduplicator import compute_fingerprint
            fp = compute_fingerprint(
                file_path=file_path,
                line_number=finding.get("line_number"),
                domain=domain,
                title=title,
                issue=issue,
            )
            finding["fingerprint"] = fp

            # Suppression check
            is_suppressed, supp_reason = self.dedup.is_suppressed(file_path, domain, title, issue)
            if is_suppressed:
                msg = f"Suppressed by rule: [{domain}] {title} — {supp_reason}"
                logger.info(msg)
                if log_fn:
                    await log_fn(msg, level="info")
                results.append(PostResult(finding_id, False, self.dry_run, "suppressed"))
                continue

            # Deduplication check
            is_dup, dup_reason = self.dedup.is_duplicate(fp, title, issue, file_path)
            if is_dup:
                msg = f"Duplicate ({dup_reason}): [{domain}] {title} in {file_path}"
                logger.info(msg)
                if log_fn:
                    await log_fn(msg, level="info")
                results.append(PostResult(finding_id, False, self.dry_run, "duplicate"))
                continue

            # Queue by confidence
            if confidence == "HIGH":
                self._pending_high.append(finding)
            else:
                self._pending_medium.append(finding)

        # Post all HIGH as REQUEST_CHANGES
        if self._pending_high:
            high_results = await self._post_review(
                self._pending_high,
                event="REQUEST_CHANGES",
                body=f"🔴 **Code Review Agent found {len(self._pending_high)} blocking issue(s).**\n\nSee inline comments below.",
                log_fn=log_fn,
            )
            results.extend(high_results)
            self._pending_high.clear()

        # Post MEDIUM as COMMENT
        if self._pending_medium:
            med_results = await self._post_review(
                self._pending_medium,
                event="COMMENT",
                body=f"💡 **Code Review Agent has {len(self._pending_medium)} suggestion(s).**",
                log_fn=log_fn,
            )
            results.extend(med_results)
            self._pending_medium.clear()

        return results

    async def _post_review(
        self,
        findings: list[dict],
        event: str,
        body: str,
        log_fn=None,
    ) -> list[PostResult]:
        """Post a batch of findings as a single GitHub review."""
        results: list[PostResult] = []

        # Build GitHub review comments
        review_comments = []
        valid_findings = []

        for finding in findings:
            position = self._get_position(finding)
            if position is None:
                msg = f"Skipping (no position): [{finding.get('domain')}] {finding.get('title')} in {finding.get('file_path')}"
                logger.warning(msg)
                if log_fn:
                    await log_fn(msg, level="warning")
                results.append(PostResult(finding.get("id", ""), False, self.dry_run, "no_position"))
                continue

            review_comments.append({
                "path": finding["file_path"],
                "position": position,
                "body": format_comment_body(finding),
            })
            valid_findings.append(finding)

        if not review_comments:
            return results

        if self.dry_run:
            for finding in valid_findings:
                msg = (
                    f"[DRY RUN] Would post [{finding['domain'].upper()}] "
                    f"{finding['confidence']} — {finding['title']} "
                    f"@ {finding['file_path']}:{finding.get('line_number')}"
                )
                logger.info(msg)
                if log_fn:
                    await log_fn(msg, level="info")
            results.extend([
                PostResult(f.get("id", ""), False, True, "dry_run")
                for f in valid_findings
            ])
            return results

        # Post to GitHub
        try:
            review = await self.gh.create_review(
                owner=self.owner,
                repo=self.repo,
                pr_number=self.pr_number,
                commit_id=self.commit_sha,
                comments=review_comments,
                event=event,
                body=body,
            )
            review_id = str(review.get("id", ""))

            for finding in valid_findings:
                msg = (
                    f"✅ Posted [{finding['domain'].upper()}] {finding['confidence']} — "
                    f"{finding['title']} @ {finding['file_path']}"
                )
                logger.info(msg)
                if log_fn:
                    await log_fn(msg, level="success")

                # Mark in deduplicator
                await self.dedup.mark_posted(
                    fingerprint=finding["fingerprint"],
                    file_path=finding["file_path"],
                    github_comment_id=review_id,
                    commit_sha=self.commit_sha,
                )
                results.append(
                    PostResult(finding.get("id", ""), True, False, "posted", review_id)
                )

        except Exception as e:
            logger.error(f"Failed to post review: {e}")
            if log_fn:
                await log_fn(f"❌ Failed to post review: {e}", level="error")
            results.extend([
                PostResult(f.get("id", ""), False, False, f"error: {e}")
                for f in valid_findings
            ])

        return results
