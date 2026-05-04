"""
Security domain analyzer.
Covers: OWASP Top 10, injection, hardcoded credentials, missing auth,
insecure deserialization, SSRF, path traversal, XSS, CSRF.
"""
from backend.agent.llm_client import call_llm, parse_findings
from backend.agent.chunker import DiffChunk

SYSTEM_PROMPT = """You are an expert application security engineer. Analyze the provided code diff for security vulnerabilities.

FOCUS ON (OWASP Top 10 + common CVE patterns):
- SQL/NoSQL/Command/LDAP injection vectors
- Hardcoded credentials, API keys, secrets, tokens
- Missing or bypassable authentication/authorization checks
- Insecure deserialization (eval, pickle.loads on untrusted data, yaml.load)
- Cross-Site Scripting (XSS) — unescaped user input in HTML output
- CSRF — state-changing endpoints missing CSRF protection
- Path traversal — user-controlled file paths
- SSRF — user-controlled URLs in server-side requests
- Sensitive data exposure — logging PII, secrets in responses
- Insecure random — using Math.random() or random() for security tokens
- Prototype pollution (JavaScript)
- XML External Entity (XXE) injection
- Open redirects
- Race conditions with security implications (TOCTOU)

STRICT RULES:
- Only report issues in ADDED lines (+)
- Assign confidence: HIGH (exploitable as written), MEDIUM (conditionally exploitable), LOW (theoretical)
- Do NOT report issues that require an attacker to already have admin access
- Every finding MUST have a concrete fix with code

Respond ONLY with valid JSON:
{
  "findings": [
    {
      "line_number": <integer>,
      "diff_position": <integer>,
      "confidence": "HIGH|MEDIUM|LOW",
      "title": "<short title>",
      "issue": "<what the vulnerability is>",
      "why_it_matters": "<exploitability and impact>",
      "fix_suggestion": "<how to fix it>",
      "code_example": "<secure code replacement>"
    }
  ]
}

If no security issues found: {"findings": []}
"""


async def analyze_security(chunk: DiffChunk, model: str | None = None) -> list[dict]:
    """Run security analysis on a diff chunk."""
    user_prompt = f"""Analyze this code diff for security vulnerabilities:

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
        f["domain"] = "security"
        f["prompt_tokens"] = response.prompt_tokens
        f["completion_tokens"] = response.completion_tokens

    return findings, response
