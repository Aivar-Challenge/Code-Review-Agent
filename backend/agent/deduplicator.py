"""
Deduplicator — prevents re-posting comments that already exist on the PR.

Strategy:
1. Fingerprint = SHA256(file_path + line_number + domain + semantic_summary)
2. Check DB for previously posted fingerprints for this PR
3. Semantic match against existing GitHub comments (keyword overlap)
4. Idempotent: same finding = same fingerprint regardless of commit SHA
"""
import hashlib
import logging
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.db.models import PostedComment, SuppressionRule

logger = logging.getLogger("agent.deduplicator")


def compute_fingerprint(
    file_path: str,
    line_number: int | None,
    domain: str,
    title: str,
    issue: str,
) -> str:
    """
    Compute a stable fingerprint for a finding.
    Uses semantic content (not line numbers that can shift).
    """
    # Normalize: lowercase, strip whitespace, remove punctuation
    def normalize(s: str) -> str:
        s = s.lower().strip()
        s = re.sub(r"[^\w\s]", "", s)
        s = re.sub(r"\s+", " ", s)
        return s[:200]  # cap length

    key = "|".join([
        file_path.lower(),
        domain.lower(),
        normalize(title),
        normalize(issue[:100]),
    ])
    return hashlib.sha256(key.encode()).hexdigest()


def semantic_overlap(text_a: str, text_b: str, threshold: float = 0.4) -> bool:
    """
    Simple keyword-based semantic similarity check.
    Returns True if texts share enough meaningful keywords.
    """
    def keywords(text: str) -> set:
        stop = {"the", "a", "an", "is", "in", "of", "to", "and", "or", "this", "that", "it", "be", "are", "was", "for"}
        tokens = re.findall(r"\b\w{3,}\b", text.lower())
        return {t for t in tokens if t not in stop}

    kw_a = keywords(text_a)
    kw_b = keywords(text_b)

    if not kw_a or not kw_b:
        return False

    intersection = kw_a & kw_b
    union = kw_a | kw_b
    jaccard = len(intersection) / len(union)
    return jaccard >= threshold


class Deduplicator:
    def __init__(self, db: AsyncSession, pr_url: str):
        self.db = db
        self.pr_url = pr_url
        self._posted_fingerprints: set[str] = set()
        self._github_comments: list[dict] = []
        self._suppression_rules: list[SuppressionRule] = []

    async def load(
        self,
        github_comments: list[dict],
        repo: str,
    ):
        """
        Load existing posted fingerprints from DB and existing GitHub comments.
        """
        # Load DB fingerprints
        result = await self.db.execute(
            select(PostedComment).where(PostedComment.pr_url == self.pr_url)
        )
        rows = result.scalars().all()
        self._posted_fingerprints = {r.fingerprint for r in rows}
        logger.info(
            f"Deduplicator: loaded {len(self._posted_fingerprints)} existing fingerprints from DB"
        )

        # Store GitHub comments for semantic matching
        self._github_comments = github_comments
        logger.info(
            f"Deduplicator: loaded {len(github_comments)} existing GitHub comments"
        )

        # Load suppression rules for this repo
        result = await self.db.execute(
            select(SuppressionRule).where(
                SuppressionRule.active == True,
                SuppressionRule.repo.in_([repo, "*"]),
            )
        )
        self._suppression_rules = result.scalars().all()
        logger.info(f"Deduplicator: loaded {len(self._suppression_rules)} suppression rules")

    def is_duplicate(
        self,
        fingerprint: str,
        title: str,
        issue: str,
        file_path: str,
    ) -> tuple[bool, str]:
        """
        Check if a finding is a duplicate.
        Returns (is_duplicate, reason).
        """
        # Check DB fingerprint
        if fingerprint in self._posted_fingerprints:
            return True, "fingerprint_match"

        # Semantic match against GitHub comments on same file
        relevant_comments = [
            c for c in self._github_comments
            if c.get("path") == file_path
        ]
        for comment in relevant_comments:
            body = comment.get("body", "")
            finding_text = f"{title} {issue}"
            if semantic_overlap(finding_text, body):
                return True, "semantic_match"

        return False, ""

    def is_suppressed(
        self,
        file_path: str,
        domain: str,
        title: str,
        issue: str,
    ) -> tuple[bool, str]:
        """Check if a finding matches any suppression rule."""
        import fnmatch
        for rule in self._suppression_rules:
            # File pattern match
            if rule.file_pattern and not fnmatch.fnmatch(file_path, rule.file_pattern):
                continue
            # Domain match
            if rule.domain and rule.domain != "*" and rule.domain != domain:
                continue
            # Keyword match
            if rule.keyword:
                combined = f"{title} {issue}".lower()
                if rule.keyword.lower() not in combined:
                    continue
            return True, rule.reason or "suppression_rule"
        return False, ""

    async def mark_posted(
        self,
        fingerprint: str,
        file_path: str,
        github_comment_id: str,
        commit_sha: str,
    ):
        """Record a posted comment in the DB."""
        self._posted_fingerprints.add(fingerprint)
        record = PostedComment(
            pr_url=self.pr_url,
            fingerprint=fingerprint,
            github_comment_id=github_comment_id,
            file_path=file_path,
            commit_sha=commit_sha,
        )
        self.db.add(record)
        await self.db.commit()
