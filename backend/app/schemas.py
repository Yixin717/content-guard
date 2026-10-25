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
    audit_id: int
    draft_id: str
    title: Optional[str] = None
    angle_name: Optional[str] = None
    final_content: str
    reviewer: Optional[str] = None
    created_at: str


class HistoryResponse(BaseModel):
    items: List[HistoryItem]


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
