"""规则库：CSV 是唯一事实来源，JSON 是派生产物；检索用字符二元组 BM25。

为什么不用向量库：规则只有 39 条，可解释、可离线、零依赖的 BM25 足够；
全量规则本身也就 4K token，检索的作用是「缩小范围 + 给出命中理由」，不是唯一依据。
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from .config import settings


@dataclass
class Rule:
    id: str
    category: str
    title: str
    quote: str
    source: str
    source_url: str
    fetched_at: str
    severity: str
    status: str
    examples: str
    note: str
    version: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)

    @property
    def example_list(self) -> List[str]:
        return [e for e in self.examples.split("|") if e.strip()]

    def digest(self) -> str:
        """给 LLM 看的一行摘要，控制 token。"""
        return (
            f"[{self.id}] {self.title}\n"
            f"  依据：{self.source}｜严重度：{self.severity}｜状态：{self.status}\n"
            f"  原文：“{self.quote}”\n"
            f"  例：{'、'.join(self.example_list)}"
        )


def load_rules(csv_path=None) -> List[Rule]:
    path = csv_path or settings.rules_csv
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return [Rule(**{k: (row.get(k) or "") for k in Rule.__dataclass_fields__}) for row in rows]


def export_json(rules: Iterable[Rule], out_path=None) -> str:
    path = out_path or settings.rules_json
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": rules_version(rules),
        "count": len(list(rules)) if not isinstance(rules, list) else len(rules),
        "rules": [r.to_dict() for r in rules],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def rules_version(rules: Iterable[Rule]) -> str:
    versions = {r.version for r in rules}
    return sorted(versions)[-1] if versions else "unknown"


# ---------- 极简 BM25（中文按字符二元组切分） ----------

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> List[str]:
    text = text.lower()
    tokens: List[str] = _TOKEN_RE.findall(text)
    han = re.sub(r"[^\u4e00-\u9fa5]", "", text)
    tokens.extend(han[i : i + 2] for i in range(len(han) - 1))
    return tokens


class BM25:
    def __init__(self, docs: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.avgdl = sum(len(d) for d in docs) / max(len(docs), 1)
        self.freqs = [Counter(d) for d in docs]
        df = Counter()
        for d in docs:
            df.update(set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def score(self, query: List[str], idx: int) -> float:
        freqs, doc_len = self.freqs[idx], len(self.docs[idx])
        total = 0.0
        for t in query:
            if t not in freqs:
                continue
            idf = self.idf.get(t, 0.0)
            tf = freqs[t]
            total += idf * (tf * (self.k1 + 1)) / (tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl))
        return total


def retrieve(rules: List[Rule], query: str, top_k: int = 18, category: Optional[str] = None) -> List[Rule]:
    """按 BM25 取 top_k；同分时按严重度排序，保证 high 优先露出。"""
    pool = [r for r in rules if (category is None or r.category == category)]
    docs = [tokenize(f"{r.title} {r.quote} {r.examples} {r.note}") for r in pool]
    bm25 = BM25(docs)
    q = tokenize(query)
    order = {"high": 0, "medium": 1, "low": 2}
    scored = sorted(
        zip(pool, (bm25.score(q, i) for i in range(len(pool)))),
        key=lambda x: (-x[1], order.get(x[0].severity, 9)),
    )
    return [r for r, _ in scored[:top_k]]
