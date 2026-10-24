"""改写：按违规项生成合规版本，并给出可核对的 diff。

设计取舍：
- 只让模型改「违规句」，其余原样（prompt 里强制），这样 diff 才有意义；
- diff 按中文句读切分后比对，粒度是"句子"，不是字符；商家要的是"哪句被改了"；
- 改完立刻复检（第二个检查器调用），用"违规数下降"量化效果，而不是自称"改好了"。
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .check import CheckResult, check_text
from .llm import LLM
from .prompts import REWRITER_SYSTEM, build_rewrite_prompt
from .rules import Rule, load_rules


class ChangePayload(BaseModel):
    before: str = ""
    after: str = ""
    reason: str = ""
    rule_ids: List[str] = Field(default_factory=list)


class RewritePayload(BaseModel):
    title: str = ""
    hook: str = ""
    script: str = ""
    selling_points: List[str] = Field(default_factory=list)
    changes: List[ChangePayload] = Field(default_factory=list)


@dataclass
class RewriteResult:
    title: str
    hook: str
    script: str
    selling_points: List[str]
    changes: List[ChangePayload]
    before_check: CheckResult
    after_check: Optional[CheckResult] = None
    rounds: int = 1
    usage: Dict[str, int] = field(default_factory=dict)

    @property
    def violation_reduction(self) -> Optional[float]:
        before = len(self.before_check.violations)
        if before == 0:
            return None
        after = len(self.after_check.violations) if self.after_check else before
        return (before - after) / before

    def to_dict(self) -> Dict[str, object]:
        return {
            "title": self.title,
            "hook": self.hook,
            "script": self.script,
            "selling_points": self.selling_points,
            "changes": [c.model_dump() for c in self.changes],
            "before_violations": len(self.before_check.violations),
            "after_violations": len(self.after_check.violations) if self.after_check else None,
            "rounds": self.rounds,
            "violation_reduction": (
                round(self.violation_reduction, 3) if self.violation_reduction is not None else None
            ),
            "usage": self.usage,
        }


_CLAUSE_RE = re.compile(r"(?<=[。！？；\n])")


def split_clauses(text: str) -> List[str]:
    """按中文句读切成句子，保留标点，用于 diff 对齐。"""
    return [c for c in _CLAUSE_RE.split(text) if c.strip()]


def sentence_diff(before: str, after: str) -> List[Dict[str, str]]:
    """句子级 diff：返回 删/增/改 三类变更，便于前端高亮。"""
    a, b = split_clauses(before), split_clauses(after)
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    changes: List[Dict[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changes.append(
            {
                "type": tag,  # replace / delete / insert
                "before": "".join(a[i1:i2]).strip(),
                "after": "".join(b[j1:j2]).strip(),
            }
        )
    return changes


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
    """按违规项改写；verify=True 时复检，未清零则再改一轮（最多 max_rounds 轮）。"""
    rules = rules if rules is not None else load_rules()
    llm = llm or LLM()

    before_check = check
    cur_title, cur_hook, cur_script = title, hook or "", script
    all_changes: List[ChangePayload] = []
    usage_total: Dict[str, int] = {"tokens_in": 0, "tokens_out": 0, "latency_ms": 0, "attempts": 0}
    current_check = check
    selling_points: List[str] = []
    rounds = 0

    while rounds < max_rounds and current_check.violations:
        rounds += 1
        remaining = [v.to_dict() for v in current_check.violations]
        payload, usage = llm.chat_json(
            REWRITER_SYSTEM,
            build_rewrite_prompt(cur_title, cur_hook, cur_script, remaining, rules),
            RewritePayload,
        )
        for k in usage_total:
            usage_total[k] += usage.get(k, 0)

        cur_title = payload.title.strip() or cur_title
        cur_hook = payload.hook.strip() or cur_hook
        cur_script = payload.script.strip() or cur_script
        selling_points = [p.strip() for p in payload.selling_points if p.strip()] or selling_points
        all_changes.extend(payload.changes)

        if not verify:
            break
        current_check = check_text(cur_title, cur_script, rules=rules, llm=llm)

    return RewriteResult(
        title=cur_title,
        hook=cur_hook,
        script=cur_script,
        selling_points=selling_points,
        changes=all_changes,
        before_check=before_check,
        after_check=current_check if verify else None,
        rounds=max(rounds, 1),
        usage=usage_total,
    )
