"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import StatusBar from "@/components/StatusBar";
import TopBar from "@/components/TopBar";
import { rules as fetchRules } from "@/lib/api";

const CATS = [
  { key: "all", label: "全部" },
  { key: "absolute", label: "绝对化用语" },
  { key: "false_claim", label: "虚假宣传" },
  { key: "platform", label: "平台规则" },
];

const STATUS_LABEL = {
  verified: "法条核验",
  platform_official: "平台官方",
  platform_pending: "依据待补",
};

export default function RulesPage() {
  const router = useRouter();
  const [items, setItems] = useState(null);
  const [cat, setCat] = useState("all");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(null);

  useEffect(() => {
    fetchRules()
      .then(setItems)
      .catch(() => setItems([]));
  }, []);

  const stats = useMemo(() => {
    const list = items || [];
    const by = (s) => list.filter((r) => r.status === s).length;
    return { total: list.length, verified: by("verified"), official: by("platform_official"), pending: by("platform_pending") };
  }, [items]);

  const filtered = useMemo(() => {
    const list = items || [];
    return list.filter((r) => {
      if (cat !== "all" && r.category !== cat) return false;
      if (!q.trim()) return true;
      const hay = `${r.id} ${r.title} ${r.quote} ${r.source} ${r.counter_examples || ""}`.toLowerCase();
      return hay.includes(q.trim().toLowerCase());
    });
  }, [items, cat, q]);

  return (
    <div className="app">
      <TopBar stage="entry" entryLabel="规则" onBack={() => router.push("/")} />
      <div className="main">
        <div className="page">
          <h1 className="page-title">规则库</h1>
          <p className="page-sub">
            共 {stats.total} 条 · 法条核验 {stats.verified} / 平台官方 {stats.official} / 依据待补 {stats.pending}
          </p>

          <div className="toolbar">
            {CATS.map((c) => (
              <button key={c.key} className={`chip${cat === c.key ? " on" : ""}`} onClick={() => setCat(c.key)}>
                {c.label}
              </button>
            ))}
            <div className="spacer" />
            <input
              className="search"
              placeholder="搜索标题 / 原文 / 关键词"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>

          {!items && <p className="meta">加载中…</p>}
          {items && filtered.length === 0 && <p className="meta">没有匹配的规则。</p>}

          {filtered.map((r) => (
            <div className="rule-row" key={r.id} onClick={() => setOpen(open === r.id ? null : r.id)}>
              <div className="rule-row-top">
                <span className="rule-id mono">{r.id}</span>
                <span className={`tag tag-${r.status}`}>{STATUS_LABEL[r.status] || r.status}</span>
                <span className={`pill pill-${r.severity}`}>{r.severity === "high" ? "高危" : r.severity === "medium" ? "中危" : "低危"}</span>
                <div className="spacer" />
                <span className="dim">{r.source}</span>
              </div>
              <div className="rule-title">{r.title}</div>
              {open === r.id && (
                <div className="rule-detail">
                  <div className="label">条款原文</div>
                  <div className="clause">{r.quote}</div>
                  {r.counter_examples && (
                    <>
                      <div className="label">反例（不算违规）</div>
                      <div className="suggest">{r.counter_examples}</div>
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
      <StatusBar />
    </div>
  );
}
