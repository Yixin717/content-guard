"""不依赖网络的单元测试：JSON 兜底解析、规则加载与检索、幻觉 rule_id 过滤。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.check import CheckPayload, ViolationPayload, check_text
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
