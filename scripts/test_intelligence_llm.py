"""Manual smoke test for B4.3 LLM structured extraction.

Not invoked by pytest. Requires a real LLM_API_KEY in the environment / .env.
Does not access the public internet for source content.

Usage (project root):

    uv run python scripts/test_intelligence_llm.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.domains.intelligence.llm.analyzer import LLMIntelligenceAnalyzer
from app.domains.intelligence.rules.analyzer import RuleAnalyzer
from app.domains.intelligence.schemas import ContentIntelligenceInput
from app.integrations.llm.factory import create_llm_provider

SAMPLE_TEXT = """【重磅】最高补贴500万元，名额有限，错过再等一年！

现组织开展2026年度科技创新项目申报工作。支持对象为在北京市注册的科技型企业。
申报截止时间为2026年9月30日。最高支持100万元。

如需申报辅导，请立即联系我们的项目顾问，全程代办服务，提高通过率。
"""


def main() -> int:
    if not (settings.LLM_API_KEY or "").strip() or settings.LLM_PROVIDER.lower() in {"fake", "stub"}:
        print("Set LLM_API_KEY and LLM_PROVIDER to a real provider before running this script.")
        print("pytest is not allowed to call this script or any real LLM.")
        return 1

    payload = ContentIntelligenceInput(
        source_id=uuid4(),
        ingestion_id=uuid4(),
        title="最高补贴500万！立即咨询",
        publisher="某企业服务机构",
        source_url="https://example.com/marketing-policy",
        normalized_text=SAMPLE_TEXT,
    )
    rules = RuleAnalyzer().analyze(payload)
    extraction = LLMIntelligenceAnalyzer(create_llm_provider()).analyze(payload, rules)
    result = extraction.intelligence_result
    claim = result.opportunity_claim

    print(f"content_nature: {result.analysis.content_nature}")
    print(f"opportunity_relevance: {result.analysis.opportunity_relevance}")
    print(f"apparent_source_type: {result.source_assessment.apparent_source_type}")
    print(f"marketing_level: {result.source_assessment.marketing_level}")
    print(f"intermediary_level: {result.source_assessment.intermediary_level}")
    print(f"claimed_title: {None if claim is None else claim.claimed_title}")
    print(f"claimed_issuer: {None if claim is None else claim.claimed_issuer}")
    print(f"claimed_deadline: {None if claim is None else claim.claimed_deadline}")
    print(f"requirements count: {0 if claim is None else len(claim.claimed_requirements)}")
    print(f"evidence count: {len(result.evidence)}")
    print(f"provider: {extraction.provider}")
    print(f"model: {extraction.model}")
    print(f"prompt_version: {extraction.prompt_version}")
    print(
        "token usage: "
        f"in={extraction.usage.input_tokens} "
        f"out={extraction.usage.output_tokens} "
        f"total={extraction.usage.total_tokens} "
        f"cost={extraction.usage.estimated_cost}"
    )
    print(f"latency_ms: {extraction.latency_ms}")
    print(f"warnings: {result.analysis.warnings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
