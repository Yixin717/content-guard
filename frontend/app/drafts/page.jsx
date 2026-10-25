"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Icon from "@/components/Icon";
import StatusBar from "@/components/StatusBar";
import TopBar from "@/components/TopBar";
import { DRAFTS } from "@/lib/mock";
import { K, getJSON, setJSON } from "@/lib/store";

export default function DraftsPage() {
  const router = useRouter();
  const [drafts, setDrafts] = useState(null);

  useEffect(() => {
    setDrafts(getJSON(K.drafts, DRAFTS));
  }, []);

  function pick(d) {
    setJSON(K.picked, d);
    router.push("/workbench?from=draft");
  }

  return (
    <div className="app">
      <TopBar stage="drafts" onBack={() => router.push("/")} />

      <div className="main">
        {!drafts ? (
          <div className="drafts">
            <div className="drafts-head">
              <h2>正在生成 3 版…</h2>
              <span className="hint">生成时会逐条对照 40 条规则，约 10–20 秒</span>
            </div>
            <div className="drafts-grid">
              {[0, 1, 2].map((i) => (
                <div className="draft-col" key={i}>
                  <div className="draft-skeleton">
                    <span /><span /><span /><span /><span />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="drafts">
            <div className="drafts-head">
              <h2>3 版草稿</h2>
              <span className="hint">三版都已跑过 40 条规则自检，选一版继续确认</span>
              <div className="spacer" />
              <button className="btn btn-text btn-sm" onClick={() => router.push("/?mode=write")}>
                重新生成
              </button>
            </div>

            <div className="drafts-grid">
              {drafts.map((d) => (
                <div className="draft-col" key={d.angle}>
                  <div className="draft-top">
                    <span className="draft-angle">{d.angle_name || d.angleName}</span>
                    <div className="spacer" />
                    <span className="chars mono">
                      {(d.script || d.text || "").length} 字
                    </span>
                  </div>

                  <h3>{d.title}</h3>
                  <p className="body">{d.script || d.text}</p>

                  {d.selling_points?.length > 0 && (
                    <ul className="points">
                      {d.selling_points.map((p) => (
                        <li key={p}>{p}</li>
                      ))}
                    </ul>
                  )}

                  <div className="draft-foot">
                    <span className="check">
                      <Icon name="check" size={13} />
                      {d.self_check?.passed === false
                        ? "需人工确认"
                        : `自检通过 · ${d.self_check?.rules || 40} 条`}
                    </span>
                    <div className="spacer" />
                    <button className="btn btn-ghost btn-sm" onClick={() => pick(d)}>
                      用这版 <Icon name="arrow" size={13} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <StatusBar />
    </div>
  );
}
