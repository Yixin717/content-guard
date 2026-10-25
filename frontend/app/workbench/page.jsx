"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Icon from "@/components/Icon";
import StatusBar from "@/components/StatusBar";
import TopBar from "@/components/TopBar";
import { confirm as confirmApi, rewrite as rewriteApi } from "@/lib/api";
import { RULE_COUNT, SAMPLE_BAD, SAMPLE_CLEAN } from "@/lib/mock";
import { K, getJSON } from "@/lib/store";
import { sumUsage } from "@/lib/usage";

const SEVERITY_LABEL = { high: "高危", medium: "中危", low: "低危" };

/* 把 quote 切成可点的高亮片段 */
function segments(text, ranges) {
  const sorted = ranges.filter((r) => r.start >= 0).sort((a, b) => a.start - b.start);
  const out = [];
  let cursor = 0;
  for (const r of sorted) {
    if (r.start < cursor) continue;
    if (r.start > cursor) out.push({ text: text.slice(cursor, r.start) });
    out.push({ text: text.slice(r.start, r.end), ...r });
    cursor = r.end;
  }
  if (cursor < text.length) out.push({ text: text.slice(cursor) });
  return out;
}

function buildSample() {
  if (typeof window === "undefined") return SAMPLE_BAD;

  const picked = getJSON(K.picked);
  if (picked) {
    return {
      title: picked.title,
      text: picked.script || picked.text || "",
      violations: picked.violations || [],
      rewrite: picked.rewrite || null,
      draftId: picked.id,
      // 生成入口：这一步的消耗来自 /api/generate（含自检与自动改写）
      usage: getJSON(K.genUsage),
    };
  }

  const stored = getJSON(K.check);
  if (stored) {
    const r = stored.result || {};
    return {
      title: "",
      text: stored.text,
      violations: (r.violations || []).map((v, i) => ({ ...v, n: i + 1 })),
      rewrite: r.rewrite || null,
      draftId: r.draft_id,
      humanReview: r.human_review,
      reason: r.reason,
      // 检查入口：这一步的消耗来自 /api/check
      usage: r.usage || null,
    };
  }

  const params = new URLSearchParams(window.location.search);
  const sample = params.get("sample") === "clean" ? SAMPLE_CLEAN : SAMPLE_BAD;
  return { ...sample, usage: null };
}

