"""API 测试：不触网，LLM 用 dependency_overrides 替换。"""

import pytest
from fastapi.testclient import TestClient

from app.api import app, get_llm
from app.check import CheckPayload, ViolationPayload
from app.config import settings
from app.generate import DraftPayload
from app.rewrite import ReplacementPayload, RewritePayload


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
            # 只回答「这一处换成什么」，不再重写整篇
            return RewritePayload(
                replacements=[ReplacementPayload(rule_id="ABS-004", before="69 两条", after="两条 69")],
            ), usage
        raise AssertionError(f"未预期的 schema: {schema}")


class UnfixableLLM(FakeLLM):
    """模型承认改不了（after 为空）——系统必须标「需人工」，不能编一条改动。"""

    def chat_json(self, system, user, schema, max_retries=2):
        if schema is RewritePayload:
            usage = {"tokens_in": 10, "tokens_out": 20, "latency_ms": 5, "attempts": 1}
            return RewritePayload(
                replacements=[ReplacementPayload(rule_id="ABS-004", before="69 两条", after="")],
            ), usage
        return super().chat_json(system, user, schema, max_retries)


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


# ---- /api/analyze：检查与改动必须数量一致（ADR-009）----


def test_check_returns_clause_text(client):
    """中栏「条款原文」不能是空的：clause 必须来自 rules.csv 的原文。"""
    body = client.post("/api/check", json={"content": "全网最低价，69 两条"}).json()
    v = body["violations"][0]
    assert v["n"] == 1
    assert v["clause"], "条款原文不能为空"
    from app.rules import load_rules

    rule = {r.id: r for r in load_rules()}["ABS-004"]
    assert v["clause"] == rule.quote
    assert v["source_url"] == rule.source_url


def test_analyze_change_count_equals_violation_count(client):
    body = client.post("/api/analyze", json={"content": "全网最低价，69 两条"}).json()
    violations = body["violations"]
    changes = body["rewrite"]["changes"]
    assert len(violations) == len(changes) == 1
    # 编号共用：左栏 ① = 中栏 ① = 右栏 ①
    assert [v["n"] for v in violations] == [c["n"] for c in changes]
    assert changes[0]["rule_id"] == violations[0]["rule_id"]
    assert changes[0]["status"] == "fixed"
    assert changes[0]["after"] == "两条 69"
    # 服务端给出高亮位置，前端不用 indexOf
    start, end = changes[0]["start"], changes[0]["end"]
    assert body["rewrite"]["script"][start:end] == "两条 69"
    assert body["rewrite"]["remaining"] == 0


def test_analyze_marks_unfixable_without_inventing_change(client):
    app.dependency_overrides[get_llm] = lambda: UnfixableLLM()
    body = client.post("/api/analyze", json={"content": "全网最低价，69 两条"}).json()
    changes = body["rewrite"]["changes"]
    assert len(changes) == len(body["violations"]) == 1
    assert changes[0]["status"] == "unresolved"
    assert changes[0]["after"] == ""
    assert changes[0]["start"] == -1
    assert "需人工" in changes[0]["reason"]
    # 不再拿"改写后的复检"当结论：改写没改好就逐条标出来，其余不猜
    assert body["rewrite"]["remaining"] == 0


def test_analyze_usage_covers_both_checks_and_rewrite(client):
    body = client.post("/api/analyze", json={"content": "全网最低价，69 两条"}).json()
    # 独立检查 2 次（取并集）+ 改写 1 次
    assert body["usage"]["attempts"] == 3
    assert body["usage"]["tokens_in"] == 30


class ReverseOrderLLM(FakeLLM):
    """故意先返回后面的问题，验证系统会按原文顺序重排。"""

    def chat_json(self, system, user, schema, max_retries=2):
        if schema is CheckPayload:
            usage = {"tokens_in": 10, "tokens_out": 20, "latency_ms": 5, "attempts": 1}
            return CheckPayload(
                violations=[
                    ViolationPayload(rule_id="ABS-001", quote="国家级品质", severity="high", confidence=0.9),
                    ViolationPayload(rule_id="ABS-004", quote="全网最低价", severity="high", confidence=0.9),
                ],
                suspected=[],
                human_review=False,
            ), usage
        return super().chat_json(system, user, schema, max_retries)


def test_violations_sorted_by_position_in_text(client):
    app.dependency_overrides[get_llm] = lambda: ReverseOrderLLM()
    body = client.post("/api/analyze", json={"content": "全网最低价，国家级品质，69 两条"}).json()
    assert [v["rule_id"] for v in body["violations"]] == ["ABS-004", "ABS-001"]
    assert [v["n"] for v in body["violations"]] == [1, 2]
    # 改动顺序也跟着原文顺序，编号一一对应
    assert [c["n"] for c in body["rewrite"]["changes"]] == [1, 2]


