#!/usr/bin/env python3
"""评测脚本：读样本 → 调本地 analyze → 算指标 → 写数据报告。

用法：
    python3 eval/run_eval.py                 # 跑 main 层全部样本
    python3 eval/run_eval.py --layer all     # 三层都跑（smoke/edge 只做描述，不进主指标）
    python3 eval/run_eval.py --ids 001-zara-jacket
    python3 eval/run_eval.py --from-raw eval/runs/<id>/raw.json   # 不调模型，重算指标

为什么在本地跑：公网有 10 次/分钟限流，评测要可重复、可重算；线上另抽 3 条人工复核即可。
为什么要存 raw：调一次模型约 3 次调用，指标定义改了不该重新花钱——`--from-raw` 直接重算。

指标口径（先定义，再看数字；写进报告时也要原样带上）：
    命中    = rule_id 严格相等 且 quote 归一化后「相等或互相包含」
    召回    = 命中处数 ÷ gold 处数
    误报率  = (报出条数 - 命中条数) ÷ 报出条数
    引用正确率 = quote 在原文逐字出现 ∧ rule_id 在 rules.csv 存在 ∧ clause 与 rules.csv 一致
    uncertain（confidence < 0.7）不计入召回，单独报「灰区」——页面不展示它，对用户等于漏
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "data" / "eval_cases"
RUNS_DIR = ROOT / "eval" / "runs"
sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings
from app.rules import load_rules

# 与 scripts/verify_rules.py 的 RADICAL_FIX 保持一致：PDF 里的康熙部首与常用字码位不同。
# 这里复制一份而不是 import scripts 下的脚本，避免评测依赖「脚本所在目录可导入」。
RADICAL_FIX = {
    "⺠": "民", "⻁": "虎", "⻋": "车", "⻓": "长",
    "⻔": "门", "⻛": "风", "⻝": "食", "⼩": "小",
}

LAYERS = {"main", "smoke", "edge"}


def norm(text: str) -> str:
    """比对用的归一化：统一全/半角与部首字形，去掉所有空白。"""
    text = text or ""
    for bad, good in RADICAL_FIX.items():
        text = text.replace(bad, good)
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def quote_match(gold_quote: str, model_quote: str) -> bool:
    """同一句的判定：归一化后相等，或一段包含另一段（模型常带前后标点）。"""
    a, b = norm(gold_quote), norm(model_quote)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def pct(value) -> str:
    return "—" if value is None else f"{value:.1%}"


def esc(text: str) -> str:
    """Markdown 表格里不能有裸的 | 和换行。"""
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def git_commit() -> str:
    """返回 short hash；工作区有未提交改动时加 -dirty，避免把数字挂到错误的提交上。"""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=5, check=False,
        )
        sha = out.stdout.strip() or "unknown"
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=5, check=False,
        )
        return sha + ("-dirty" if status.stdout.strip() else "")
    except Exception:  # noqa: BLE001 —— 拿不到 git 信息不该中断评测
        return "unknown"


def load_cases(layer: str, ids: list[str] | None) -> list[dict]:
    cases = []
    for path in sorted(CASES_DIR.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        case.setdefault("split", "main")
        if case["split"] not in LAYERS:
            raise SystemExit(f"{path.name}: split 只能是 {sorted(LAYERS)}，现在是 {case['split']!r}")
        if layer != "all" and case["split"] != layer:
            continue
        if ids and case["id"] not in ids:
            continue
        if not (case.get("draft") or "").strip():
            raise SystemExit(f"{path.name}: draft 为空")
        cases.append(case)
    if not cases:
        raise SystemExit(f"没有匹配的样本（layer={layer}, ids={ids}）")
    return cases


def validate_gold(cases: list[dict], rules_by_id: dict) -> None:
    problems = []
    for case in cases:
        for i, g in enumerate(case.get("ground_truth") or []):
            rid = g.get("rule_id", "")
            if rid not in rules_by_id:
                problems.append(f"{case['id']} ground_truth[{i}]: 规则 {rid!r} 不存在于 rules.csv")
            if not (g.get("quote") or "").strip():
                problems.append(f"{case['id']} ground_truth[{i}]: quote 为空")
            elif norm(g["quote"]) not in norm(case["draft"]):
                problems.append(f"{case['id']} ground_truth[{i}]: quote 不在原文中：{g['quote']!r}")
    if problems:
        raise SystemExit("gold 自检失败（先修样本，再跑模型）：\n  - " + "\n  - ".join(problems))


def call_analyze(client, case: dict, owner: str) -> dict:
    started = time.time()
    try:
        resp = client.post(
            "/api/analyze",
            json={"content": case["draft"]},
            headers={"X-Owner-Id": owner},
            timeout=300,
        )
        elapsed_ms = int((time.time() - started) * 1000)
    except Exception as exc:  # noqa: BLE001 —— 网络/超时/服务异常都记下来，不中断整轮
        return {"error": f"{type(exc).__name__}: {exc}", "elapsed_ms": int((time.time() - started) * 1000)}
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:300]}", "elapsed_ms": elapsed_ms}
    try:
        return {"response": resp.json(), "elapsed_ms": elapsed_ms}
    except Exception as exc:  # noqa: BLE001 —— 单条响应异常不该中断整轮
        return {"error": f"响应不是 JSON: {exc}", "elapsed_ms": elapsed_ms}


def score_case(case: dict, response: dict, rules_by_id: dict) -> dict:
    """严格口径：只有 rule_id 相等且 quote 是同一句，才叫命中。"""
    draft = case["draft"]
    violations = response.get("violations") or []
    uncertain = response.get("uncertain") or []
    # 原始样本用 ground_truth，raw.json 里存成 gold；两种都认
    gold = case.get("ground_truth") or case.get("gold") or []

    used: set[int] = set()
    hits, misses = [], []
    for g in gold:
        idx = next(
            (
                i for i, v in enumerate(violations)
                if i not in used
                and v.get("rule_id") == g.get("rule_id")
                and quote_match(g.get("quote", ""), v.get("quote", ""))
            ),
            None,
        )
        if idx is None:
            misses.append(g)
        else:
            used.add(idx)
            hits.append({"gold": g, "violation": violations[idx]})

    fps = [v for i, v in enumerate(violations) if i not in used]

    # 边界项：需要资质/语境才能判，既不进 gold，也不该算误报。
    # 模型报了它 → 单独记「边界命中」，从 FP 里剔除（否则会把"判得对但依据不足"冤枉成误报）。
    edge_items = case.get("edge_items") or []
    edge_hits, scored_fps = [], []
    for v in fps:
        if any(quote_match(e.get("quote", ""), v.get("quote", "")) for e in edge_items):
            edge_hits.append(v)
        else:
            scored_fps.append(v)
    fps = scored_fps

    edge_status = []
    for e in edge_items:
        q = e.get("quote", "")
        if any(quote_match(q, v.get("quote", "")) for v in violations):
            status = "violation"
        elif any(quote_match(q, u.get("quote", "")) for u in uncertain):
            status = "uncertain"
        else:
            status = "silent"
        edge_status.append({"quote": q, "why": e.get("why", ""), "status": status})

    # 提示召回：gold 是否被「提到过」（violation 或 uncertain；同句或同规则即可）。
    # 和严格召回分开：它回答「系统有没有看见」，不回答「敢不敢下结论」。
    surface_hits = []
    for g in misses:
        q = g.get("quote", "")
        rid = g.get("rule_id", "")
        seen_quote = any(quote_match(q, v.get("quote", "")) for v in violations + uncertain)
        seen_rule = any(v.get("rule_id") == rid for v in violations + uncertain)
        if seen_quote or seen_rule:
            surface_hits.append(g)

    # 灰区：gold 落在 uncertain 里（页面不展示，对用户等于漏）
    uncertain_hits = []
    for g in gold:
        for v in uncertain:
            if v.get("rule_id") == g.get("rule_id") and quote_match(g.get("quote", ""), v.get("quote", "")):
                uncertain_hits.append({"gold": g, "violation": v})
                break

    citations = []
    for v in violations:
        rid = v.get("rule_id", "")
        rule = rules_by_id.get(rid)
        citations.append(
            {
                "rule_id": rid,
                "quote_in_draft": bool(norm(v.get("quote", ""))) and norm(v["quote"]) in norm(draft),
                "rule_exists": rule is not None,
                "clause_matches": bool(rule) and norm(v.get("clause", "")) == norm(rule.quote),
            }
        )

    # 同一句但规则报错：严格口径下它会被同时算成一次误报 + 一次漏报，这里单独标出来解释
    mismatches = []
    for fp in fps:
        for g in misses:
            if quote_match(g.get("quote", ""), fp.get("quote", "")):
                mismatches.append({"gold_rule": g.get("rule_id"), "model_rule": fp.get("rule_id"),
                                   "quote": fp.get("quote")})
                break

    reported_n = len(violations)
    # 边界命中不计分，所以误报率的分母也要把它们扣掉
    scored_reported = reported_n - len(edge_hits)
    gold_n = len(gold)
    tp = len(hits)
    fp = len(fps)
    return {
        "id": case["id"],
        "split": case["split"],
        "draft": draft,
        "gold": gold,
        "hits": hits,
        "misses": misses,
        "fps": fps,
        "edge_hits": edge_hits,
        "edge_status": edge_status,
        "mismatches": mismatches,
        "uncertain_hits": uncertain_hits,
        "surface_hits": surface_hits,
        "citations": citations,
        "gold_n": gold_n,
        "reported_n": reported_n,
        "scored_reported": scored_reported,
        "tp": tp,
        "fn": len(misses),
        "fp": fp,
        "recall": (tp / gold_n) if gold_n else None,
        "surface_rate": ((tp + len(surface_hits)) / gold_n) if gold_n else None,
        "fp_rate": (fp / scored_reported) if scored_reported else None,
        "uncertain_n": len(uncertain),
        "suspected_n": len(response.get("suspected") or []),
        "elapsed_ms": None,  # 由调用方填
    }


def aggregate(rows: list[dict]) -> dict:
    ok = [r for r in rows if not r.get("error")]
    gold = sum(r["gold_n"] for r in ok)
    tp = sum(r["tp"] for r in ok)
    fn = sum(r["fn"] for r in ok)
    surfaced = sum(len(r["surface_hits"]) for r in ok)
    reported = sum(r["reported_n"] for r in ok)
    scored_reported = sum(r["scored_reported"] for r in ok)
    edge_hits = sum(len(r["edge_hits"]) for r in ok)
    fp = sum(r["fp"] for r in ok)
    cite_n = sum(len(r["citations"]) for r in ok)
    cite_ok = sum(
        1 for r in ok for c in r["citations"]
        if c["quote_in_draft"] and c["rule_exists"] and c["clause_matches"]
    )
    return {
        "cases": len(rows),
        "cases_ok": len(ok),
        "cases_error": len(rows) - len(ok),
        "gold": gold,
        "tp": tp,
        "fn": fn,
        "reported": reported,
        "scored_reported": scored_reported,
        "edge_hits": edge_hits,
        "fp": fp,
        "recall": (tp / gold) if gold else None,
        "surfaced": surfaced,
        "surface_rate": ((tp + surfaced) / gold) if gold else None,
        "fp_rate": (fp / scored_reported) if scored_reported else None,
        "precision": (tp / scored_reported) if scored_reported else None,
        "citation_n": cite_n,
        "citation_ok": cite_ok,
        "citation_rate": (cite_ok / cite_n) if cite_n else None,
        "uncertain_hits": sum(len(r["uncertain_hits"]) for r in ok),
        "mismatches": sum(len(r["mismatches"]) for r in ok),
    }


def tokens_of(response: dict) -> tuple[int, int]:
    usage = (response or {}).get("usage") or {}
    return int(usage.get("tokens_in", 0) or 0), int(usage.get("tokens_out", 0) or 0)


def build_report(payload: dict, rows: list[dict], agg: dict) -> str:
    meta = payload
    lines: list[str] = []
    add = lines.append

    add("# 评测结果（自动生成）")
    add("")
    add("> 本文件由 `eval/run_eval.py` 生成，**不要手改**；要改口径就改脚本后重算。")
    add("> 面向面试官的解读与错误归因写在 `eval/report-v1.md`，那里引用本文件的数字。")
    add("")
    add("## 0. 运行信息")
    add("")
    add("| 项 | 值 |")
    add("|---|---|")
    add(f"| 运行时间 | {meta['started_at']} |")
    add(f"| git commit | `{meta['git_commit']}` |")
    add(f"| 模型 | `{meta['model']}` |")
    add(f"| 规则数 | {meta['rules_count']}（冻结，评测期间未改） |")
    add(f"| 样本层 | {meta['layer']} |")
    total_cases = agg["cases"] + agg.get("other_cases", 0)
    add(
        f"| 样本数 | {total_cases}（main {agg['cases']}，smoke/edge {agg.get('other_cases', 0)}；"
        f"成功 {agg['cases_ok']}，失败 {agg['cases_error']}） |"
    )
    add(f"| 总 tokens | {meta['tokens_in']:,} in / {meta['tokens_out']:,} out |")
    add(f"| 墙钟耗时 | {meta['elapsed_s']:.1f}s |")
    add(f"| 成本 | {meta['cost_text']} |")
    add("")

    add("## 1. 指标口径")
    add("")
    add("| 指标 | 定义 |")
    add("|---|---|")
    add("| 命中 | `rule_id` 严格相等 **且** `quote` 归一化后相等或互相包含 |")
    add("| 召回 recall | 命中处数 ÷ gold 处数 |")
    add("| 误报率 FP rate | （报出条数 − 命中条数）÷ 报出条数 |")
    add("| 引用正确率 | `quote` 在原文逐字出现 ∧ `rule_id` 在 rules.csv 存在 ∧ `clause` 与 rules.csv 一致 |")
    add("")
    add("补充说明：")
    add("")
    add("- 一次 `analyze` 会做**两遍独立检查取并集**，所以召回高于单次检查，误报也可能更高；这是真实产品口径，不是评测脚本额外加的。")
    add("- **严格召回**只算 `violations`；**提示召回**把 `uncertain` 里提到过的也算上，两者差值就是「模型看见了但不敢定」的部分。")
    add("- `uncertain`（confidence < 0.7）不计入严格召回——页面不展示它，对用户就是漏；单独列在第 4.3 节「灰区」。")
    add("- 严格口径下，同一句报错规则会**同时**算一次误报和一次漏报；第 4 节把它们标成「同句不同规则」，便于解释。")
    add("- **边界项**（需要资质/语境才能判，如「护眼」「母婴级」）单列：模型报了不算误报，不报也不算漏；处理情况见第 4.4 节。")
    add("")

    add("## 2. 总体指标")
    add("")
    add("| 指标 | 值 | 分子 / 分母 |")
    add("|---|---|---|")
    add(f"| 严格召回 recall | **{pct(agg['recall'])}** | {agg['tp']} / {agg['gold']} |")
    add(f"| 提示召回（含 uncertain） | {pct(agg['surface_rate'])} | {agg['tp'] + agg['surfaced']} / {agg['gold']} |")
    add(f"| 误报率 FP rate | **{pct(agg['fp_rate'])}** | {agg['fp']} / {agg['scored_reported']}（已剔除边界命中） |")
    add(f"| 精确率 precision | {pct(agg['precision'])} | {agg['tp']} / {agg['scored_reported']} |")
    add(f"| 引用正确率 | **{pct(agg['citation_rate'])}** | {agg['citation_ok']} / {agg['citation_n']} |")
    add(f"| 边界命中（不计分） | {agg['edge_hits']} 处 | 需要资质/语境，判对方向但依据不足 |")
    add(f"| 灰区命中（不计入召回） | {agg['uncertain_hits']} 处 | — |")
    add(f"| 同句不同规则 | {agg['mismatches']} 处 | — |")
    add("")
    if agg["other_cases"]:
        add(f"> 另有 {agg['other_cases']} 条 smoke/edge 样本，按约定**不计入主指标**；逐条结果仍列在第 3 节。")
    if agg["cases_ok"] == 0:
        add("> 本次没有成功的 main 层样本，主指标不适用（表中为 —，不是 0）。")
    add("> 样本少（12–24 条），以上是**单次运行**的观察值，不是稳定估计；跑第二遍会有波动。")
    add("")

    add("## 3. 逐条结果")
    add("")
    add("| 样本 | 层 | gold | 报出 | 边界 | 命中 | 漏 | 误 | 召回 | 误报率 | 耗时 | tokens in/out |")
    add("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if r.get("error"):
            add(f"| {r['id']} | — | — | — | — | — | — | — | — | — | {r['elapsed_ms']}ms | ❌ 失败 |")
            continue
        add(
            f"| {r['id']} | {r['split']} | {r['gold_n']} | {r['reported_n']} | {len(r['edge_hits'])} | {r['tp']} | "
            f"{r['fn']} | {r['fp']} | {pct(r['recall'])} | {pct(r['fp_rate'])} | "
            f"{r['elapsed_ms']}ms | {r['tokens_in']:,}/{r['tokens_out']:,} |"
        )
    add("")

    errors = [r for r in rows if r.get("error")]
    if errors:
        add("### 失败样本")
        add("")
        for r in errors:
            add(f"- **{r['id']}**：`{r['error']}`")
        add("")

    add("## 4. 错误明细")
    add("")
    miss_rows = [r for r in rows if not r.get("error") and r["misses"]]
    if not miss_rows:
        add("### 4.1 漏报（FN）")
        add("")
        add("无。")
        add("")
    else:
        add("### 4.1 漏报（FN）")
        add("")
        for r in miss_rows:
            for g in r["misses"]:
                extra = ""
                same = [m for m in r["mismatches"] if m["gold_rule"] == g.get("rule_id")]
                if same:
                    extra = f"（模型报了同一句但规则是 `{same[0]['model_rule']}`）"
                elif any(sg.get("quote") == g.get("quote") for sg in r["surface_hits"]):
                    extra = "（模型在 uncertain 里提到过，但没敢定成违规）"
                else:
                    extra = "（完全没提）"
                add(f"- **{r['id']}** 应报 `{g.get('rule_id')}`「{g.get('quote')}」{extra}")
        add("")

    fp_rows = [r for r in rows if not r.get("error") and r["fps"]]
    if not fp_rows:
        add("### 4.2 误报（FP）")
        add("")
        add("无。")
        add("")
    else:
        add("### 4.2 误报（FP）")
        add("")
        for r in fp_rows:
            for v in r["fps"]:
                conf = v.get("confidence")
                conf_txt = f"，confidence {conf:.2f}" if isinstance(conf, (int, float)) else ""
                note = "（同句不同规则）" if any(
                    m["model_rule"] == v.get("rule_id") and quote_match(m.get("quote", ""), v.get("quote", ""))
                    for m in r["mismatches"]
                ) else ""
                add(f"- **{r['id']}** 报 `{v.get('rule_id')}`「{v.get('quote')}」{conf_txt}{note}")
        add("")

    unc_rows = [r for r in rows if not r.get("error") and r["uncertain_hits"]]
    add("### 4.3 灰区（gold 落在 uncertain，页面不展示）")
    add("")
    if not unc_rows:
        add("无。")
    else:
        for r in unc_rows:
            for h in r["uncertain_hits"]:
                v = h["violation"]
                add(
                    f"- **{r['id']}** `{v.get('rule_id')}`「{v.get('quote')}」"
                    f"confidence {v.get('confidence')} — 用户看不到"
                )
    add("")

    add("### 4.4 边界项（不计分，看方向对不对）")
    add("")
    add("> 这些句子需要资质/语境才能定性，**不进 gold、也不算误报**；列出来是看模型有没有「顶出来」。")
    add("")
    edge_rows = [(r, e) for r in rows if not r.get("error") for e in r["edge_status"]]
    if not edge_rows:
        add("无。")
    else:
        add("| 样本 | 原句 | 模型处理 | 说明 |")
        add("|---|---|---|---|")
        label = {"violation": "报了（violation）", "uncertain": "报了（uncertain）", "silent": "未提示"}
        for r, e in edge_rows:
            add(f"| {r['id']} | {esc(e['quote'])} | {label[e['status']]} | {esc(e['why'])} |")
    add("")

    add("## 5. 规则维度")
    add("")
    add("| 规则 | 名称 | gold 处数 | 命中 | 漏 | 模型报出 | 其中误报 |")
    add("|---|---|---|---|---|---|---|")
    stat: dict[str, dict] = {}

    def slot(rid: str) -> dict:
        return stat.setdefault(rid, {"gold": 0, "hit": 0, "miss": 0, "reported": 0, "fp": 0})

    for r in rows:
        if r.get("error"):
            continue
        for g in r["gold"]:
            slot(g.get("rule_id", ""))["gold"] += 1
        for h in r["hits"]:
            rid = h["gold"].get("rule_id", "")
            slot(rid)["hit"] += 1
            slot(rid)["reported"] += 1
        for g in r["misses"]:
            slot(g.get("rule_id", ""))["miss"] += 1
        for v in r["fps"]:
            rid = v.get("rule_id", "")
            slot(rid)["reported"] += 1
            slot(rid)["fp"] += 1
    for rid in sorted(stat):
        s = stat[rid]
        rule = payload["rules_by_id"].get(rid)
        title = getattr(rule, "title", "")
        add(f"| `{rid}` | {title} | {s['gold']} | {s['hit']} | {s['miss']} | {s['reported']} | {s['fp']} |")
    add("")

    add("## 6. 局限（必须一起读）")
    add("")
    add("- 样本量小（本次 " + str(agg["cases_ok"]) + " 条），只说明这一批的方向，不能外推成平台整体准确率。")
    add("- gold 是「AI 按条款预标注 + 作者逐条确认」得到的一致项，不是法律专家判定；拿不准的进 edge 层，不参与主指标。")
    add("- 只测一个模型（`" + meta["model"] + "`）、一套 prompt、一次运行；prompt 或规则一变就要重跑。")
    add("- 只覆盖文本；图片、视频、账号级规则（推广占比、连发）不在范围内。")
    add("- 严格 rule_id 口径会把「同句不同规则」同时记成漏报 + 误报，数字偏保守，这是有意为之。")
    add("")
    add("## 7. 复现")
    add("")
    add("```bash")
    add("cd content-guard")
    add("python3 eval/run_eval.py" + (" --layer all" if meta["layer"] == "all" else ""))
    add("# 不重新调模型，只按当前指标定义重算：")
    add(f"python3 eval/run_eval.py --from-raw {meta['run_dir']}/raw.json")
    add("```")
    add("")
    return "\n".join(lines)


def cost_text(tokens_in: int, tokens_out: int) -> str:
    pin, pout = settings.price_input_per_m, settings.price_output_per_m
    if not pin and not pout:
        return "未配置单价（`DEEPSEEK_PRICE_INPUT/OUTPUT`），不折算金额"
    cost = tokens_in / 1_000_000 * pin + tokens_out / 1_000_000 * pout
    return f"约 ¥{cost:.3f}（按 .env 单价）"


def main() -> int:
    ap = argparse.ArgumentParser(description="Content Guard 评测")
    ap.add_argument("--layer", default="main", choices=["main", "smoke", "edge", "all"])
    ap.add_argument("--ids", nargs="*", help="只跑指定 id")
    ap.add_argument("--from-raw", help="从已有 raw.json 重算，不调模型")
    ap.add_argument("--out", default=str(ROOT / "eval" / "results-v1.md"))
    ap.add_argument("--sleep", type=float, default=0.5, help="每条之间的间隔秒数")
    ap.add_argument("--owner", default="eval-runner", help="写入本地库时用的匿名设备号")
    args = ap.parse_args()

    started_at = datetime.now().isoformat(timespec="seconds")
    all_rules = load_rules()
    # 评分只认 Rule 对象：rule.quote 是 rules.csv 的条款原文，用来核对引用
    rules_by_id = {r.id: r for r in all_rules}

    if args.from_raw:
        raw = json.loads(Path(args.from_raw).read_text(encoding="utf-8"))
        payload = raw
        cases = raw["cases"]
        rows = []
        for c in cases:
            if c.get("error"):
                rows.append({"id": c["id"], "split": c.get("split", "main"), "error": c["error"],
                             "elapsed_ms": c.get("elapsed_ms", 0)})
                continue
            row = score_case(c, c["response"], rules_by_id)
            row["elapsed_ms"] = c.get("elapsed_ms", 0)
            row["tokens_in"], row["tokens_out"] = tokens_of(c["response"])
            rows.append(row)
        payload["run_dir"] = str(Path(args.from_raw).resolve().parent)
    else:
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        cases = load_cases(args.layer, args.ids)
        validate_gold(cases, rules_by_id)

        # 评测数据写到独立的 SQLite，不污染本地开发/演示的历史记录
        settings.db_path = run_dir / "eval.db"

        from app.api import app
        from fastapi.testclient import TestClient

        payload = {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "started_at": started_at,
            "git_commit": git_commit(),
            "model": settings.model,
            "rules_count": len(all_rules),
            "layer": args.layer,
            "owner": args.owner,
            "cases": [],
        }
        rows = []
        t0 = time.time()
        print(f"样本 {len(cases)} 条；模型 {settings.model}；规则 {len(all_rules)} 条")
        print(f"运行目录 {run_dir.relative_to(ROOT)}\n")

        with TestClient(app) as client:
            for i, case in enumerate(cases, 1):
                print(f"[{i}/{len(cases)}] {case['id']} … ", end="", flush=True)
                result = call_analyze(client, case, args.owner)
                entry = {"id": case["id"], "split": case["split"],
                         "draft": case["draft"], "gold": case.get("ground_truth") or [],
                         "edge_items": case.get("edge_items") or [],
                         "elapsed_ms": result["elapsed_ms"]}
                if "error" in result:
                    entry["error"] = result["error"]
                    rows.append({"id": case["id"], "split": case["split"],
                                 "error": result["error"], "elapsed_ms": result["elapsed_ms"]})
                    print(f"❌ {result['error']}")
                else:
                    entry["response"] = result["response"]
                    row = score_case(case, result["response"], rules_by_id)
                    row["elapsed_ms"] = result["elapsed_ms"]
                    row["tokens_in"], row["tokens_out"] = tokens_of(result["response"])
                    rows.append(row)
                    print(
                        f"gold {row['gold_n']} / 报出 {row['reported_n']} / "
                        f"命中 {row['tp']} / {result['elapsed_ms']}ms"
                    )
                payload["cases"].append(entry)
                if i < len(cases) and args.sleep:
                    time.sleep(args.sleep)

        payload["elapsed_s"] = time.time() - t0
        payload["tokens_in"] = sum(r.get("tokens_in", 0) for r in rows if not r.get("error"))
        payload["tokens_out"] = sum(r.get("tokens_out", 0) for r in rows if not r.get("error"))
        payload["cases"] = [
            {k: v for k, v in c.items()
             if k in ("id", "split", "draft", "gold", "edge_items", "response", "error", "elapsed_ms")}
            for c in payload["cases"]
        ]
        (run_dir / "raw.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    # 主指标只算 main 层：smoke 太容易、edge 是「拿不准」，混进来会污染数字
    main_rows = [r for r in rows if r.get("split") == "main"]
    other_rows = [r for r in rows if r.get("split") != "main"]
    agg = aggregate(main_rows)
    agg["other_cases"] = len(other_rows)
    payload.setdefault("elapsed_s", 0.0)
    payload.setdefault("tokens_in", sum(r.get("tokens_in", 0) for r in rows if not r.get("error")))
    payload.setdefault("tokens_out", sum(r.get("tokens_out", 0) for r in rows if not r.get("error")))
    payload["cost_text"] = cost_text(payload["tokens_in"], payload["tokens_out"])
    payload["rules_by_id"] = rules_by_id

    report = build_report(payload, rows, agg)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")

    if not args.from_raw:
        (run_dir / "metrics.json").write_text(
            json.dumps({"aggregate": agg, "cases": [
                {k: r.get(k) for k in ("id", "split", "gold_n", "reported_n", "tp", "fn", "fp",
                                       "recall", "fp_rate", "elapsed_ms", "tokens_in", "tokens_out", "error")}
                for r in rows
            ]}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print()
    print(f"召回 {pct(agg['recall'])}（{agg['tp']}/{agg['gold']}）  "
          f"误报率 {pct(agg['fp_rate'])}（{agg['fp']}/{agg['reported']}）  "
          f"引用正确率 {pct(agg['citation_rate'])}  "
          f"灰区 {agg['uncertain_hits']}")
    print(f"报告：{out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return 0 if agg["cases_error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
