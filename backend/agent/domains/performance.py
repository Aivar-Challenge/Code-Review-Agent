"""
Performance domain analyzer.
Detects: N+1 queries, O(n²) loops, blocking I/O in async code,
unbounded queries, inefficient data structures.
"""
from backend.agent.llm_client import call_llm, parse_findings
from backend.agent.chunker import DiffChunk

SYSTEM_PROMPT = """You are an expert performance engineer. Analyze the provided code diff for performance issues that would impact production systems.

FOCUS ON:
- N+1 database query patterns (querying inside a loop)
- O(n²) or worse time complexity (nested loops over large collections)
- Blocking I/O in async/concurrent code (time.sleep, requests in asyncio, sync DB calls)
- Unbounded database queries missing LIMIT clauses
- Missing database indexes implied by query patterns
- Repeated expensive operations that should be cached
- Memory leaks — appending to global lists, infinite caches
- String concatenation in loops (use join or StringBuilder)
- Unnecessary serialization/deserialization in hot paths
- Fetching all rows to filter in application memory
- Loading entire file into memory when streaming is possible
- Excessive object creation in tight loops (GC pressure)
- Synchronous API calls in parallel code paths that could be batched
- Regex compilation inside loops (should be compiled once)

STRICT RULES:
- Only report issues in ADDED lines (+)
- Only report issues that would measurably impact performance at scale (10k+ requests/day or large datasets)
- Do NOT report micro-optimizations on cold paths
- Assign confidence: HIGH (definite perf problem), MEDIUM (likely perf problem under load), LOW (theoretical)
- Every finding MUST include the fixed code

Respond ONLY with valid JSON:
{
  "findings": [
    {
      "line_number": <integer>,
      "diff_position": <integer>,
      "confidence": "HIGH|MEDIUM|LOW",
      "title": "<short title>",
      "issue": "<what the performance issue is>",
      "why_it_matters": "<quantified impact: latency, throughput, memory>",
      "fix_suggestion": "<how to fix>",
      "code_example": "<optimized code>"
    }
  ]
}

If no performance issues found: {"findings": []}
"""


async def analyze_performance(chunk: DiffChunk, model: str | None = None) -> tuple:
    """Run performance analysis on a diff chunk."""
    user_prompt = f"""Analyze this code diff for performance issues:

Language: {chunk.language}
File: {chunk.file_path} (chunk {chunk.chunk_index + 1}/{chunk.total_chunks})

{chunk.raw_text}

Focus only on lines marked with + (added/changed lines).
"""
    response = await call_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        model=model,
        temperature=0.1,
    )

    findings = parse_findings(response.content)
    for f in findings:
        f["domain"] = "performance"
        f["prompt_tokens"] = response.prompt_tokens
        f["completion_tokens"] = response.completion_tokens

    return findings, response
