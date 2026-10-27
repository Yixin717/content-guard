#!/usr/bin/env python3
"""把样本里的「预标注」渲染成一张逐条勾选表，供作者确认。

用法：
    python3 eval/label_sheet.py                 # 生成 eval/label-sheet.md（全部样本）
    python3 eval/label_sheet.py --ids 001-zara-jacket
    python3 eval/label_sheet.py --out /tmp/label.md

填写约定（在「你的判断」列里写一个）：
    同意                  → 进 gold
    不同意：一句话理由      → 我改判或删掉，并记下理由
    拿不准                → 进 edge 层，不参与主指标

只有双方一致的才进 gold。这不是形式主义：面试官问「gold 谁定的」，
答案是「按条款原文预标注 + 作者逐条确认，不一致的单独归因」，而不是「我觉得」。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "data" / "eval_cases"
sys.path.insert(0, str(ROOT / "backend"))

from app.rules import load_rules


def esc(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", "<br>").strip()


def render_case(case: dict, rules_by_id: dict) -> list[str]:
    out: list[str] = []
    out.append(f"## {case['id']}")
    out.append("")
    meta = []
    if case.get("source"):
        meta.append(f"来源：{case['source']}")
    if case.get("scene"):
        meta.append(f"场景：{case['scene']}")
    if case.get("notes"):
        meta.append(f"备注：{case['notes']}")
    if meta:
        out.append("- " + "；".join(meta))
        out.append("")

    out.append("**正文**")
    out.append("")
    for line in (case.get("draft") or "").splitlines() or [""]:
        out.append(f"> {line}" if line else ">")
    out.append("")

    proposed = case.get("proposed") or []
    if proposed:
        out.append("**预标注（请逐条判断）**")
        out.append("")
        out.append("| # | 原句 | 预标规则 | 条款原文 | 为什么这么判 | 你的判断 |")
        out.append("|---|---|---|---|---|---|")
        for i, p in enumerate(proposed, 1):
            rule = rules_by_id.get(p.get("rule_id", ""))
            clause = esc(rule.quote) if rule else "⚠️ 规则不存在"
            review = p.get("review", "") or ""
            basis = p.get('basis', '')
            if p.get('author_note'):
                basis += f"（作者：{p['author_note']}）"
            out.append(
                f"| {i} | {esc(p.get('quote'))} | `{p.get('rule_id')}` "
                f"{esc(rule.title) if rule else ''} | {clause} | {esc(basis)} | {review} |"
            )
        out.append("")
    else:
        out.append("**预标注**：无（本条没有明确违规；边界项与反例见下）")
        out.append("")

    negatives = case.get("negatives") or []
    if negatives:
        out.append("**明确不该报（模型若报了就是误报）** —— 空白 = 同意，不同意才写一句")
        out.append("")
        out.append("| 原句 | 为什么不该报 | 不同意才写 |")
        out.append("|---|---|---|")
        for n in negatives:
            out.append(f"| {esc(n.get('quote'))} | {esc(n.get('why'))} | {n.get('review', '')} |")
        out.append("")

    edge_items = case.get("edge_items") or []
    if edge_items:
        out.append("**边界项（不用勾，仅供你确认方向）**")
        out.append("")
        out.append("| 原句 | 为什么放边界 |")
        out.append("|---|---|")
        for e in edge_items:
            why = e.get('why', '')
            if e.get('author_note'):
                why += f"｜作者原话：{e['author_note']}"
            out.append(f"| {esc(e.get('quote'))} | {esc(why)} |")
        out.append("")

    gold = case.get("ground_truth") or []
    if gold:
        out.append("**当前 gold**：" + "；".join(
            f"`{g.get('rule_id')}`「{esc(g.get('quote'))}」" for g in gold
        ))
        out.append("")

    out.append("---")
    out.append("")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="生成标注确认表")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--out", default=str(ROOT / "eval" / "label-sheet.md"))
    args = ap.parse_args()

    rules = load_rules()
    rules_by_id = {r.id: r for r in rules}

    cases = []
    for path in sorted(CASES_DIR.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        if args.ids and case["id"] not in args.ids:
            continue
        cases.append(case)

    if not cases:
        print("没有匹配的样本", file=sys.stderr)
        return 1

    todo = sum(len(c.get("proposed") or []) for c in cases)
    lines = [
        "# 评测标注确认表",
        "",
        "> 由 `eval/label_sheet.py` 生成。每处预标注只需要你在最后一列写一个词：",
        ">",
        "> - `同意` → 进 gold（参与召回/误报计算）",
        "> - `不同意：一句话理由` → 我改判或删掉",
        "> - `拿不准` → 进 edge 层，单独分析，不进主指标",
        ">",
        "> 「明确不该报」默认算同意，只有不同意才写一句；「边界项」不用勾，只供你确认方向。",
        ">",
        f"> 本次共 {len(cases)} 条笔记、{todo} 处预标注待确认。判断完把文件发我即可。",
        ">",
        "> 若某条样本已经有「当前 gold」，那是历史标注，**本次仍需你确认一次**，才算双方一致。",
        ">",
        "> **只需要勾 3 处**：有「预标注」的样本已排在最前；其余 21 条没有明确违规，扫一眼边界项和反例即可。",
        "",
        "---",
        "",
    ]
    # 需要判断的排最前，其余只需抽查
    cases.sort(key=lambda c: (0 if c.get("proposed") else 1, c["id"]))
    for case in cases:
        lines.extend(render_case(case, rules_by_id))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"已生成 {out}（{len(cases)} 条笔记，{todo} 处预标注）")
    if todo == 0:
        print("提示：还没有任何 proposed；先用 eval/import_inbox.py 导入，再由 AI 预标注。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
