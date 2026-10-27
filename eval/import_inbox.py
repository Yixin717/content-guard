#!/usr/bin/env python3
"""把 data/eval_cases/inbox.md 里的笔记批量转成样本 JSON。

用法：
    python3 eval/import_inbox.py              # 真正写文件
    python3 eval/import_inbox.py --dry-run    # 只解析、只打印，不写

为什么单独做一个导入脚本：手写 12 个 JSON 一定会漏字段或转义错，
而「样本静默丢失」比脚本报错难发现得多（见 backlog B-005 / B-009）。

只解析严格的格式，不猜：
    ## 002              ← 编号，必填；可选短名（`## 002 面霜`）
    - 来源: ...          ← 可选
    - 场景: ...          ← 可选
    - 备注: ...          ← 可选
    - 名称: ...          ← 可选（决定文件名里的短名）
    ### 正文             ← 必填，下面到下一个 `## ` 之前都是正文
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "data" / "eval_cases" / "inbox.md"
OUT_DIR = ROOT / "data" / "eval_cases"

HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
NUMBER_RE = re.compile(r"^(\d{1,3})\s*(.*)$")
META_RE = re.compile(r"^-\s*(来源|场景|备注|名称|标题)\s*[:：]\s*(.*)$")
PLACEHOLDER = "把你的第"


class InboxError(Exception):
    pass


def slugify(text: str) -> str:
    """保留中文/字母/数字，去掉空格与标点；上限 20 字。"""
    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip(), flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:20] or "note"


def parse_inbox(text: str) -> list[dict]:
    lines = text.splitlines()
    blocks: list[dict] = []
    current: dict | None = None
    in_fence = False
    in_body = False

    for lineno, raw in enumerate(lines, 1):
        line = raw.rstrip("\n")
        if line.strip().startswith("```"):
            in_fence = not in_fence
            if current is not None and in_body:
                current["body"].append(line)
            continue
        if in_fence:
            if current is not None and in_body:
                current["body"].append(line)
            continue

        heading = HEADING_RE.match(line)
        if heading:
            if current is not None:
                blocks.append(current)
            title = heading.group(1)
            m = NUMBER_RE.match(title)
            if not m:
                raise InboxError(
                    f"第 {lineno} 行的标题「{title}」不是「## 数字」格式；"
                    "示例块请放进 ``` 代码块里"
                )
            current = {
                "lineno": lineno,
                "num": int(m.group(1)),
                "name": m.group(2).strip(),
                "meta": {},
                "body": [],
            }
            in_body = False
            continue

        if current is None:
            continue

        if line.strip().startswith("###"):
            if not re.match(r"^###\s*正文\s*$", line.strip()):
                raise InboxError(
                    f"第 {lineno} 行是未知的三级标题「{line.strip()}」；只认「### 正文」"
                )
            in_body = True
            continue

        if not in_body:
            meta = META_RE.match(line.strip())
            if meta:
                current["meta"][meta.group(1)] = meta.group(2).strip()
            elif line.strip():
                raise InboxError(
                    f"第 {lineno} 行在元信息区但不是「- 来源/场景/备注/名称:」格式：{line.strip()}"
                )
            continue

        current["body"].append(line)

    if current is not None:
        blocks.append(current)

    if not blocks:
        raise InboxError("没有解析到任何 `## 数字` 块")

    cases: list[dict] = []
    seen: set[int] = set()
    for b in blocks:
        num = b["num"]
        if num in seen:
            raise InboxError(f"编号 {num} 重复（第 {b['lineno']} 行附近）")
        seen.add(num)
        if not b["body"]:
            raise InboxError(f"编号 {num} 缺少「### 正文」或正文为空")
        draft = "\n".join(b["body"]).strip()
        # 真实粘贴场景里标题就是正文第一行（handover §8）；标题必须让检查器看到，
        # 否则「标题党」类违规（PLT-012）和只在标题里的绝对化用语永远测不出来。
        title = b["meta"].get("标题", "").strip()
        if title and not draft.startswith(title):
            draft = f"{title}\n{draft}"
        if PLACEHOLDER in draft:
            print(f"  · 跳过 {num:03d}：正文还是占位符", file=sys.stderr)
            continue
        # 短名优先级：名称 > 标题 > 标题里带的短名；都没有就用 note
        name = b["meta"].get("名称") or b["meta"].get("标题") or b["name"]
        case_id = f"{num:03d}-{slugify(name)}"
        cases.append(
            {
                "id": case_id,
                "split": "main",
                "source": b["meta"].get("来源", ""),
                "scene": b["meta"].get("场景", ""),
                "brief": b["meta"].get("标题", ""),
                "draft": draft,
                "proposed": [],
                "ground_truth": [],
                "expected_action": "unknown",
                "notes": b["meta"].get("备注", ""),
            }
        )
    return cases


def main() -> int:
    ap = argparse.ArgumentParser(description="inbox.md → data/eval_cases/*.json")
    ap.add_argument("--inbox", default=str(INBOX))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的样本文件")
    args = ap.parse_args()

    inbox = Path(args.inbox)
    if not inbox.exists():
        print(f"找不到 {inbox}", file=sys.stderr)
        return 1

    try:
        cases = parse_inbox(inbox.read_text(encoding="utf-8"))
    except InboxError as exc:
        print(f"解析失败：{exc}", file=sys.stderr)
        return 1

    if not cases:
        print("没有可导入的笔记（都是占位符？）", file=sys.stderr)
        return 1

    skipped = 0
    for case in cases:
        target = OUT_DIR / f"{case['id']}.json"
        if target.exists() and not args.force:
            print(f"  ! 已存在，跳过：{target.relative_to(ROOT)}（要覆盖加 --force）", file=sys.stderr)
            skipped += 1
            continue
        print(f"  + {case['id']:<24} {len(case['draft']):>4} 字  {target.relative_to(ROOT)}")
        if not args.dry_run:
            target.write_text(
                json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

    print(f"\n共 {len(cases)} 条，写入 {len(cases) - skipped} 条，跳过 {skipped} 条。")
    if args.dry_run:
        print("（--dry-run：没有写文件）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
