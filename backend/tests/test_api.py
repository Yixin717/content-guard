"""API 测试：不触网，LLM 用 dependency_overrides 替换。"""

import pytest
from fastapi.testclient import TestClient

from app.api import app, get_llm
from app.check import CheckPayload, ViolationPayload
from app.config import settings
from app.generate import DraftPayload
from app.rewrite import RewritePayload


class FakeLLM:
    """按 schema 返回固定结构，模拟模型输出。"""

    def chat_json(self, system, user, schema, max_retries=2):
        usage = {"tokens_in": 10, "tokens_out": 20, "latency_ms": 5, "attempts": 1}
        if schema is DraftPayload:
            return DraftPayload(
                title="胯宽姐妹看这条",
                hook="坐下不卡裆",
                script="我胯宽，穿这条坐下不卡裆，69 两条。",
                selling_points=["遮胯", "69 两条"],
            ), usage
        if schema is CheckPayload:
            return CheckPayload(
                violations=[
                    ViolationPayload(
                        rule_id="ABS-004", quote="69 两条", severity="high", suggestion="去掉绝对化", confidence=0.9
                    )
                ],
                suspected=[],
                human_review=False,
            ), usage
        if schema is RewritePayload:
            return RewritePayload(
                title="胯宽姐妹看这条",
                hook="坐下不卡裆",
                script="我胯宽，穿这条坐下不卡裆，两条 69。",
                selling_points=["遮胯"],
                changes=[],
            ), usage
        raise AssertionError(f"未预期的 schema: {schema}")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "test.db")
    app.dependency_overrides[get_llm] = lambda: FakeLLM()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_generate_requires_brief(client):
    assert client.post("/api/generate", json={}).status_code == 422
    assert client.post("/api/generate", json={"brief": "短"}).status_code == 422


def test_check_requires_content_or_draft(client):
    assert client.post("/api/check", json={}).status_code == 422
    assert client.post("/api/check", json={"content": "   "}).status_code == 422


def test_rules_filter_by_category(client):
    resp = client.get("/api/rules", params={"category": "absolute"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] > 0
    assert {r["category"] for r in body["items"]} == {"absolute"}
    assert client.get("/api/rules", params={"category": "bogus"}).status_code == 422


def test_generate_is_self_checked(client):
    gen = client.post("/api/generate", json={"brief": "杭州女装，冰丝阔腿裤，69 元两条"})
    assert gen.status_code == 200
    drafts = gen.json()["drafts"]
    assert len(drafts) == 3
    # ADR-003：返回的每一版都带自检结果
    assert all(d["self_check"] is not None for d in drafts)
    assert all(d["self_check"]["rules"] > 0 for d in drafts)


def test_check_with_pasted_content_creates_draft(client):
    chk = client.post("/api/check", json={"content": "全网最低价，三天根治痘痘"})
    assert chk.status_code == 200
    assert chk.json()["draft_id"], "粘贴检查必须返回 draft_id，否则无法继续改写"
    # 有了 draft_id，改写接口才可用
    rw = client.post("/api/rewrite", json={"draft_id": chk.json()["draft_id"]})
    assert rw.status_code in (200, 409)


def test_generate_check_confirm_flow_is_idempotent(client):
    gen = client.post("/api/generate", json={"brief": "杭州女装，冰丝阔腿裤，69 元两条"})
    assert gen.status_code == 200
    draft_id = gen.json()["drafts"][0]["id"]

    chk = client.post("/api/check", json={"draft_id": draft_id})
    assert chk.status_code == 200
    assert "violations" in chk.json()

    first = client.post("/api/confirm", json={"draft_id": draft_id, "final_content": "定稿"})
    second = client.post("/api/confirm", json={"draft_id": draft_id, "final_content": "定稿"})
    assert first.status_code == second.status_code == 200
    assert first.json()["idempotent"] is False
    assert second.json()["idempotent"] is True
    assert first.json()["audit_id"] == second.json()["audit_id"]

    hist = client.get("/api/history").json()["items"]
    assert len(hist) == 1
    assert hist[0]["draft_id"] == draft_id


def test_unknown_draft_returns_404(client):
    assert client.post("/api/check", json={"draft_id": "p_nope"}).status_code == 404
    assert client.post("/api/confirm", json={"draft_id": "p_nope", "final_content": "x"}).status_code == 404


# ---- 用量（B-008：页面上不许有假数字，接口必须给真数字）----
# FakeLLM 每次调用固定 tokens_in=10 / tokens_out=20 / latency_ms=5 / attempts=1


def test_check_returns_real_usage(client):
    body = client.post("/api/check", json={"content": "全网最低价，三天根治痘痘"}).json()
    usage = body["usage"]
    assert usage["tokens_in"] == 10
    assert usage["tokens_out"] == 20
    assert usage["latency_ms"] == 5
    assert usage["attempts"] == 1
    assert usage["elapsed_ms"] >= 0


def test_rewrite_usage_counts_precheck_and_recheck(client):
    # FakeLLM 的违规引用固定是「69 两条」，原文里得有这段，否则会被当成"引用不实"丢弃 → 409
    draft_id = client.post("/api/check", json={"content": "全网最低价，69 两条"}).json()["draft_id"]
    body = client.post("/api/rewrite", json={"draft_id": draft_id}).json()
    # 前置检查 1 次 + 改写 1 次 + 复检 1 次 = 3 次调用，少算任何一次都是在骗人
    assert body["usage"]["tokens_in"] == 30
    assert body["usage"]["attempts"] == 3


def test_generate_usage_includes_self_check(client):
    body = client.post("/api/generate", json={"brief": "杭州女装，冰丝阔腿裤，69 元两条"}).json()
    # 3 版 × (写作 1 + 自检 1 + 改写 1 + 复检 1) = 12 次调用
    assert body["usage"]["tokens_in"] == 120
    assert body["usage"]["attempts"] == 12
    # 老字段保持兼容，且与新字段一致
    assert body["tokens_in"] == body["usage"]["tokens_in"]
    assert body["elapsed_ms"] == body["usage"]["elapsed_ms"]


def test_usage_is_logged_for_journalctl(client, caplog):
    from app.api import usage_logger

    usage_logger.addHandler(caplog.handler)
    try:
        client.post("/api/check", json={"content": "全网最低价"})
    finally:
        usage_logger.removeHandler(caplog.handler)

    lines = [r.getMessage() for r in caplog.records if r.name == "content_guard.usage"]
    assert any("llm_usage path=/api/check" in ln and "tokens_in=10" in ln for ln in lines), lines
