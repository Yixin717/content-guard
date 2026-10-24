"""CLI：brief → 3 版草稿 → 合规检查 →（可选）改写复检。

用法：
    python -m app.cli "杭州女装，冰丝阔腿裤，69 元两条"
    python -m app.cli "..." --rewrite              # 有违规时自动改写并复检
    python -m app.cli --check "某段文案"            # 只检查
    python -m app.cli --check "某段文案" --rewrite  # 检查 + 改写
    python -m app.cli "..." --json                 # 只输出 JSON
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from .check import CheckResult, check_text
from .config import settings
from .generate import generate_drafts
from .llm import LLM, LLMError
from .rewrite import RewriteResult, rewrite_draft
from .rules import load_rules

SEVERITY_LABEL = {"high": "高", "medium": "中", "low": "低"}


def _rule(s: str = "") -> None:
    print(s)


def _print_check(result: CheckResult, prefix: str = "") -> None:
    if result.violations:
        print(f"{prefix}违规 {len(result.violations)} 条：")
        for v in result.violations:
            print(f"  [{SEVERITY_LABEL.get(v.severity, v.severity)}] {v.rule_id} {v.rule_title}")
            print(f"{prefix}     原文：{v.quote}")
            print(f"{prefix}     依据：{v.source}｜置信度 {v.confidence:.2f}")
            print(f"{prefix}     改写：{v.suggestion}")
    else:
        print(f"{prefix}违规 0 条")
    for v in result.uncertain:
        print(f"{prefix}  [?] 待确认 {v.rule_id} {v.rule_title}｜置信度 {v.confidence:.2f}｜原文：{v.quote}")
    for s in result.suspected:
        print(f"{prefix}  [!] 疑似问题（无对应条款）：{s.quote}｜{s.reason}")
    if result.dropped_quotes:
        print(f"{prefix}（丢弃无法逐字匹配的引用：{'；'.join(result.dropped_quotes[:3])}）")
    if result.human_review:
        print(f"{prefix}⚠ 需人工复核：{result.reason}")


def _print_rewrite(rw: RewriteResult) -> None:
    _rule("─" * 68)
    before = len(rw.before_check.violations)
    after = len(rw.after_check.violations) if rw.after_check else None
    if after is None:
        print(f"改写：{before} 条违规 → 未复检")
    else:
        rate = rw.violation_reduction
        pct = f"{rate * 100:.0f}%" if rate is not None else "—"
        print(f"改写：{before} 条违规 → {after} 条（下降 {pct}，共 {rw.rounds} 轮）")

    if rw.changes:
        print("改动明细：")
        for c in rw.changes:
            ids = "、".join(c.rule_ids) if c.rule_ids else "—"
            print(f"  • [{ids}] {c.reason}")
            print(f"      改前：{c.before}")
            print(f"      改后：{c.after}")

    print("\n改写后全文：")
    if rw.title:
        print(f"《{rw.title}》")
    if rw.hook:
        print(rw.hook)
    print(rw.script)
    if rw.selling_points:
        print(f"\n卖点：{' / '.join(rw.selling_points)}")

    if rw.after_check and rw.after_check.violations:
        print("\n复检仍存在的违规：")
        _print_check(rw.after_check, prefix="  ")


def run_check(text: str, do_rewrite: bool) -> int:
    rules = load_rules()
    llm = LLM()
    check = check_text("", text, rules=rules, llm=llm)

    print(f"规则库：{len(rules)} 条｜命中 {len(check.violations)} 条")
    _print_check(check)

    if do_rewrite and check.violations:
        rw = rewrite_draft("", "", text, check, rules=rules, llm=llm)
        _print_rewrite(rw)
    elif do_rewrite:
        print("无违规，跳过改写")
    return 0


def run(brief: str, tone: str, as_json: bool, do_check: bool, do_rewrite: bool) -> int:
    started = time.time()
    rules = load_rules()
    llm = LLM()

    if not as_json:
        print(f"规则库：{len(rules)} 条")
        print(f"商品简报：{brief}\n")

    drafts = generate_drafts(brief, tone=tone, llm=llm)
    items = []
    for d in drafts:
        check = check_text(d.title, d.script, rules=rules, llm=llm) if do_check else None
        rw = None
        if do_rewrite and check and check.violations:
            rw = rewrite_draft(d.title, d.hook, d.script, check, rules=rules, llm=llm)
        items.append({"draft": d, "check": check, "rewrite": rw})

    payload = {
        "brief": brief,
        "tone": tone,
        "elapsed_ms": int((time.time() - started) * 1000),
        "drafts": [
            {
                "id": it["draft"].id,
                "angle": it["draft"].angle,
                "angle_name": it["draft"].angle_name,
                "title": it["draft"].title,
                "hook": it["draft"].hook,
                "script": it["draft"].script,
                "selling_points": it["draft"].selling_points,
                "disclosure": it["draft"].disclosure,
                "check": it["check"].to_dict() if it["check"] else None,
                "rewrite": it["rewrite"].to_dict() if it["rewrite"] else None,
                "usage": it["draft"].usage,
            }
            for it in items
        ],
    }

    settings.out_dir.mkdir(exist_ok=True)
    out_path = settings.out_dir / f"run-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    for i, it in enumerate(items, 1):
        d, c = it["draft"], it["check"]
        _rule("═" * 68)
        print(f"【{i}/{len(items)}】{d.angle_name}｜{d.title}")
        _rule("─" * 68)
        if d.hook and not d.script.startswith(d.hook):
            print(f"开场：{d.hook}\n")
        print(d.script)
        print(f"\n卖点：{' / '.join(d.selling_points)}")
        print(f"AI 声明：{d.disclosure}")
        if c is not None:
            _rule("─" * 68)
            _print_check(c)
        if it["rewrite"]:
            _print_rewrite(it["rewrite"])

    total_in = total_out = 0
    for it in items:
        total_in += it["draft"].usage.get("tokens_in", 0)
        total_out += it["draft"].usage.get("tokens_out", 0)
        for key in ("check", "rewrite"):
            obj = it[key]
            if obj:
                total_in += obj.usage.get("tokens_in", 0)
                total_out += obj.usage.get("tokens_out", 0)

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
    parser.add_argument("--rewrite", action="store_true", help="有违规时自动改写并复检")
    parser.add_argument("--tone", default="亲切、像朋友聊天", help="语气")
    parser.add_argument("--json", action="store_true", dest="as_json", help="只输出 JSON")
    parser.add_argument("--no-check", action="store_true", help="跳过合规检查")
    args = parser.parse_args(argv)

    try:
        if args.check:
            return run_check(args.check, args.rewrite)
        if not args.brief:
            parser.error("需要提供 brief，或用 --check 传入待检查文案")
        return run(args.brief, args.tone, args.as_json, not args.no_check, args.rewrite)
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
