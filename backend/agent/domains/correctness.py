"""
Correctness domain analyzer.
Detects: null/None dereferences, logic errors, unchecked return values,
off-by-one errors, type mismatches, unhandled exceptions.
"""
from backend.agent.llm_client import call_llm, parse_findings
from backend.agent.chunker import DiffChunk

SYSTEM_PROMPT = """You are an expert code correctness reviewer. Analyze the provided code diff and identify ONLY real, concrete correctness bugs.

FOCUS ON:
- Null/None pointer dereferences (accessing attributes on potentially null values)
- Logic errors (wrong conditions, inverted boolean logic, dead code)
- Unchecked return values (ignoring error returns, ignoring None)
- Off-by-one errors (loop bounds, array indexing, range calculations)
- Type mismatches (passing wrong types, implicit coercions that lose data)
- Unhandled exceptions (bare except, swallowed errors, missing error handling)
- Resource leaks (unclosed files, connections, handles)
- Race conditions in concurrent code
- Integer overflow / underflow possibilities

STRICT RULES:
- Only report issues in ADDED lines (+) — do not critique removed code
- Assign confidence: HIGH (certain bug), MEDIUM (likely bug), LOW (possible issue)
- Do NOT report style, naming, or formatting issues
- Do NOT report subjective design preferences
- Every finding MUST have a concrete, actionable fix with a code example

Respond ONLY with valid JSON in this exact format:
{
  "findings": [
    {
      "line_number": <new line number as integer>,
      "diff_position": <diff position as integer>,
      "confidence": "HIGH|MEDIUM|LOW",
      "title": "<short title, max 80 chars>",
      "issue": "<what the bug is, 1-3 sentences>",
      "why_it_matters": "<impact if this bug hits production, 1-2 sentences>",
      "fix_suggestion": "<concrete fix description>",
      "code_example": "<corrected code snippet>"
    }
  ]
}

If there are no correctness issues, return: {"findings": []}
"""


async def analyze_correctness(chunk: DiffChunk, model: str | None = None) -> list[dict]:
    """Run correctness analysis on a diff chunk."""
    user_prompt = f"""Analyze this code diff for correctness bugs:

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
        f["domain"] = "correctness"
        f["prompt_tokens"] = response.prompt_tokens
        f["completion_tokens"] = response.completion_tokens

    return findings, response
