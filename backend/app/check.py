"""检查器：规则检索 → LLM 逐条核对 → 幻觉防护 + 引用校验 + 置信度分流。

三道工程护栏（都是被真实误报逼出来的）：
1. rule_id 必须真实存在，否则丢弃；
2. quote 必须在草稿中逐字出现，否则丢弃（防止模型"总结"而非"引用"）；
3. confidence 低于阈值的不进 violations，进 uncertain —— 误报比漏报更伤信任。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .llm import LLM
from .prompts import CHECKER_SYSTEM, build_check_prompt
from .rules import Rule, load_rules, retrieve

CONFIDENCE_THRESHOLD = 0.7


class ViolationPayload(BaseModel):
    rule_id: str
    quote: str = ""
    severity: str = "medium"
    suggestion: str = ""
    confidence: float = 0.0


class SuspectedPayload(BaseModel):
    """疑似有问题、但规则库没有对应条款的情况 —— 不硬套 rule_id。"""

    quote: str = ""
    reason: str = ""
    severity: str = "medium"


class CheckPayload(BaseModel):
    violations: List[ViolationPayload] = Field(default_factory=list)
    suspected: List[SuspectedPayload] = Field(default_factory=list)
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
    # 条款原文与出处链接：中栏要显示「违反了哪一条的哪句话」，不能只有一个标题
    clause: str = ""
    source_url: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "rule_title": self.rule_title,
            "source": self.source,
            "source_url": self.source_url,
            "quote": self.quote,
            "clause": self.clause,
            "severity": self.severity,
            "suggestion": self.suggestion,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class Suspected:
    quote: str
    reason: str
    severity: str = "medium"

    def to_dict(self) -> Dict[str, object]:
        return {"quote": self.quote, "reason": self.reason, "severity": self.severity}


@dataclass
class CheckResult:
    violations: List[Violation] = field(default_factory=list)
    suspected: List[Suspected] = field(default_factory=list)
    uncertain: List[Violation] = field(default_factory=list)
    human_review: bool = False
    reason: str = ""
    dropped_unknown_rule_ids: List[str] = field(default_factory=list)
    dropped_quotes: List[str] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "violations": [v.to_dict() for v in self.violations],
            "uncertain": [v.to_dict() for v in self.uncertain],
            "suspected": [s.to_dict() for s in self.suspected],
            "human_review": self.human_review,
            "reason": self.reason,
            "dropped_unknown_rule_ids": self.dropped_unknown_rule_ids,
            "dropped_quotes": self.dropped_quotes,
            "usage": self.usage,
        }


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def check_text(
    title: str,
    script: str,
    rules: Optional[List[Rule]] = None,
    llm: Optional[LLM] = None,
    top_k: int = 18,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
) -> CheckResult:
    rules = rules if rules is not None else load_rules()
    llm = llm or LLM()
    by_id = {r.id: r for r in rules}
    draft_norm = _norm(f"{title}\n{script}")

    candidates = retrieve(rules, f"{title}\n{script}", top_k=top_k)
    payload, usage = llm.chat_json(CHECKER_SYSTEM, build_check_prompt(title, script, candidates), CheckPayload)

    result = CheckResult(human_review=payload.human_review, reason=payload.reason.strip(), usage=usage)
    seen = set()
    for v in payload.violations:
        rule = by_id.get(v.rule_id.strip())
        if rule is None:  # 模型编了一个不存在的 rule_id
            result.dropped_unknown_rule_ids.append(v.rule_id)
            continue
        quote = v.quote.strip()
        if quote and _norm(quote) not in draft_norm:  # 引用不是原文，而是模型的转述
            result.dropped_quotes.append(quote)
            continue
        if rule.id in seen:
            continue
        seen.add(rule.id)
        item = Violation(
            rule_id=rule.id,
            rule_title=rule.title,
            source=rule.source,
            quote=quote,
            severity=(v.severity or rule.severity).strip(),
            suggestion=v.suggestion.strip(),
            confidence=float(v.confidence or 0.0),
            clause=rule.quote,
            source_url=rule.source_url,
        )
        if item.confidence < confidence_threshold:
            result.uncertain.append(item)
        else:
            result.violations.append(item)

    for s in payload.suspected:
        quote = s.quote.strip()
        if quote and _norm(quote) not in draft_norm:
            result.dropped_quotes.append(quote)
            continue
        result.suspected.append(Suspected(quote=quote, reason=s.reason.strip(), severity=s.severity or "medium"))

    # 按「在原文里出现的位置」从上往下排：用户是逐行读的，
    # 编号 ①②③ 必须跟阅读顺序一致；同一位置再按严重度排。
    order = {"high": 0, "medium": 1, "low": 2}
    draft_text = f"{title}\n{script}"

    def _pos(v: Violation) -> int:
        idx = draft_text.find(v.quote)
        return idx if idx >= 0 else 10**9

    result.violations.sort(key=lambda x: (_pos(x), order.get(x.severity, 9)))
    result.uncertain.sort(key=lambda x: order.get(x.severity, 9))

    if result.suspected:
        result.human_review = True
    if not result.violations and not result.human_review:
        result.human_review = True
        result.reason = result.reason or "未发现可确证的违规，建议人工复核"
    return result
