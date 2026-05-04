"""
Cost tracker — tracks token usage and estimates USD cost per run.
"""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("agent.cost")

# Pricing per 1M tokens (input / output) as of 2024
PRICING: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    # Anthropic
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    # Google
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 3.50, "output": 10.50},
}


@dataclass
class DomainUsage:
    domain: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class CostTracker:
    model: str
    _domains: dict[str, DomainUsage] = field(default_factory=dict)

    def record(self, domain: str, prompt_tokens: int, completion_tokens: int):
        if domain not in self._domains:
            self._domains[domain] = DomainUsage(domain=domain)
        d = self._domains[domain]
        d.prompt_tokens += prompt_tokens
        d.completion_tokens += completion_tokens
        d.calls += 1

    def _price_per_token(self, kind: str) -> float:
        """Price per single token (not per million)."""
        pricing = PRICING.get(self.model, {"input": 0.15, "output": 0.60})
        return pricing[kind] / 1_000_000

    @property
    def total_prompt_tokens(self) -> int:
        return sum(d.prompt_tokens for d in self._domains.values())

    @property
    def total_completion_tokens(self) -> int:
        return sum(d.completion_tokens for d in self._domains.values())

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens

    @property
    def estimated_cost_usd(self) -> float:
        cost = (
            self.total_prompt_tokens * self._price_per_token("input")
            + self.total_completion_tokens * self._price_per_token("output")
        )
        return round(cost, 6)

    def report(self) -> dict:
        domains_report = {}
        for domain, usage in self._domains.items():
            domain_cost = (
                usage.prompt_tokens * self._price_per_token("input")
                + usage.completion_tokens * self._price_per_token("output")
            )
            domains_report[domain] = {
                "calls": usage.calls,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "estimated_cost_usd": round(domain_cost, 6),
            }

        return {
            "model": self.model,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "domains": domains_report,
        }

    def log_report(self):
        report = self.report()
        logger.info("=" * 50)
        logger.info(f"COST REPORT — Model: {report['model']}")
        logger.info(f"Total tokens: {report['total_tokens']:,}")
        logger.info(f"  Prompt: {report['total_prompt_tokens']:,}")
        logger.info(f"  Completion: {report['total_completion_tokens']:,}")
        logger.info(f"Estimated cost: ${report['estimated_cost_usd']:.4f}")
        for domain, d in report["domains"].items():
            logger.info(
                f"  [{domain}] {d['calls']} calls, "
                f"{d['total_tokens']:,} tokens, "
                f"${d['estimated_cost_usd']:.4f}"
            )
        logger.info("=" * 50)
