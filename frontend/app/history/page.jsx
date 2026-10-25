"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import StatusBar from "@/components/StatusBar";
import TopBar from "@/components/TopBar";
import { getEvent, history } from "@/lib/api";
import { K, setJSON } from "@/lib/store";

const STATUS_LABEL = { checked: "未确认", confirmed: "已确认" };

export default function HistoryPage() {
  const router = useRouter();
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    history()
      .then(setItems)
      .catch((e) => setError(e.message));
  }, []);

  async function open(id) {
    setError("");
    try {
      const res = await getEvent(id);
      const result = res.analyze || {};
      if (!result.script) {
        setError("这条记录没有可恢复的内容");
        return;
      }
      setJSON(K.check, { text: result.script, result });
      router.push("/workbench");
    } catch (e) {
      setError(e.message || "打开记录失败");
    }
  }

  return (
    <div className="app">
      <TopBar stage="entry" entryLabel="历史" onBack={() => router.push("/")} />
      <div className="main">
        <div className="page">
          <h1 className="page-title">历史</h1>
          <p className="page-sub">
            这台设备查过的文案都会留在这里（查过就算，不需要先确认）。换浏览器或清缓存后看不到旧记录。
          </p>

          {error && <p className="error-text">{error}</p>}
          {!items && !error && <p className="meta">加载中…</p>}
          {items && items.length === 0 && <p className="meta">还没有记录，回首页查一条试试。</p>}

          {items && items.length > 0 && (
            <div className="history-list">
              {items.map((it) => (
                <div className="recent-row" key={it.id} onClick={() => open(it.id)}>
                  <span className="t">{it.title || "（无标题）"}</span>
                  <span className={`n${it.count ? "" : " clean"}`}>
                    {it.count ? `${it.count} 处问题` : "未发现问题"}
                  </span>
                  <span className={`tag${it.status === "confirmed" ? " tag-ok" : ""}`}>
                    {STATUS_LABEL[it.status] || it.status}
                  </span>
                  <span className="d">
                    {String(it.createdAt || "").replace("T", " ").slice(5, 16)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <StatusBar />
    </div>
  );
}
