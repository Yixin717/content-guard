#!/usr/bin/env python3
"""校验 rules.csv 的真实性与完整性。

用法：
    python scripts/verify_rules.py              # 离线校验（默认）
    python scripts/verify_rules.py --check-urls # 额外检查来源链接是否可访问

校验项：
    1. 必填字段非空
    2. rule_id 唯一且前缀与 category 匹配
    3. category / severity / status 取值合法
    4. status=verified 的规则，quote 必须是 docs/sources/ 下存档原文的逐字子串
    5. status=platform_pending 的规则，note 里必须写明待补事项
    6. --check-urls 时，所有 source_url 必须返回 HTTP 200

任何一项失败 → 退出码 1。
"""

from __future__ import annotations

import csv
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES_CSV = ROOT / "rules.csv"
SOURCES_DIR = ROOT / "docs" / "sources"

REQUIRED_FIELDS = [
    "id", "category", "title", "quote", "source",
    "source_url", "fetched_at", "severity", "status", "examples", "note",
]
CATEGORIES = {"absolute", "false_claim", "platform"}
PREFIX = {"absolute": "ABS", "false_claim": "FLM", "platform": "PLT"}
SEVERITIES = {"high", "medium", "low"}
STATUSES = {"verified", "platform_official", "platform_pending"}
# 需要与存档原文逐字比对的来源状态
QUOTED_STATUSES = {"verified", "platform_official"}


def load_archive_text() -> str:
    """把 docs/sources/ 下的所有存档拼成一个大字符串，用于逐字比对。"""
    if not SOURCES_DIR.exists():
        return ""
    parts = []
    for path in sorted(SOURCES_DIR.rglob("*.md")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def check_urls(rows: list[dict]) -> list[str]:
    errors = []
    seen: set[str] = set()
    for url in sorted({r["source_url"] for r in rows}):
        if url in seen or not url.startswith("http"):
            continue
        seen.add(url)
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "content-guard/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                code = resp.status
        except urllib.error.HTTPError as exc:  # 4xx / 5xx
            code = exc.code
        except Exception as exc:  # 网络不可达等
            errors.append(f"来源不可访问: {url} ({type(exc).__name__})")
            continue
        if code != 200:
            errors.append(f"来源返回 {code}: {url}")
        else:
            print(f"  ✓ 200 {url}")
    return errors


def main() -> int:
    if not RULES_CSV.exists():
        print(f"找不到 {RULES_CSV}")
        return 1

    with RULES_CSV.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        header = reader.fieldnames or []

    errors: list[str] = []
    warnings: list[str] = []

    missing_cols = [c for c in REQUIRED_FIELDS if c not in header]
    if missing_cols:
        errors.append(f"缺少列: {', '.join(missing_cols)}")

    archive = load_archive_text()
    if not archive:
        errors.append("docs/sources/ 下没有存档文件，无法校验 verified 规则")

    seen_ids: Counter[str] = Counter()
    for line_no, row in enumerate(rows, start=2):  # 第 1 行是表头
        rid = (row.get("id") or "").strip()
        tag = f"第 {line_no} 行 {rid or '<无 id>'}"

        for field in REQUIRED_FIELDS:
            if not (row.get(field) or "").strip():
                errors.append(f"{tag}: 字段 {field} 为空")

        if not rid:
            continue
        seen_ids[rid] += 1

        category = (row.get("category") or "").strip()
        if category not in CATEGORIES:
            errors.append(f"{tag}: category 非法值 {category!r}")
        elif not rid.startswith(PREFIX[category] + "-"):
            errors.append(f"{tag}: 前缀与 category={category} 不匹配（应为 {PREFIX[category]}-xxx）")

        severity = (row.get("severity") or "").strip()
        if severity not in SEVERITIES:
            errors.append(f"{tag}: severity 非法值 {severity!r}")

        status = (row.get("status") or "").strip()
        if status not in STATUSES:
            errors.append(f"{tag}: status 非法值 {status!r}")
        elif status in QUOTED_STATUSES:
            quote = (row.get("quote") or "").strip()
            if quote and quote not in archive:
                errors.append(
                    f"{tag}: quote 在存档原文中找不到逐字匹配 —— 可能改写或抄错\n"
                    f"        quote: {quote}"
                )
        elif status == "platform_pending":
            note = (row.get("note") or "")
            if "待" not in note:
                warnings.append(f"{tag}: platform_pending 但 note 未说明待补事项")

        # source_url 允许是 http(s) 链接，或仓库内存档的相对路径
        src_url = (row.get("source_url") or "").strip()
        if src_url and not src_url.startswith("http"):
            if not (ROOT / src_url).exists():
                errors.append(f"{tag}: source_url 指向的本地存档不存在 —— {src_url}")

    for rid, count in seen_ids.items():
        if count > 1:
            errors.append(f"id 重复 {count} 次: {rid}")

    by_category = Counter((r.get("category") or "").strip() for r in rows)
    by_status = Counter((r.get("status") or "").strip() for r in rows)

    print("=" * 60)
    print(f"规则总数: {len(rows)}")
    print("按类别: " + ", ".join(f"{k}={v}" for k, v in sorted(by_category.items())))
    print("按状态: " + ", ".join(f"{k}={v}" for k, v in sorted(by_status.items())))

    if "--check-urls" in sys.argv:
        print("\n检查来源链接：")
        errors.extend(check_urls([r for r in rows if r.get("source_url")]))

    print("-" * 60)
    for w in warnings:
        print(f"⚠ 警告: {w}")
    if errors:
        for e in errors:
            print(f"✗ {e}")
        print(f"\n结果：{len(errors)} 项失败，{len(warnings)} 项警告")
        return 1

    print(f"结果：全部通过（{len(warnings)} 项警告，0 项失败）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
