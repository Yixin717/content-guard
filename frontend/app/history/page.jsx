"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import StatusBar from "@/components/StatusBar";
import TopBar from "@/components/TopBar";
import { history } from "@/lib/api";

export default function HistoryPage() {
  const router = useRouter();
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    history()
      .then(setItems)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="app">
      <TopBar stage="entry" entryLabel="历史" onBack={() => router.push("/")} />
      <div className="main">
        <div className="page">
          <h1 className="page-title">历史</h1>
          <p className="page-sub">已人工确认的文案，按确认时间倒序。</p>

          {error && <p className="error-text">{error}</p>}
          {!items && !error && <p className="meta">加载中…</p>}
          {items && items.length === 0 && <p className="meta">还没有确认过的文案。</p>}

          {items && items.length > 0 && (
            <table className="table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>标题</th>
                  <th>来源</th>
                  <th>审核人</th>
                  <th>审计编号</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr key={it.audit_id}>
                    <td className="mono dim">{it.created_at}</td>
                    <td>{it.title}</td>
                    <td className="dim">{it.angle_name || "—"}</td>
                    <td className="dim">{it.reviewer || "—"}</td>
                    <td className="mono dim">#{it.audit_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <StatusBar />
    </div>
  );
}
