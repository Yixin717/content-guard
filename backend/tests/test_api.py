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


def test_generate_check_confirm_flow_is_idempotent(client):
    gen = client.post("/api/generate", json={"brief": "杭州女装，冰丝阔腿裤，69 元两条"})
    assert gen.status_code == 200
    draft_id = gen.json()["drafts"][0]["id"]

    chk = client.post("/api/check", json={"draft_id": draft_id})
    assert chk.status_code == 200
    assert len(chk.json()["violations"]) == 1

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
