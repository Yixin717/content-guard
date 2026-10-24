"""FastAPI 应用：把 CLI 的流水线暴露成 HTTP 接口。

约定：
- 校验交给 Pydantic（缺参/空串 → 422），业务层只管"合法但不存在"（→ 404）；
- LLM 超时/坏 JSON → 504，并提示"转人工"（合规场景不假装成功）；
- 幂等：/api/confirm 靠 UNIQUE(draft_id)，重复调用返回同一 audit_id。
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .check import check_text
from .config import settings
from .generate import generate_drafts
from .llm import LLM, LLMError
from .rewrite import rewrite_draft
from .rules import load_rules
from .schemas import (
    CheckRequest,
    CheckResponse,
    ConfirmRequest,
    ConfirmResponse,
    GenerateRequest,
    GenerateResponse,
    HistoryResponse,
    RewriteRequest,
    RewriteResponse,
    RuleOut,
    RulesResponse,
)

ALLOWED_CATEGORIES = {"absolute", "false_claim", "platform"}


def get_llm() -> LLM:
    """工厂函数：测试里可以 monkeypatch 掉，避免真实调用。"""
    return LLM()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Content Guard API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _conn():
    return db.connect()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": settings.model, "rules": len(load_rules())}


@app.post("/api/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest, llm: LLM = Depends(get_llm)) -> GenerateResponse:
    started = time.time()
    product_id = f"p_{uuid.uuid4().hex[:10]}"
    try:
        drafts = generate_drafts(req.brief, tone=req.tone, platform=req.platform, llm=llm)
    except LLMError as exc:
        raise HTTPException(status_code=504, detail=f"模型调用失败，请重试或转人工：{exc}") from exc

    with _conn() as conn:
        db.insert_product(conn, product_id, req.brief, req.tone)
        for d in drafts:
            db.insert_draft(
                conn,
                {
                    "id": d.id, "product_id": product_id, "angle": d.angle, "angle_name": d.angle_name,
                    "title": d.title, "hook": d.hook, "script": d.script,
                    "selling_points": d.selling_points, "disclosure": d.disclosure,
                },
            )

    return GenerateResponse(
        product_id=product_id,
        drafts=[d.__dict__ for d in drafts],
        elapsed_ms=int((time.time() - started) * 1000),
        tokens_in=sum(d.usage.get("tokens_in", 0) for d in drafts),
        tokens_out=sum(d.usage.get("tokens_out", 0) for d in drafts),
    )


@app.post("/api/check", response_model=CheckResponse)
def check(req: CheckRequest, llm: LLM = Depends(get_llm)) -> CheckResponse:
    title, content, draft_id = "", req.content or "", None

    if req.draft_id:
        with _conn() as conn:
            row = db.get_draft(conn, req.draft_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"草稿不存在：{req.draft_id}")
        draft = db.draft_row_to_dict(row)
        title, content, draft_id = draft["title"], draft["script"], draft["id"]

    try:
        result = check_text(title, content, llm=llm)
    except LLMError as exc:
        raise HTTPException(status_code=504, detail=f"检查失败，请转人工：{exc}") from exc

    if draft_id:
        with _conn() as conn:
            for v in result.violations:
                db.save_check(conn, draft_id, "violation", v.to_dict())
            for v in result.uncertain:
                db.save_check(conn, draft_id, "uncertain", v.to_dict())
            for s in result.suspected:
                db.save_check(conn, draft_id, "suspected", s.to_dict())
            conn.execute("UPDATE drafts SET status='checked' WHERE id=?", (draft_id,))

    payload = result.to_dict()
    payload["draft_id"] = draft_id
    return CheckResponse(**payload)


@app.post("/api/rewrite", response_model=RewriteResponse)
def rewrite(req: RewriteRequest, llm: LLM = Depends(get_llm)) -> RewriteResponse:
    with _conn() as conn:
        row = db.get_draft(conn, req.draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"草稿不存在：{req.draft_id}")

    draft = db.draft_row_to_dict(row)
    try:
        base_check = check_text(draft["title"], draft["script"], llm=llm)
        if not base_check.violations:
            raise HTTPException(status_code=409, detail="该草稿没有可确证的违规，无需改写")
        result = rewrite_draft(draft["title"], draft.get("hook", ""), draft["script"], base_check, llm=llm)
    except LLMError as exc:
        raise HTTPException(status_code=504, detail=f"改写失败，请转人工：{exc}") from exc

    return RewriteResponse(
        draft_id=req.draft_id,
        title=result.title,
        script=result.script,
        changes=[c.model_dump() for c in result.changes],
        before_violations=len(base_check.violations),
        after_violations=len(result.after_check.violations) if result.after_check else 0,
        violation_reduction=result.violation_reduction,
        rounds=result.rounds,
    )


@app.post("/api/confirm", response_model=ConfirmResponse)
def confirm(req: ConfirmRequest) -> ConfirmResponse:
    with _conn() as conn:
        row = db.get_draft(conn, req.draft_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"草稿不存在：{req.draft_id}")
        saved = db.upsert_confirmation(conn, req.draft_id, req.final_content, req.reviewer)
    return ConfirmResponse(ok=True, **saved)


@app.get("/api/history", response_model=HistoryResponse)
def history(limit: int = Query(default=20, ge=1, le=100)) -> HistoryResponse:
    with _conn() as conn:
        rows = db.list_history(conn, limit=limit)
    return HistoryResponse(items=[dict(r) for r in rows])


@app.get("/api/rules", response_model=RulesResponse)
def rules(category: Optional[str] = Query(default=None)) -> RulesResponse:
    if category and category not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category 只能是 {sorted(ALLOWED_CATEGORIES)}")
    with _conn() as conn:
        rows = db.list_rules(conn, category=category)
    items = [RuleOut(**dict(r)) for r in rows]
    return RulesResponse(total=len(items), items=items)
