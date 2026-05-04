"""
Synthesis analyzer — runs after all per-chunk analyses to catch
cross-chunk and cross-file issues that individual chunk analyses miss.
"""
import json
from backend.agent.llm_client import call_llm, parse_findings

SYNTHESIS_SYSTEM_PROMPT = """You are an expert code reviewer doing a final synthesis pass.
You have already seen individual findings from chunk-level analysis.
Your job is to identify CROSS-CHUNK and CROSS-FILE issues that the individual analyses couldn't see.

LOOK FOR:
- A function changed in one file is called incorrectly in another file shown in the diff
- An API contract changed in one place but callers in other changed files don't match
- A new database migration implies changes needed in ORM models not present
- New configuration keys used in code but not added to config schema
- Circular dependencies introduced by the changes
- Inconsistent error handling strategy across changed files
- New exception types raised but not caught anywhere in the changed code

STRICT RULES:
- Only report issues that REQUIRE seeing multiple files/chunks together
- Do NOT repeat findings already obvious from single-chunk analysis
- HIGH: Definite breakage that crosses file boundaries
- MEDIUM: Likely inconsistency
- LOW: Suppress

Respond ONLY with valid JSON:
{
  "findings": [
    {
      "file_path": "<primary affected file>",
      "line_number": null,
      "diff_position": null,
      "confidence": "HIGH|MEDIUM",
      "title": "<short title>",
      "issue": "<cross-file issue description>",
      "why_it_matters": "<impact>",
      "fix_suggestion": "<how to fix>",
      "code_example": "<example>"
    }
  ]
}

If no cross-chunk issues: {"findings": []}
"""


async def run_synthesis_pass(
    all_findings: list[dict],
    changed_files_summary: str,
    model: str | None = None,
) -> tuple[list[dict], object]:
    """
    Run synthesis analysis over all collected findings.
    Returns additional cross-file findings.
    """
    findings_summary = json.dumps(
        [
            {
                "file": f.get("file_path", ""),
                "domain": f.get("domain", ""),
                "title": f.get("title", ""),
                "confidence": f.get("confidence", ""),
            }
            for f in all_findings[:50]  # cap to avoid huge prompts
        ],
        indent=2,
    )

    user_prompt = f"""Perform a synthesis analysis for this PR.

Changed files in PR:
{changed_files_summary}

Individual findings found so far:
{findings_summary}

Identify any cross-file or cross-chunk issues not captured above.
"""
    response = await call_llm(
        system_prompt=SYNTHESIS_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        model=model,
        temperature=0.1,
    )

    findings = parse_findings(response.content)
    for f in findings:
        f["domain"] = f.get("domain", "correctness")
        f["is_synthesis"] = True
        f["prompt_tokens"] = response.prompt_tokens
        f["completion_tokens"] = response.completion_tokens

    return findings, response