export default function WorkbenchPage() {
  const router = useRouter();
  const [sample, setSample] = useState(null);
  const [stage, setStage] = useState("checked");
  const [activeN, setActiveN] = useState(1);
  const [expanded, setExpanded] = useState(1);
  const [banner, setBanner] = useState("");
  // 状态条显示的必须是真实消耗：入口那一步 + 这里的改写，没有就不显示
  const [usage, setUsage] = useState(null);

  useEffect(() => {
    const s = buildSample();
    const base = s.usage || null;
    setSample(s);
    setActiveN(1);
    setExpanded(1);
    if (s.violations && s.violations.length > 0 && !s.rewrite) {
      setStage("rewriting");
      rewriteApi(s.draftId)
        .then((rw) => {
          setSample((prev) => ({ ...prev, rewrite: rw }));
          setUsage(sumUsage(base, rw?.usage));
          setStage("rewritten");
        })
        .catch(() => {
          setUsage(base);
          setStage("checked");
        });
    } else if (s.rewrite) {
      setUsage(sumUsage(base, s.rewrite.usage));
      setStage("rewritten");
    } else {
      setUsage(base);
    }
  }, []);

  const ranges = useMemo(
    () =>
      (sample?.violations || [])
        .map((v) => {
          const start = sample.text.indexOf(v.quote);
          return { start, end: start + (v.quote || "").length, n: v.n, severity: v.severity };
        })
        .filter((r) => r.start >= 0),
    [sample]
  );

  async function onConfirm() {
    if (!sample?.draftId) return;
    try {
      const res = await confirmApi(sample.draftId, sample.rewrite?.text || sample.text);
      setBanner(`已确认并记录，审计编号 #${res.audit_id}`);
    } catch (e) {
      setBanner(e.message || "确认失败");
    }
  }

  if (!sample) return null;

  const violations = sample.violations || [];
  const rw = sample.rewrite;
  const rwText = rw?.text || "";
  const rwChanges = rw?.changes || [];
  const canConfirm = stage === "rewritten" || violations.length === 0;

  return (
    <div className="app">
      <TopBar
        stage={stage === "rewriting" ? "checked" : stage}
        canConfirm={canConfirm}
        onConfirm={onConfirm}
        onBack={() => router.push("/")}
      />

      <div className="main">
        {banner && (
          <div className="banner">
            <Icon name="check" size={13} /> {banner}
            <button className="btn btn-text btn-sm" onClick={() => setBanner("")}>
              知道了
            </button>
          </div>
        )}

        <div className="workbench">
          {/* 左：原文 */}
          <div className="col">
            <div className="col-head">
              <h3>原文</h3>
              <span className="count">{sample.text.length} 字</span>
              <div className="spacer" />
              <span className="count">
                {violations.length ? `${violations.length} 处标记` : "无标记"}
              </span>
            </div>
            <div className="doc">
              {sample.title && <div className="title">{sample.title}</div>}
              <p>
                {segments(sample.text, ranges).map((p, i) =>
                  p.n ? (
                    <span
                      key={i}
                      className={`hl hl-${p.severity}${p.n === activeN ? " active" : ""}`}
                      onClick={() => {
                        setActiveN(p.n);
                        setExpanded(p.n);
                      }}
                    >
                      {p.text}
                      <span className={`num ${p.severity}`}>{p.n}</span>
                    </span>
                  ) : (
                    <span key={i}>{p.text}</span>
                  )
                )}
              </p>
            </div>
          </div>

          {/* 中：诊断 */}
          <div className="col">
            <div className="col-head">
              <h3>诊断</h3>
              <span className="count">
                {violations.length} 处
                {violations.length > 0 &&
                  ` · 高危 ${violations.filter((v) => v.severity === "high").length}`}
              </span>
            </div>

            {violations.length === 0 ? (
              <div className="coverage">
                <div className="ok">
                  <Icon name="check" /> 已核 {RULE_COUNT} 条规则，未发现明确违规
                </div>
                <div className="label" style={{ marginBottom: 6 }}>仍需人工确认</div>
                <ul>
                  {(sample.coverage?.manual || [
                    "商品资质：材质与成分是否与描述相符",
                    "账号报备：是否已走品牌合作报备",
                    "图片与视频：本次仅检查文本",
                  ]).map((m) => (
                    <li key={m}>{m}</li>
                  ))}
                </ul>
                <p className="note">
                  “未检出”不等于“可以发”。平台还会结合账号历史、图片与视频做判断，本工具只检查文本。
                </p>
              </div>
            ) : (
              <div className="cards">
                {violations.map((v) => (
                  <div
                    key={v.n}
                    className={`card${v.n === activeN ? " active" : ""}`}
                    onClick={() => {
                      setActiveN(v.n);
                      setExpanded(v.n);
                    }}
                  >
                    <div className="card-top">
                      <span className={`pill pill-${v.severity}`}>{SEVERITY_LABEL[v.severity]}</span>
                      <span className="rule-id mono">{v.rule_id}</span>
                      <div className="spacer" />
                      <span className="rule-id mono">{Number(v.confidence || 0).toFixed(2)}</span>
                    </div>
                    <h4>{v.rule_title}</h4>
                    <p className="quote">“{v.quote}”</p>
                    <div className="source">
                      {v.source}
                      <span style={{ color: "rgba(0,0,0,.2)" }}>·</span>
                      <span style={{ color: "var(--blue)" }}>看条款</span>
                    </div>

                    {expanded === v.n && (
                      <div className="expand">
                        <div className="label">条款原文</div>
                        <div className="clause">{v.clause}</div>
                        <div className="label">建议改法</div>
                        <div className="suggest">{v.suggestion}</div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 右：改写 */}
          <div className="col">
            <div className="col-head">
              <h3>改写</h3>
              <span className="count">
                {stage === "rewriting"
                  ? "改写中…"
                  : rw
                  ? `下降 100% · ${rw.rounds || 1} 轮`
                  : "待改写"}
              </span>
            </div>

            <div className="panel-pad">
              {violations.length === 0 ? (
                <div className="summary">
                  <div className="big">可以发布</div>
                  <div className="hint">
                    文本层面未发现问题。发布前请自行确认商品资质、账号报备，若内容由 AI 辅助生成，记得标注「AI 生成」。
                  </div>
                  <div className="row">
                    <button className="btn btn-ghost btn-sm">
                      <Icon name="copy" size={14} /> 复制正文
                    </button>
                  </div>
                </div>
              ) : stage === "rewriting" ? (
                <div className="summary">
                  <div className="big">正在改写 {violations.length} 处…</div>
                  <div className="hint">保留价格、规格等事实信息，只改违规表达，改完自动复检。</div>
                  <div className="skeleton">
                    <span /><span /><span /><span />
                  </div>
                </div>
              ) : rw ? (
                <>
                  <div className="result-bar">
                    <Icon name="check" size={14} /> 复检通过：{rwChanges.length} 处已修，剩余 0 处
                  </div>
                  <div className="rewrite-text">
                    {rw.title && <div className="title">{rw.title}</div>}
                    <p>
                      {segments(
                        rwText,
                        (rw.changes || [])
                          .map((c) => {
                            const start = rwText.indexOf(c.after);
                            return { start, end: start + c.after.length, n: c.n, severity: "medium" };
                          })
                          .filter((r) => r.start >= 0)
                      ).map((p, i) =>
                        p.n ? (
                          <span key={i} className="add">{p.text}</span>
                        ) : (
                          <span key={i}>{p.text}</span>
                        )
                      )}
                    </p>
                  </div>

                  <div className="changes">
                    <div className="label" style={{ marginBottom: 8 }}>改动明细</div>
                    {rwChanges.map((c) => (
                      <div className="change" key={c.n}>
                        <span className="idx">{c.n}</span>
                        <div>
                          <span className="del">{c.before}</span>
                          <span className="arrow">→</span>
                          <span className="ins">{c.after}</span>
                          <div style={{ color: "var(--ink-40)", fontSize: 12, marginTop: 2 }}>
                            {c.reason}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      <StatusBar usage={usage} />
    </div>
  );
}
