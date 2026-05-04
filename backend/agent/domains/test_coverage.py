"""
Test coverage domain analyzer.
Identifies risky changes (new functions, business logic, error paths)
that lack corresponding test additions in the PR.
"""
from backend.agent.llm_client import call_llm, parse_findings
from backend.agent.chunker import DiffChunk

SYSTEM_PROMPT = """You are an expert software engineer specializing in test strategy. Analyze the provided code diff to identify risky changes that have NO corresponding tests in the PR.

LOOK FOR RISKY UNTESTED CHANGES:
- New public functions or methods with complex logic
- New error handling paths (try/except blocks without test for the exception)
- New conditional branches with significant business logic
- New API endpoints with no test file additions visible in the diff
- Changes to authentication/authorization logic
- Changes to data validation logic
- Changes to financial calculations or sensitive computations
- Changes to state machine transitions
- New integrations with external services

DO NOT FLAG:
- Private/internal helper functions with simple logic
- Simple getters/setters with no logic
- Configuration changes
- Documentation updates
- Refactors that preserve existing behavior (if tests exist)
- Changes that ARE covered by visible test additions in the diff

STRICT RULES:
- Only report on ADDED lines (+) representing new risky logic
- HIGH: New critical path (auth, payment, data integrity) with zero test additions in PR
- MEDIUM: New complex logic that is testable but lacks test additions
- LOW: Simple changes where absence of tests is a minor gap
- Do NOT penalize for not testing things that are hard to test (infra code, config)
- Suggest SPECIFIC test cases, not generic "add tests"

Respond ONLY with valid JSON:
{
  "findings": [
    {
      "line_number": <integer>,
      "diff_position": <integer>,
      "confidence": "HIGH|MEDIUM|LOW",
      "title": "<short title>",
      "issue": "<what risky change is untested>",
      "why_it_matters": "<what could break silently without this test>",
      "fix_suggestion": "<specific test cases to add>",
      "code_example": "<example test code>"
    }
  ]
}

If coverage looks adequate: {"findings": []}
"""


async def analyze_test_coverage(chunk: DiffChunk, all_files_context: str = "", model: str | None = None) -> tuple:
    """
    Run test coverage analysis on a diff chunk.
    all_files_context: names of all changed files in the PR for broader context.
    """
    user_prompt = f"""Analyze this code diff for risky changes that lack test coverage:

Language: {chunk.language}
File: {chunk.file_path} (chunk {chunk.chunk_index + 1}/{chunk.total_chunks})

All changed files in this PR:
{all_files_context or "Not available"}

{chunk.raw_text}

Focus only on lines marked with + (added/changed lines).
Identify which new behaviors are NOT covered by test additions visible in the diff.
"""
    response = await call_llm(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        model=model,
        temperature=0.1,
    )

    findings = parse_findings(response.content)
    for f in findings:
        f["domain"] = "test_coverage"
        f["prompt_tokens"] = response.prompt_tokens
        f["completion_tokens"] = response.completion_tokens

    return findings, response
