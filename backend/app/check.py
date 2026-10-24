"""检查器：规则检索 → LLM 逐条核对 → 幻觉防护（rule_id 必须真实存在）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .llm import LLM
from .prompts import CHECKER_SYSTEM, build_check_prompt
from .rules import Rule, load_rules, retrieve


class ViolationPayload(BaseModel):
    rule_id: str
    quote: str = ""
    severity: str = "medium"
    suggestion: str = ""
    confidence: float = 0.0


class CheckPayload(BaseModel):
    violations: List[ViolationPayload] = Field(default_factory=list)
    human_review: bool = False
    reason: str = ""


@dataclass
class Violation:
    rule_id: str
    rule_title: str
    source: str
    quote: str
    severity: str
    suggestion: str
    confidence: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "rule_title": self.rule_title,
            "source": self.source,
            "quote": self.quote,
            "severity": self.severity,
            "suggestion": self.suggestion,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class CheckResult:
    violations: List[Violation] = field(default_factory=list)
    human_review: bool = False
    reason: str = ""
    dropped_unknown_rule_ids: List[str] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "violations": [v.to_dict() for v in self.violations],
            "human_review": self.human_review,
            "reason": self.reason,
            "dropped_unknown_rule_ids": self.dropped_unknown_rule_ids,
            "usage": self.usage,
        }


def check_text(
    title: str,
    script: str,
    rules: Optional[List[Rule]] = None,
    llm: Optional[LLM] = None,
    top_k: int = 18,
) -> CheckResult:
    rules = rules if rules is not None else load_rules()
    llm = llm or LLM()
    by_id = {r.id: r for r in rules}

    candidates = retrieve(rules, f"{title}\n{script}", top_k=top_k)
    payload, usage = llm.chat_json(CHECKER_SYSTEM, build_check_prompt(title, script, candidates), CheckPayload)

    result = CheckResult(human_review=payload.human_review, reason=payload.reason.strip(), usage=usage)
    seen = set()
    for v in payload.violations:
        rule = by_id.get(v.rule_id.strip())
        if rule is None:  # 模型编了一个不存在的 rule_id
            result.dropped_unknown_rule_ids.append(v.rule_id)
            continue
        if rule.id in seen:
            continue
        seen.add(rule.id)
        result.violations.append(
            Violation(
                rule_id=rule.id,
                rule_title=rule.title,
                source=rule.source,
                quote=v.quote.strip(),
                severity=(v.severity or rule.severity).strip(),
                suggestion=v.suggestion.strip(),
                confidence=float(v.confidence or 0.0),
            )
        )

    order = {"high": 0, "medium": 1, "low": 2}
    result.violations.sort(key=lambda x: order.get(x.severity, 9))
    if not result.violations and not result.human_review:
        result.reason = result.reason or "未发现明确违规，建议人工复核"
        result.human_review = True
    return result
