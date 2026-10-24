#!/usr/bin/env python3
"""rules.csv → data/rules.json（派生文件，供前端/评测读取）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.rules import export_json, load_rules, rules_version  # noqa: E402

if __name__ == "__main__":
    rules = load_rules()
    path = export_json(rules)
    print(f"导出 {len(rules)} 条规则 → {path}（version={rules_version(rules)}）")
