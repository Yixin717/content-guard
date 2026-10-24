"""CLI：brief → 3 版草稿 → 合规检查 → 打印 / 落盘。

用法：
    python -m app.cli "杭州女装，冰丝阔腿裤，遮胯显瘦，69 元两件"
    python -m app.cli "..." --json          # 只输出 JSON，方便喂给评测
    python -m app.cli "..." --no-check      # 只看生成
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from .check import check_text
from .config import settings
from .generate import generate_drafts
from .llm import LLM, LLMError
from .rules import load_rules

SEVERITY_LABEL = {"high": "高", "medium": "中", "low": "低"}


def _rule(s: str = "") -> None:
    print(s)


def run_check(text: str) -> int:
    """只检查一段现成文案，用于回归和演示。"""
    rules = load_rules()
    result = check_text("", text, rules=rules)
    print(f"规则库：{len(rules)} 条｜命中 {len(result.violations)} 条")
    for v in result.violations:
        print(f"  [{SEVERITY_LABEL.get(v.severity, v.severity)}] {v.rule_id} {v.rule_title}")
        print(f"       原文：{v.quote}")
        print(f"       依据：{v.source}｜置信度 {v.confidence:.2f}")
        print(f"       改写：{v.suggestion}")
    for v in result.uncertain:
        print(f"  [?] {v.rule_id} {v.rule_title}｜置信度 {v.confidence:.2f}（待确认，未计入违规）")
        print(f"       原文：{v.quote}")
    if result.dropped_quotes:
        print(f"（丢弃无法逐字匹配的引用：{'；'.join(result.dropped_quotes[:3])}）")
    if result.human_review:
        print(f"⚠ 需人工复核：{result.reason}")
    return 0


def run(brief: str, tone: str, as_json: bool, do_check: bool) -> int:
    started = time.time()
    rules = load_rules()
    llm = LLM()

    if not as_json:
        print(f"规则库：{len(rules)} 条")
        print(f"商品简报：{brief}\n")

    drafts = generate_drafts(brief, tone=tone, llm=llm)

    results = []
    for d in drafts:
        check = check_text(d.title, d.script, rules=rules, llm=llm) if do_check else None
        results.append({"draft": d, "check": check})

    payload = {
        "brief": brief,
        "tone": tone,
        "elapsed_ms": int((time.time() - started) * 1000),
        "drafts": [
            {
                "id": d.id,
                "angle": d.angle,
                "angle_name": d.angle_name,
                "title": d.title,
                "hook": d.hook,
                "script": d.script,
                "selling_points": d.selling_points,
                "disclosure": d.disclosure,
                "check": (c.to_dict() if c else None),
                "usage": d.usage,
            }
            for d, c in ((r["draft"], r["check"]) for r in results)
        ],
    }

    settings.out_dir.mkdir(exist_ok=True)
    out_path = settings.out_dir / f"run-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    for i, (d, c) in enumerate(((r["draft"], r["check"]) for r in results), 1):
        _rule("═" * 68)
        print(f"【{i}/{len(results)}】{d.angle_name}｜{d.title}")
        _rule("─" * 68)
        if d.hook and not d.script.startswith(d.hook):
            print(f"开场：{d.hook}\n")
        print(d.script)
        print(f"\n卖点：{' / '.join(d.selling_points)}")
        print(f"AI 声明：{d.disclosure}")
        _rule("─" * 68)
        if c is None:
            print("检查：已跳过")
            continue
        if c.violations:
            print(f"违规 {len(c.violations)} 条：")
            for v in c.violations:
                print(f"  [{SEVERITY_LABEL.get(v.severity, v.severity)}] {v.rule_id} {v.rule_title}")
                print(f"       原文：{v.quote}")
                print(f"       依据：{v.source}｜置信度 {v.confidence:.2f}")
                print(f"       改写：{v.suggestion}")
        else:
            print("违规 0 条")
        for v in c.uncertain:
            print(f"  [?] 待确认 {v.rule_id} {v.rule_title}｜置信度 {v.confidence:.2f}｜原文：{v.quote}")
        if c.human_review:
            print(f"⚠ 需人工复核：{c.reason}")
        if c.dropped_unknown_rule_ids:
            print(f"（丢弃模型编造的 rule_id：{', '.join(c.dropped_unknown_rule_ids)}）")

    total_in = total_out = 0
    for r in results:
        total_in += r["draft"].usage.get("tokens_in", 0)
        total_out += r["draft"].usage.get("tokens_out", 0)
        if r["check"]:
            total_in += r["check"].usage.get("tokens_in", 0)
            total_out += r["check"].usage.get("tokens_out", 0)
    _rule("═" * 68)
    print(
        f"耗时 {payload['elapsed_ms'] / 1000:.1f}s｜"
        f"tokens in {total_in} / out {total_out}｜"
        f"结果已存 {out_path.relative_to(settings.out_dir.parent)}"
    )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Content Guard CLI")
    parser.add_argument("brief", nargs="?", help="商品简报，一句话即可")
    parser.add_argument("--check", metavar="TEXT", help="只检查这段文案（不生成）")
    parser.add_argument("--tone", default="亲切、像朋友聊天", help="语气")
    parser.add_argument("--json", action="store_true", dest="as_json", help="只输出 JSON")
    parser.add_argument("--no-check", action="store_true", help="跳过合规检查")
    args = parser.parse_args(argv)

    try:
        if args.check:
            return run_check(args.check)
        if not args.brief:
            parser.error("需要提供 brief，或用 --check 传入待检查文案")
        return run(args.brief, args.tone, args.as_json, not args.no_check)
    except LLMError as exc:
        print(f"❌ 模型调用失败：{exc}", file=sys.stderr)
        if exc.raw:
            print(f"原始返回（前 300 字）：{exc.raw[:300]}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
