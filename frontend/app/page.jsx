"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Icon from "@/components/Icon";
import StatusBar from "@/components/StatusBar";
import TopBar from "@/components/TopBar";
import { analyze, generate, getEvent, history } from "@/lib/api";
import { RULE_COUNT } from "@/lib/mock";
import { K, getJSON, setJSON } from "@/lib/store";

const SAMPLE_TEXT =
  "姐妹们，这条裤子全网最低价！三天根治大腿根的痘印，国家级品质，加V领福利。我自己穿了三个月，洗完不皱，垂感一直在。69 两条，周末截止。";

export default function EntryPage() {
  const router = useRouter();
  const [mode, setMode] = useState("check");
  // 默认空输入框，示例只做灰色占位；从工作台点「编辑原文」回来时回填上次粘贴的内容
  const [text, setText] = useState("");
  const [brief, setBrief] = useState("杭州女装小店的冰丝阔腿裤，遮胯显瘦、垂感好，面向胯宽腿粗的女生，69 元两条。");
  const [price, setPrice] = useState("69 元两条，周末截止");
  const [tone, setTone] = useState("像朋友聊天");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [recent, setRecent] = useState(null);
  const [elapsed, setElapsed] = useState(0);

  // 真实等待计时：一次请求要跑完检查+改写+复检，不能只显示"检查中…"
  useEffect(() => {
    if (!busy) {
      setElapsed(0);
      return undefined;
    }
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 500);
    return () => clearInterval(timer);
  }, [busy]);

  useEffect(() => {
    const m = new URLSearchParams(window.location.search).get("mode");
    if (m === "write") setMode("write");
    const stored = getJSON(K.check);
    if (stored?.text) setText(stored.text);
  }, []);

  // 「最近」读真实历史（后端没起时 api 层才退回样例，见 lib/api.js）
  useEffect(() => {
    history()
      .then((items) => setRecent(items || []))
      .catch(() => setRecent([]));
  }, []);

  // 点一条历史：拿回当次快照，直接恢复工作台
  async function openEvent(id) {
    setError("");
    try {
      const res = await getEvent(id);
      const result = res.analyze || {};
      if (!result.script) {
        router.push("/history");
        return;
      }
      setJSON(K.check, { text: result.script, result });
      router.push("/workbench");
    } catch (e) {
      setError(e.message || "打开记录失败");
    }
  }

  // 一次算完：服务端内部 检查 → 改写 → 复检（ADR-009）
  async function runAnalyze(input) {
    const content = (input || "").trim();
    setError("");
    setBusy("analyze");
    try {
      const result = await analyze(content);
      setJSON(K.check, { text: content, result });
      router.push("/workbench");
    } catch (e) {
      setError(e.message || "检查失败，请重试");
    } finally {
      setBusy("");
    }
  }

  // 空着直接检查 = 用灰色示例跑一遍（演示用）
  function onCheck() {
    const content = text.trim() ? text : SAMPLE_TEXT;
    if (!text.trim()) setText(SAMPLE_TEXT);
    runAnalyze(content);
  }

  // 空输入框按回车不再换行，而是直接用示例开跑
  function onComposerKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey && !text.trim() && !busy) {
      e.preventDefault();
      onCheck();
    }
  }

  async function onGenerate() {
    setError("");
    setBusy("generate");
    try {
      const { drafts, usage } = await generate(`${brief}\n价格与活动：${price}\n语气：${tone}`);
      setJSON(K.drafts, drafts);
      setJSON(K.genUsage, usage);
      router.push("/drafts");
    } catch (e) {
      setError(e.message || "生成失败，请重试");
    } finally {
      setBusy("");
    }
  }


  return (
    <div className="app">
      <TopBar stage="entry" entryLabel={mode === "write" ? "生成" : "粘贴"} canConfirm={false} />

      <div className="main">
        {mode === "write" ? (
          <div className="entry-wrap">
            <div className="entry">
              <h1>先写一版</h1>
              <p className="sub">填三样东西就行，生成 3 个角度的草稿，出稿前会先过一遍 40 条规则。</p>

              <div className="brief-form">
                <div className="field">
                  <label>卖什么、卖给谁</label>
                  <textarea value={brief} onChange={(e) => setBrief(e.target.value)} />
                </div>
                <div className="field">
                  <label>价格与活动</label>
                  <input value={price} onChange={(e) => setPrice(e.target.value)} />
                </div>
                <div className="field">
                  <label>语气</label>
                  <div className="chips">
                    {["像朋友聊天", "专业克制", "活泼种草"].map((t) => (
                      <button
                        key={t}
                        className={`chip${tone === t ? " on" : ""}`}
                        onClick={() => setTone(t)}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="form-foot">
                  <button className="btn btn-primary" onClick={onGenerate} disabled={busy === "generate"}>
                    {busy === "generate" ? "生成中…" : "生成 3 版"} <Icon name="arrow" size={14} />
                  </button>
                  <button className="btn btn-text btn-sm" onClick={() => setMode("check")} disabled={!!busy}>
                    回到检查
                  </button>
                </div>
                {error && <p className="error-text">{error}</p>}
              </div>
            </div>
          </div>
        ) : (
          <div className="entry-wrap">
            <div className="entry">
              <h1>Content Guard</h1>
              <p className="sub">发布前先过一遍，帮你稳稳过关！</p>

              <div className="composer">
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={onComposerKeyDown}
                  placeholder={SAMPLE_TEXT}
                  aria-label="粘贴要检查的文案"
                />
                <div className="composer-foot">
                  <span className="meta">已粘贴 {text.length} 字</span>
                  <span className="meta">·</span>
                  <span className="meta">
                    {text.trim() ? `规则库 ${RULE_COUNT} 条` : "没内容？回车用示例跑一遍"}
                  </span>
                  <div className="spacer" />
                  <button className="btn btn-primary" disabled={!!busy} onClick={onCheck}>
                    {busy === "analyze" ? `检查中… ${elapsed}s` : "开始检查"} <Icon name="arrow" size={14} />
                  </button>
                </div>
              </div>

              <div className="alt-entry">
                <span>还没有文案？</span>
                <button className="btn btn-ghost" onClick={() => setMode("write")} disabled={!!busy}>
                  生成一版 <Icon name="arrow" size={14} />
                </button>
              </div>

              {error && <p className="error-text">{error}</p>}

              <div className="recent">
                <div className="recent-head">
                  <h2>最近</h2>
                  <button className="btn btn-text btn-sm" onClick={() => router.push("/history")}>
                    查看全部 <Icon name="arrow" size={12} />
                  </button>
                </div>
                {!recent && <p className="meta">加载中…</p>}
                {recent && recent.length === 0 && <p className="meta">还没有记录，查一条试试</p>}
                {(recent || []).slice(0, 5).map((r) => (
                  <div className="recent-row" key={r.id} onClick={() => openEvent(r.id)}>
                    <span className="t">{r.title || "（无标题）"}</span>
                    <span className={`n${r.count ? "" : " clean"}`}>
                      {r.count ? `${r.count} 处问题` : "未发现问题"}
                    </span>
                    <span className="d">{String(r.createdAt || "").replace("T", " ").slice(5, 16)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      <StatusBar />
    </div>
  );
}
