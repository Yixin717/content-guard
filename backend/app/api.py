"""FastAPI 应用：把 CLI 的流水线暴露成 HTTP 接口。

约定：
- 校验交给 Pydantic（缺参/空串 → 422），业务层只管"合法但不存在"（→ 404）；
- LLM 超时/坏 JSON → 504，并提示"转人工"（合规场景不假装成功）；
- 幂等：/api/confirm 靠 UNIQUE(draft_id)，重复调用返回同一 audit_id。
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .check import check_text
from .config import settings
from .generate import generate_drafts
from .llm import LLM, LLMError
from .rewrite import rewrite_draft
from .rules import load_rules
from .schemas import (
    AnalyzeResponse,
    ChangeOut,
    CheckRequest,
    CheckResponse,
    ConfirmRequest,
    ConfirmResponse,
    EventDetailResponse,
    GenerateRequest,
    GenerateResponse,
    HistoryResponse,
    RewriteOut,
    RewriteRequest,
    RewriteResponse,
    RuleOut,
    RulesResponse,
)

ALLOWED_CATEGORIES = {"absolute", "false_claim", "platform"}


# ---- 用量日志：一行一条，journalctl 里能直接和页面上的数字对上 ----
# 自己挂 handler 且不向上传播：uvicorn 的 logging 配置各不相同，这样能保证一定进 stderr。
usage_logger = logging.getLogger("content_guard.usage")
if not usage_logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    usage_logger.addHandler(_handler)
    usage_logger.setLevel(logging.INFO)
    usage_logger.propagate = False

USAGE_KEYS = ("tokens_in", "tokens_out", "latency_ms", "attempts")


def merge_usage(*usages: Optional[dict]) -> dict:
    """把多次 LLM 调用的 usage 相加；缺失字段按 0 处理。"""
    total = {k: 0 for k in USAGE_KEYS}
    for u in usages:
        for k in USAGE_KEYS:
            total[k] += int((u or {}).get(k, 0) or 0)
    return total


def log_usage(path: str, usage: dict, started: float, **fields: object) -> dict:
    """记录并补上整条请求的墙钟耗时（elapsed_ms），返回可直接塞进响应的 usage。"""
    usage = dict(usage)
    usage["elapsed_ms"] = int((time.time() - started) * 1000)
    extra = "".join(f" {k}={v}" for k, v in fields.items())
    usage_logger.info(
        "llm_usage path=%s tokens_in=%d tokens_out=%d llm_ms=%d elapsed_ms=%d attempts=%d%s",
        path,
        usage["tokens_in"],
        usage["tokens_out"],
        usage["latency_ms"],
        usage["elapsed_ms"],
        usage["attempts"],
        extra,
    )
    return usage


def get_owner(x_owner_id: str = Header(default="")) -> str:
    """匿名设备号：前端用 localStorage 生成 UUID 放在请求头里。

    没有账号体系，所以它只是"隔离命名空间"，不是身份认证——
    伪造它就能看到别人的记录。小项目 demo 接受这个边界，PRD 里如实写。
    """
    return (x_owner_id or "").strip()[:64] or "public"


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
    # 本地开发/静态预览的端口不固定（3000 next dev、4311/4321 静态预览），用正则统一放行
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


def _conn():
    return db.connect()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": settings.model, "rules": len(load_rules())}


@app.post("/api/generate", response_model=GenerateResponse)
def generate(
    req: GenerateRequest, llm: LLM = Depends(get_llm), owner: str = Depends(get_owner)
) -> GenerateResponse:
    started = time.time()
    product_id = f"p_{uuid.uuid4().hex[:10]}"
    rules = load_rules()
    # 生成只是第一步：自检、自动改写、复检都在这个请求里发生，token 必须一起算
    task_usage = {k: 0 for k in USAGE_KEYS}

    try:
        drafts = generate_drafts(req.brief, tone=req.tone, platform=req.platform, llm=llm)
    except LLMError as exc:
        raise HTTPException(status_code=504, detail=f"模型调用失败，请重试或转人工：{exc}") from exc
    for d in drafts:
        task_usage = merge_usage(task_usage, d.usage)

    # ADR-003：生成即自检，命中就自动改写，通过才作为成品返回
    for d in drafts:
        try:
            first = check_text(d.title, d.script, rules=rules, llm=llm)
            task_usage = merge_usage(task_usage, first.usage)
            fixed = len(first.violations)
            remaining = fixed
            if fixed:
                rw = rewrite_draft(d.title, d.hook, d.script, first, rules=rules, llm=llm)
                task_usage = merge_usage(task_usage, rw.usage)
                d.title, d.script = rw.title, rw.script
                remaining = len(rw.after_check.violations) if rw.after_check else fixed
            d.self_check = {
                "rules": len(rules),
                "fixed": fixed,
                "remaining": remaining,
                "passed": remaining == 0,
                "rounds": getattr(rw, "rounds", 0) if fixed else 0,
            }
        except LLMError as exc:  # 自检失败不能让整个生成挂掉
            d.self_check = {"rules": len(rules), "fixed": 0, "remaining": None, "passed": False, "error": str(exc)}

    with _conn() as conn:
        db.insert_product(conn, product_id, req.brief, req.tone)
        for d in drafts:
            db.insert_draft(
                conn,
                {
                    "id": d.id, "product_id": product_id, "angle": d.angle, "angle_name": d.angle_name,
                    "title": d.title, "hook": d.hook, "script": d.script,
                    "selling_points": d.selling_points, "disclosure": d.disclosure,
                    "owner_id": owner,
                },
            )

    usage = log_usage("/api/generate", task_usage, started, product_id=product_id, drafts=len(drafts))
    return GenerateResponse(
        product_id=product_id,
        drafts=[
            {
                "id": d.id, "angle": d.angle, "angle_name": d.angle_name,
                "title": d.title, "hook": d.hook, "script": d.script,
                "selling_points": d.selling_points, "disclosure": d.disclosure,
                "self_check": d.self_check,
            }
            for d in drafts
        ],
        elapsed_ms=usage["elapsed_ms"],
        tokens_in=usage["tokens_in"],
        tokens_out=usage["tokens_out"],
        usage=usage,
    )


def _numbered(violations) -> list:
    """给违规编号：左栏标记、中栏卡片、右栏改动共用同一个 n。"""
    return [{**v.to_dict(), "n": i} for i, v in enumerate(violations, start=1)]


def _resolve_and_check(req: CheckRequest, llm: LLM, owner: str):
    """解析目标（draft_id 或粘贴文本）→ 建/取草稿 → 检查 → 落库。

    返回 (draft_id, 检查用标题, 正文, 结果, 列表展示标题)。
    """
    title, content, draft_id = "", req.content or "", None
    display_title = ""

    if req.draft_id:
        with _conn() as conn:
            row = db.get_draft(conn, req.draft_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"草稿不存在：{req.draft_id}")
        if row["owner_id"] and row["owner_id"] != owner:
            # 不是自己的草稿：当成不存在，避免通过 id 探测别人
            raise HTTPException(status_code=404, detail=f"草稿不存在：{req.draft_id}")
        draft = db.draft_row_to_dict(row)
        title, content, draft_id = draft["title"], draft["script"], draft["id"]
        display_title = draft["title"]
        if draft.get("angle") == "paste":
            # 粘贴文案的"标题"就是正文第一行，再当标题传进去会把同一句话检查两遍
            title = ""
    else:
        # 粘贴检查：自动建一条 draft，后续 /api/rewrite 才有 id 可用
        lines = [ln.strip() for ln in req.content.splitlines() if ln.strip()]
        draft_title = lines[0][:60] if lines else "粘贴的文案"
        display_title = draft_title
        title = ""  # 检查/改写只用正文，避免"标题 = 第一行"重复
        draft_id = f"d_{uuid.uuid4().hex[:8]}"
        pid = f"p_{uuid.uuid4().hex[:8]}"
        with _conn() as conn:
            db.insert_product(conn, pid, "（粘贴检查）", "")
            db.insert_draft(
                conn,
                {
                    "id": draft_id, "product_id": pid, "angle": "paste", "angle_name": "粘贴",
                    "title": draft_title, "hook": "", "script": req.content,
                    "selling_points": [], "disclosure": "", "owner_id": owner,
                },
            )

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

    return draft_id, title, content, result, display_title


@app.post("/api/check", response_model=CheckResponse)
def check(
    req: CheckRequest, llm: LLM = Depends(get_llm), owner: str = Depends(get_owner)
) -> CheckResponse:
    started = time.time()
    draft_id, title, content, result, display_title = _resolve_and_check(req, llm, owner)

    payload = result.to_dict()
    payload["draft_id"] = draft_id
    payload["violations"] = _numbered(result.violations)
    payload["usage"] = log_usage("/api/check", result.usage, started, draft_id=draft_id or "-", owner=owner)
    resp = CheckResponse(**payload)

    with _conn() as conn:
        db.add_event(
            conn, owner, "check", draft_id, display_title,
            violation_count=len(result.violations), remaining_count=len(result.violations),
            payload=resp.model_dump(),
        )
    return resp


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(
    req: CheckRequest, llm: LLM = Depends(get_llm), owner: str = Depends(get_owner)
) -> AnalyzeResponse:
    """检查 → 改写 → 复检，一次算完再返回（ADR-009）。

    前端只呈现这一份结果，所以「检查出的条数」和「改写明细的条数」必然一致。
    """
    started = time.time()
    draft_id, title, content, result, display_title = _resolve_and_check(req, llm, owner)
    usage = dict(result.usage)
    rewrite_out: Optional[RewriteOut] = None
    rewrite_error: Optional[str] = None

    if result.violations:
        try:
            rw = rewrite_draft(title, "", content, result, llm=llm)
            usage = merge_usage(result.usage, rw.usage)
            rewrite_out = RewriteOut(
                title=rw.title,
                script=rw.script,
                changes=[ChangeOut(**c.to_dict()) for c in rw.changes],
                rounds=rw.rounds,
                remaining=rw.remaining,
                unresolved=rw.unresolved,
                before_violations=len(result.violations),
                after_violations=rw.remaining,
                violation_reduction=rw.violation_reduction,
            )
        except LLMError as exc:
            # 改写失败不能把检查结果一起丢掉：照常返回违规项，让前端提示重试
            rewrite_error = f"改写失败，可重试：{exc}"

    usage = log_usage(
        "/api/analyze",
        usage,
        started,
        draft_id=draft_id or "-",
        violations=len(result.violations),
        rewritten=int(rewrite_out is not None),
        owner=owner,
    )
    resp = AnalyzeResponse(
        draft_id=draft_id,
        title=title,
        script=content,
        violations=_numbered(result.violations),
        uncertain=_numbered(result.uncertain),
        suspected=[s.to_dict() for s in result.suspected],
        human_review=result.human_review,
        reason=result.reason,
        rewrite=rewrite_out,
        rewrite_error=rewrite_error,
        usage=usage,
    )

    # 查过就算一条历史：payload 存完整快照，点开就能恢复那次的任务
    with _conn() as conn:
        db.add_event(
            conn, owner, "check", draft_id, display_title,
            violation_count=len(result.violations), remaining_count=resp.rewrite.remaining if resp.rewrite else 0,
            payload=resp.model_dump(),
        )
    return resp



@app.post("/api/rewrite", response_model=RewriteResponse)
def rewrite(req: RewriteRequest, llm: LLM = Depends(get_llm)) -> RewriteResponse:
    started = time.time()
    with _conn() as conn:
        row = db.get_draft(conn, req.draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"草稿不存在：{req.draft_id}")

    draft = db.draft_row_to_dict(row)
    try:
        base_check = check_text(draft["title"], draft["script"], llm=llm)
        if not base_check.violations:
            log_usage("/api/rewrite", base_check.usage, started, draft_id=req.draft_id, outcome="409_no_violation")
            raise HTTPException(status_code=409, detail="该草稿没有可确证的违规，无需改写")
        result = rewrite_draft(draft["title"], draft.get("hook", ""), draft["script"], base_check, llm=llm)
    except LLMError as exc:
        raise HTTPException(status_code=504, detail=f"改写失败，请转人工：{exc}") from exc

    usage = log_usage(
        "/api/rewrite",
        merge_usage(base_check.usage, result.usage),
        started,
        draft_id=req.draft_id,
        rounds=result.rounds,
    )

    return RewriteResponse(
        draft_id=req.draft_id,
        title=result.title,
        script=result.script,
        changes=[c.to_dict() for c in result.changes],
        before_violations=len(base_check.violations),
        after_violations=len(result.after_check.violations) if result.after_check else 0,
        violation_reduction=result.violation_reduction,
        rounds=result.rounds,
        usage=usage,
    )


@app.post("/api/confirm", response_model=ConfirmResponse)
def confirm(req: ConfirmRequest, owner: str = Depends(get_owner)) -> ConfirmResponse:
    with _conn() as conn:
        row = db.get_draft(conn, req.draft_id)
        if row is None or (row["owner_id"] and row["owner_id"] != owner):
            raise HTTPException(status_code=404, detail=f"草稿不存在：{req.draft_id}")
        saved = db.upsert_confirmation(conn, req.draft_id, req.final_content, req.reviewer)
        db.mark_confirmed(conn, owner, req.draft_id)
    return ConfirmResponse(ok=True, **saved)


@app.get("/api/history", response_model=HistoryResponse)
def history(
    limit: int = Query(default=20, ge=1, le=100), owner: str = Depends(get_owner)
) -> HistoryResponse:
    """查过就算：不只是"已确认"的那些，按设备隔离。"""
    with _conn() as conn:
        rows = db.list_events(conn, owner, limit=limit)
    return HistoryResponse(items=[dict(r) for r in rows])


@app.get("/api/events/{event_id}", response_model=EventDetailResponse)
def event_detail(event_id: int, owner: str = Depends(get_owner)) -> EventDetailResponse:
    """点开一条历史，把当次的分析快照还回去。别人的记录一律 404。"""
    with _conn() as conn:
        row = db.get_event(conn, event_id, owner)
    if row is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    payload = json.loads(row["payload"]) if row["payload"] else {}
    return EventDetailResponse(
        id=row["id"],
        created_at=row["created_at"],
        status=row["status"],
        draft_id=row["draft_id"],
        title=row["title"],
        result=payload,
    )


@app.get("/api/rules", response_model=RulesResponse)
def rules(category: Optional[str] = Query(default=None)) -> RulesResponse:
    if category and category not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category 只能是 {sorted(ALLOWED_CATEGORIES)}")
    with _conn() as conn:
        rows = db.list_rules(conn, category=category)
    items = [RuleOut(**dict(r)) for r in rows]
    return RulesResponse(total=len(items), items=items)