# ---- 历史与匿名设备号（方案 C：事件表 + 按设备隔离）----


def _hdr(owner):
    return {"X-Owner-Id": owner}


def test_history_is_per_device(client):
    client.post("/api/analyze", json={"content": "全网最低价，69 两条"}, headers=_hdr("device-A"))
    a = client.get("/api/history", headers=_hdr("device-A")).json()["items"]
    b = client.get("/api/history", headers=_hdr("device-B")).json()["items"]
    assert len(a) == 1
    assert a[0]["violation_count"] == 1
    assert a[0]["title"], "列表要有标题（或首句）"
    assert b == [], "别人不能看到我的记录"


def test_history_counts_every_check_not_only_confirmed(client):
    for _ in range(2):
        client.post("/api/analyze", json={"content": "全网最低价，69 两条"}, headers=_hdr("A"))
    items = client.get("/api/history", headers=_hdr("A")).json()["items"]
    assert len(items) == 2, "查过就算，同一条文案查两次就是两条"
    assert all(it["status"] == "checked" for it in items)


def test_event_detail_restores_snapshot_and_is_private(client):
    client.post("/api/analyze", json={"content": "全网最低价，69 两条"}, headers=_hdr("A"))
    ev = client.get("/api/history", headers=_hdr("A")).json()["items"][0]
    ok = client.get(f"/api/events/{ev['id']}", headers=_hdr("A"))
    assert ok.status_code == 200
    result = ok.json()["result"]
    assert result["script"] and result["rewrite"]["changes"] and result["violations"]
    assert client.get(f"/api/events/{ev['id']}", headers=_hdr("B")).status_code == 404


def test_confirm_is_owner_scoped_and_marks_history(client):
    body = client.post("/api/analyze", json={"content": "全网最低价，69 两条"}, headers=_hdr("A")).json()
    assert client.post(
        "/api/confirm", json={"draft_id": body["draft_id"], "final_content": "定稿"}, headers=_hdr("B")
    ).status_code == 404
    assert client.post(
        "/api/confirm", json={"draft_id": body["draft_id"], "final_content": "定稿"}, headers=_hdr("A")
    ).status_code == 200
    items = client.get("/api/history", headers=_hdr("A")).json()["items"]
    assert items[0]["status"] == "confirmed"


def test_cannot_check_other_devices_draft(client):
    body = client.post("/api/analyze", json={"content": "全网最低价，69 两条"}, headers=_hdr("A")).json()
    resp = client.post("/api/analyze", json={"draft_id": body["draft_id"]}, headers=_hdr("B"))
    assert resp.status_code == 404


class SecondOpinionLLM(FakeLLM):
    """两次检查结论不同：第二次补上了第一次漏掉的一条。"""

    def __init__(self):
        self.calls = 0

    def chat_json(self, system, user, schema, max_retries=2):
        if schema is CheckPayload:
            self.calls += 1
            usage = {"tokens_in": 10, "tokens_out": 20, "latency_ms": 5, "attempts": 1}
            if self.calls == 1:
                first = ViolationPayload(rule_id="ABS-004", quote="全网最低价", severity="high", confidence=0.9)
                return CheckPayload(violations=[first], suspected=[], human_review=False), usage
            return CheckPayload(
                violations=[
                    ViolationPayload(rule_id="ABS-004", quote="全网最低价", severity="high", confidence=0.9),
                    ViolationPayload(rule_id="ABS-001", quote="国家级品质", severity="medium", confidence=0.9),
                ],
                suspected=[], human_review=False,
            ), usage
        return super().chat_json(system, user, schema, max_retries)


def test_analyze_merges_two_checks_and_dedupes(client):
    llm = SecondOpinionLLM()
    app.dependency_overrides[get_llm] = lambda: llm
    body = client.post("/api/analyze", json={"content": "全网最低价，国家级品质，69 两条"}).json()
    # 两次检查取并集：第一次 1 条、第二次 2 条（含重复），最终 2 条，按原文顺序
    assert [v["rule_id"] for v in body["violations"]] == ["ABS-004", "ABS-001"]
    assert [v["n"] for v in body["violations"]] == [1, 2]
    assert len(body["rewrite"]["changes"]) == 2
    # 两条都来自用户原文，都能标位置、带法条
    assert all(v["clause"] for v in body["violations"])
    assert all(v["quote"] in body["script"] for v in body["violations"])
