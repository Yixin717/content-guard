"""不依赖网络的单元测试：JSON 兜底解析、规则加载与检索、幻觉 rule_id 过滤。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.check import CheckPayload, SuspectedPayload, ViolationPayload, check_text
from app.llm import _extract_json
from app.rules import load_rules, retrieve


def test_extract_json_handles_markdown_fence():
    raw = '好的，结果如下：\n```json\n{"a": 1}\n```\n希望有帮助'
    assert _extract_json(raw) == '{"a": 1}'


def test_extract_json_returns_none_when_no_object():
    assert _extract_json("模型开始胡说") is None


def test_rules_load_and_categories():
    rules = load_rules()
    assert len(rules) >= 30
    assert {r.category for r in rules} == {"absolute", "false_claim", "platform"}
    assert all(r.id and r.source for r in rules)


def test_retrieve_prefers_related_rule():
    rules = load_rules()
    top = retrieve(rules, "全网最低价 三天根治痘痘 加V", top_k=6)
    ids = {r.id for r in top}
    assert "ABS-004" in ids or "ABS-001" in ids
    assert "FLM-001" in ids or "FLM-002" in ids


class _FakeLLM:
    """模拟模型编造 rule_id 的情况，验证幻觉过滤。"""

    def chat_json(self, system, user, schema, max_retries=2):
        payload = CheckPayload(
            violations=[
                ViolationPayload(
                    rule_id="ABS-001", quote="国家级品质", severity="high", suggestion="删掉", confidence=0.9
                ),
                ViolationPayload(
                    rule_id="NOT-REAL-999", quote="随便", severity="high", suggestion="", confidence=0.9
                ),
            ],
            human_review=False,
        )
        return payload, {"tokens_in": 0, "tokens_out": 0, "latency_ms": 0, "attempts": 1}


def test_checker_drops_hallucinated_rule_ids():
    rules = load_rules()
    result = check_text("国家级品质", "国家级品质，闭眼入", rules=rules, llm=_FakeLLM())
    assert [v.rule_id for v in result.violations] == ["ABS-001"]
    assert result.dropped_unknown_rule_ids == ["NOT-REAL-999"]


class _SuspectedLLM:
    """模拟「有问题但无条款可依」的情况，验证 suspected 通道与引用校验。"""

    def chat_json(self, system, user, schema, max_retries=2):
        payload = CheckPayload(
            violations=[],
            suspected=[
                SuspectedPayload(quote="不买你就等着后悔", reason="情绪施压式促销，规则库未覆盖", severity="medium"),
                SuspectedPayload(quote="草稿里根本没有这句", reason="模型瞎编的引用", severity="high"),
            ],
            human_review=False,
        )
        return payload, {"tokens_in": 0, "tokens_out": 0, "latency_ms": 0, "attempts": 1}


def test_suspected_channel_and_quote_guard():
    rules = load_rules()
    result = check_text("", "不买你就等着后悔，这价格真的划算", rules=rules, llm=_SuspectedLLM())
    assert [s.quote for s in result.suspected] == ["不买你就等着后悔"]
    assert result.suspected[0].reason.startswith("情绪施压")
    assert result.dropped_quotes == ["草稿里根本没有这句"]
    assert result.human_review is True


def test_sentence_diff_detects_replacement():
    from app.rewrite import sentence_diff, split_clauses

    before = "全网最低价！三天根治痘痘。这条裤子很好看。"
    after = "这条裤子性价比很高。痘痘肌用着有改善。这条裤子很好看。"
    changes = sentence_diff(before, after)
    kinds = {c["type"] for c in changes}
    assert "replace" in kinds
    assert any("全网最低" in c["before"] for c in changes)
    assert all(c["before"] or c["after"] for c in changes)
    assert split_clauses(before)[-1] == "这条裤子很好看。"
