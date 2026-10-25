"""API 的请求/响应模型。校验尽量前移到 Pydantic，业务层只处理"合法但不合理"的情况。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class GenerateRequest(BaseModel):
    brief: str = Field(min_length=5, max_length=500, description="商品简报")
    tone: str = Field(default="亲切、像朋友聊天", max_length=50)
    platform: str = Field(default="xiaohongshu", max_length=30)


class DraftOut(BaseModel):
    id: str
    angle: str
    angle_name: str
    title: str
    hook: str
    script: str
    selling_points: List[str]
    disclosure: str
    self_check: Optional[dict] = None


class GenerateResponse(BaseModel):
    product_id: str
    drafts: List[DraftOut]
    elapsed_ms: int
    tokens_in: int
    tokens_out: int
    # 本次请求的真实消耗（含自检与自动改写），供前端状态条显示
    usage: dict = {}


class CheckRequest(BaseModel):
    draft_id: Optional[str] = None
    content: Optional[str] = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def exactly_one_target(self):
        has_id = bool(self.draft_id and self.draft_id.strip())
        has_content = bool(self.content and self.content.strip())
        if has_id and has_content:
            raise ValueError("draft_id 与 content 只能传一个")
        if not has_id and not has_content:
            raise ValueError("必须提供 draft_id 或非空 content")
        return self


class ViolationOut(BaseModel):
    rule_id: str
    rule_title: str
    source: str
    quote: str
    severity: str
    suggestion: str
    confidence: float
    # 条款原文与出处：中栏要能直接看到「违反的是哪句话」
    clause: str = ""
    source_url: str = ""
    n: int = 0  # 全局编号，左/中/右三栏共用


class CheckResponse(BaseModel):
    draft_id: Optional[str] = None
    violations: List[ViolationOut]
    uncertain: List[ViolationOut]
    suspected: List[dict]
    human_review: bool
    reason: str
    dropped_unknown_rule_ids: List[str] = []
    dropped_quotes: List[str] = []
    # 本次请求的真实消耗，前端不得自行编造
    usage: dict = {}


class RewriteRequest(BaseModel):
    draft_id: str = Field(min_length=1)


class RewriteResponse(BaseModel):
    draft_id: str
    title: str
    script: str
    changes: List[dict]
    before_violations: int
    after_violations: int
    violation_reduction: Optional[float]
    rounds: int
    # 含前置检查 + 改写 + 复检的全部消耗
    usage: dict = {}


class ChangeOut(BaseModel):
    """一处违规 = 一条改动。status=fixed 时 start/end 指向改写后全文中的位置。"""

    n: int
    rule_id: str
    rule_title: str
    before: str
    after: str
    reason: str
    status: str  # fixed | unresolved
    start: int = -1
    end: int = -1


class RewriteOut(BaseModel):
    """一次 analyze 的改写结果：一条违规对应一条改动，不再带"复检残留"这种结论。"""

    title: str
    script: str
    changes: List[ChangeOut]
    rounds: int
    unresolved: int = 0


class AnalyzeResponse(BaseModel):
    """一次请求算完：检查 → 改写 → 复检。前端只呈现这一份结果。"""

    draft_id: Optional[str] = None
    title: str = ""
    script: str = ""
    violations: List[ViolationOut]
    uncertain: List[ViolationOut]
    suspected: List[dict]
    human_review: bool
    reason: str
    rewrite: Optional[RewriteOut] = None
    rewrite_error: Optional[str] = None
    usage: dict = {}


class ConfirmRequest(BaseModel):
    draft_id: str = Field(min_length=1)
    final_content: str = Field(min_length=1, max_length=5000)
    reviewer: str = Field(default="anonymous", max_length=50)
class ConfirmResponse(BaseModel):
    ok: bool = True
    audit_id: int
    idempotent: bool
    confirmed_at: str


class HistoryItem(BaseModel):
    """一条"查过"的记录。只带列表需要的字段，正文不在列表里传。"""

    id: int
    draft_id: Optional[str] = None
    title: Optional[str] = None
    violation_count: int = 0
    remaining_count: int = 0
    status: str = "checked"  # checked | confirmed
    created_at: str


class HistoryResponse(BaseModel):
    items: List[HistoryItem]


class EventDetailResponse(BaseModel):
    """点开一条历史：把当次的分析快照原样还给前端，用于恢复工作台。"""

    id: int
    created_at: str
    status: str
    draft_id: Optional[str] = None
    title: Optional[str] = None
    result: dict


class RuleOut(BaseModel):
    id: str
    category: str
    title: str
    quote: str
    source: str
    source_url: str
    severity: str
    status: str
    examples: str
    counter_examples: str
    note: str


class RulesResponse(BaseModel):
    total: int
    items: List[RuleOut]
