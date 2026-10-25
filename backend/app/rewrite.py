"""改写：按违规项逐条「局部替换」，并给出可核对的 diff。

设计取舍（ADR-009）：

- **不让模型重写整篇**，只让它给每个违规片段一个能原地放回去的替换文本。
  这样「改动条数」恒等于「违规条数」，不会再出现"检查 2 处、改动冒 3 处"。
- **替换位置由服务端算**（start/end），前端高亮不靠字符串查找，不会错位或漏标。
- 模型没给出可用替换的，标 `unresolved` 交给人工，**绝不编一条改动凑数**。
- 改完立刻复检，用复检结果量化效果，而不是自称"改好了"。
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from .check import CheckResult, Violation, check_text
from .llm import LLM
from .prompts import REWRITER_SYSTEM, build_rewrite_prompt
from .rules import Rule, load_rules


class ReplacementPayload(BaseModel):
    """模型只需要回答：哪一条违规、换成什么。"""

    rule_id: str = ""
    before: str = ""  # 回显违规原文，便于精确匹配（同一规则可能命中多处）
    after: str = ""


class RewritePayload(BaseModel):
    replacements: List[ReplacementPayload] = Field(default_factory=list)


def _key(v: Violation) -> str:
    return f"{v.rule_id}|{v.quote}"


@dataclass
class Change:
    n: int
    rule_id: str
    rule_title: str
    before: str
    after: str
    reason: str
    status: str = "fixed"  # fixed | unresolved
    start: int = -1
    end: int = -1

    def to_dict(self) -> Dict[str, object]:
        return {
            "n": self.n,
            "rule_id": self.rule_id,
            "rule_title": self.rule_title,
            "before": self.before,
            "after": self.after,
            "reason": self.reason,
            "status": self.status,
            "start": self.start,
            "end": self.end,
        }


@dataclass
class RewriteResult:
    title: str
    hook: str
    script: str
    changes: List[Change] = field(default_factory=list)
    before_check: Optional[CheckResult] = None
    after_check: Optional[CheckResult] = None
    rounds: int = 0
    usage: Dict[str, int] = field(default_factory=dict)

    @property
    def violation_reduction(self) -> Optional[float]:
        if not self.before_check:
            return None
        before = len(self.before_check.violations)
        if before == 0:
            return None
        after = len(self.after_check.violations) if self.after_check else before
        return (before - after) / before

    @property
    def remaining(self) -> int:
        return len(self.after_check.violations) if self.after_check else 0

    @property
    def unresolved(self) -> int:
        return sum(1 for c in self.changes if c.status != "fixed")

    def to_dict(self) -> Dict[str, object]:
        return {
            "title": self.title,
            "hook": self.hook,
            "script": self.script,
            "changes": [c.to_dict() for c in self.changes],
            "before_violations": len(self.before_check.violations) if self.before_check else 0,
            "after_violations": len(self.after_check.violations) if self.after_check else 0,
            "remaining": self.remaining,
            "unresolved": self.unresolved,
            "rounds": self.rounds,
            "violation_reduction": (
                round(self.violation_reduction, 3) if self.violation_reduction is not None else None
            ),
            "usage": self.usage,
        }


def _acc(total: Dict[str, int], usage: Dict[str, int]) -> None:
    for k in ("tokens_in", "tokens_out", "latency_ms", "attempts"):
        total[k] += int(usage.get(k, 0) or 0)


def _insert_after(text: str, start: int, end: int, after: str, spans: List[Tuple[int, int, int]]):
    """把 text[start:end] 换成 after；已记录的 spans 同步平移，返回新文本与新 span。"""
    delta = len(after) - (end - start)
    shifted = [((s + delta, e + delta) if s >= end else (s, e)) for s, e in spans]
    new_text = text[:start] + after + text[end:]
    return new_text, shifted, (start, start + len(after))


def rewrite_draft(
    title: str,
    hook: str,
    script: str,
    check: CheckResult,
    rules: Optional[List[Rule]] = None,
    llm: Optional[LLM] = None,
    verify: bool = True,
    max_rounds: int = 2,
) -> RewriteResult:
    """逐条替换违规片段；verify=True 时复检，最多 max_rounds 轮。

    轮次只用于「上一轮没改出来的那几条」，不会去改检查阶段没报的问题。
    """
    rules = rules if rules is not None else load_rules()
    llm = llm or LLM()

    violations = list(check.violations)
    cur_title, cur_script = title, script
    usage_total = {"tokens_in": 0, "tokens_out": 0, "latency_ms": 0, "attempts": 0}

    applied: Dict[str, Dict[str, object]] = {}  # key -> {after, span}
    spans: List[Tuple[int, int]] = []  # 与 applied 中 script 级改动对应的位置，用于平移
    pending = list(violations)
    after_check: Optional[CheckResult] = None
    rounds = 0

    while rounds < max_rounds and pending:
        rounds += 1
        payload, usage = llm.chat_json(
            REWRITER_SYSTEM,
            build_rewrite_prompt(cur_title, "", cur_script, [v.to_dict() for v in pending], rules),
            RewritePayload,
        )
        _acc(usage_total, usage)

        progressed = False
        for rep in payload.replacements:
            target = _pick_target(pending, rep, applied)
            if target is None:  # 不在本轮清单里（模型越界），直接忽略
                continue
            after = (rep.after or "").strip()
            if not after or after == target.quote:  # 没改或原样返回，交给人工
                continue
            quote = target.quote
            key = _key(target)

            if quote in cur_title:
                cur_title = cur_title.replace(quote, after, 1)
                applied[key] = {"after": after, "span": None}
                progressed = True
            else:
                idx = cur_script.find(quote)
                if idx < 0:
                    continue
                cur_script, spans, span = _insert_after(cur_script, idx, idx + len(quote), after, spans)
                applied[key] = {"after": after, "span": span}
                progressed = True

        if verify:
            after_check = check_text(cur_title, cur_script, rules=rules, llm=llm)
            _acc(usage_total, after_check.usage)
        pending = [v for v in pending if _key(v) not in applied]
        if not progressed:
            break

    # 逐条给出改动：条数与违规条数严格一致
    changes: List[Change] = []
    for i, v in enumerate(violations, start=1):
        key = _key(v)
        record = applied.get(key)
        if record:
            span = record["span"] or (-1, -1)
            changes.append(
                Change(
                    n=i,
                    rule_id=v.rule_id,
                    rule_title=v.rule_title,
                    before=v.quote,
                    after=str(record["after"]),
                    reason=v.suggestion or "按条款要求修改",
                    status="fixed",
                    start=span[0],
                    end=span[1],
                )
            )
            continue
        # 没拿到替换：如果复检里已经没有这一条，说明被其他改动顺带消除
        gone = after_check is not None and not any(_key(x) == key for x in after_check.violations)
        changes.append(
            Change(
                n=i,
                rule_id=v.rule_id,
                rule_title=v.rule_title,
                before=v.quote,
                after="",
                reason="已随其他改动一并消除" if gone else "模型未给出可用替换，需人工修改",
                status="fixed" if gone else "unresolved",
                start=-1,
                end=-1,
            )
        )

    return RewriteResult(
        title=cur_title,
        hook=hook or "",
        script=cur_script,
        changes=changes,
        before_check=check,
        after_check=after_check if verify else None,
        rounds=rounds,
        usage=usage_total,
    )


def _pick_target(pending: List[Violation], rep: ReplacementPayload, applied: Dict[str, object]) -> Optional[Violation]:
    """把模型返回的一条替换，对应回本轮清单里的某条违规。"""
    rule_id = (rep.rule_id or "").strip()
    before = (rep.before or "").strip()
    for v in pending:
        if _key(v) in applied:
            continue
        if v.rule_id != rule_id:
            continue
        if before and before != v.quote:
            continue
        return v
    return None


# ---- 句子级 diff：仅用于命令行预览与排查，不再决定"改动条数" ----

_CLAUSE_RE = re.compile(r"(?<=[。！？；\n])")


def split_clauses(text: str) -> List[str]:
    """按中文句读切成句子，保留标点。"""
    return [c for c in _CLAUSE_RE.split(text) if c.strip()]


def sentence_diff(before: str, after: str) -> List[Dict[str, str]]:
    """句子级 diff：返回 删/增/改 三类变更。"""
    a, b = split_clauses(before), split_clauses(after)
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    changes: List[Dict[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changes.append(
            {
                "type": tag,
                "before": "".join(a[i1:i2]).strip(),
                "after": "".join(b[j1:j2]).strip(),
            }
        )
    return changes
