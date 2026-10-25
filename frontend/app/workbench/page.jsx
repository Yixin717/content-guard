"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Icon from "@/components/Icon";
import StatusBar from "@/components/StatusBar";
import TopBar from "@/components/TopBar";
import { confirm as confirmApi } from "@/lib/api";
import { RULE_COUNT, SAMPLE_BAD, SAMPLE_CLEAN } from "@/lib/mock";
import { K, getJSON } from "@/lib/store";

const SEVERITY_LABEL = { high: "高危", medium: "中危", low: "低危" };

/* 把文字按区间切成可高亮的片段：原文用违规区间，改写文用改动区间 */
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
  if (typeof window === "undefined") return { ...SAMPLE_BAD, usage: null, rewriteError: null };

  const picked = getJSON(K.picked);
  if (picked) {
    return {
      title: picked.title,
      text: picked.script || picked.text || "",
      violations: picked.violations || [],
      rewrite: picked.rewrite || null,
      rewriteError: null,
      draftId: picked.id,
      // 生成入口：这一步的消耗来自 /api/generate（含自检与自动改写）
      usage: getJSON(K.genUsage),
    };
  }

  const stored = getJSON(K.check);
  if (stored) {
    const r = stored.result || {};
    return {
      title: r.title || "",
      text: r.script || stored.text || "",
      violations: r.violations || [],
      // 检查与改写是同一次请求算出来的，不会再出现"检查 2 处、改动 3 处"
      rewrite: r.rewrite || null,
      rewriteError: r.rewriteError || null,
      draftId: r.draftId || r.draft_id,
      humanReview: r.humanReview,
      reason: r.reason,
      usage: r.usage || null,
    };
  }

  const params = new URLSearchParams(window.location.search);
  const sample = params.get("sample") === "clean" ? SAMPLE_CLEAN : SAMPLE_BAD;
  return { ...sample, usage: null, rewriteError: null };
}

export default function WorkbenchPage() {
  const router = useRouter();
  const [sample, setSample] = useState(null);
  const [activeN, setActiveN] = useState(1);
  const [banner, setBanner] = useState("");

  useEffect(() => {
    setSample(buildSample());
    setActiveN(1);
  }, []);

  const ranges = useMemo(
    () =>
      (sample?.violations || [])
        .map((v) => {
          const start = (sample.text || "").indexOf(v.quote);
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
  // mock / 旧数据可能缺 status，这里补一次；有 after 就算改好了
  const changes = (rw?.changes || []).map((c, i) => ({
    ...c,
    n: c.n ?? i + 1,
    status: c.status || (c.after ? "fixed" : "unresolved"),
  }));
  const remaining = rw?.remaining ?? 0;
  const unresolvedCount = changes.filter((c) => c.status !== "fixed").length;
  const newHits = Math.max(0, remaining - unresolvedCount);
  const stage = rw ? "rewritten" : "checked";
  const canConfirm = !!rw || violations.length === 0;
  const reduction = rw?.reduction;

  // 后端直接给位置；mock 或缺失时按改写后的文本定位，保证一定标得出来
  const changeRanges = changes
    .map((c) => {
      let { start, end } = c;
      if ((start == null || start < 0) && c.after) {
        const idx = rwText.indexOf(c.after);
        if (idx >= 0) {
          start = idx;
          end = idx + c.after.length;
        }
      }
      return { start, end, n: c.n };
    })
    .filter((r) => r.start >= 0 && r.end > r.start);

  return (
    <div className="app">
      <TopBar
        stage={stage}
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
              <span className="count">{(sample.text || "").length} 字</span>
              <div className="spacer" />
              <span className="count">
                {violations.length ? `${violations.length} 处标记` : "无标记"}
              </span>
            </div>
            <div className="doc">
              {sample.title && <div className="title">{sample.title}</div>}
              <p>
                {segments(sample.text || "", ranges).map((p, i) =>
                  p.n ? (
                    <span
                      key={i}
                      className={`hl hl-${p.severity}${p.n === activeN ? " active" : ""}`}
                      onClick={() => setActiveN(p.n)}
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

          {/* 中：诊断（条款原文直接显示，不再藏在抽屉里） */}
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
                    onClick={() => setActiveN(v.n)}
                  >
                    <div className="card-top">
                      <span className={`pill pill-${v.severity}`}>{SEVERITY_LABEL[v.severity]}</span>
                      <span className="rule-id mono">{v.rule_id}</span>
                      <div className="spacer" />
                      <span className="rule-id mono">{Number(v.confidence || 0).toFixed(2)}</span>
                    </div>
                    <h4>{v.rule_title}</h4>
                    <p className="quote">“{v.quote}”</p>
                    <div className="source">{v.source}</div>

                    <div className="expand">
                      <div className="label">条款原文</div>
                      <div className="clause">
                        {v.clause || "（该条规则暂无可引用的原文，已标注为待补）"}
                      </div>
                      <div className="label">建议改法</div>
                      <div className="suggest">{v.suggestion || "按条款要求去掉该表述"}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 右：改写（改动处蓝字 + 浅蓝底 + 下划线，编号与左栏一致） */}
          <div className="col">
            <div className="col-head">
              <h3>改写</h3>
              <span className="count">
                {rw
                  ? `${reduction != null ? `下降 ${Math.round(reduction * 100)}%` : "已改写"} · ${
                      rw.rounds || 1
                    } 轮`
                  : "待改写"}
              </span>
            </div>

            <div className="panel-pad">
              {violations.length === 0 ? (
                <div className="summary">
                  <div className="big">可以发布</div>
                  <div className="hint">
                    文本层面未发现问题。发布前请自行确认商品资质、账号报备，本工具只检查文本。
                  </div>
                  <div className="row">
                    <button className="btn btn-ghost btn-sm">
                      <Icon name="copy" size={14} /> 复制正文
                    </button>
                  </div>
                </div>
              ) : sample.rewriteError ? (
                <div className="summary">
                  <div className="big">改写没成功</div>
                  <div className="hint">{sample.rewriteError}</div>
                  <div className="row">
                    <button className="btn btn-ghost btn-sm" onClick={() => router.push("/")}>
                      返回重试
                    </button>
                  </div>
                </div>
              ) : rw ? (
                <>
                  <div className="rewrite-text">
                    {rw.title && <div className="title">{rw.title}</div>}
                    <p>
                      {segments(rwText, changeRanges).map((p, i) =>
                        p.n ? (
                          <span key={i} className="add" onClick={() => setActiveN(p.n)}>
                            {p.text}
                            <sup className="add-n">{p.n}</sup>
                          </span>
                        ) : (
                          <span key={i}>{p.text}</span>
                        )
                      )}
                    </p>
                  </div>

                  <div className="changes">
                    <div className="label" style={{ marginBottom: 8 }}>
                      改动明细（{changes.length} 处，与左侧标记一一对应）
                    </div>
                    {changes.map((c) => {
                      const ok = c.status === "fixed";
                      return (
                        <div className={`change${ok ? "" : " unresolved"}`} key={c.n}>
                          <span className="idx">{c.n}</span>
                          <div>
                            <span className="del">{c.before}</span>
                            <span className="arrow">→</span>
                            <span className="ins">{ok ? c.after || "已随其他改动消除" : "未自动改好"}</span>
                            <div className="change-why">
                              {c.reason}
                              {c.rule_id ? ` · ${c.rule_id}` : ""}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                    {unresolvedCount > 0 && (
                      <p className="note" style={{ marginTop: 10 }}>
                        标「未自动改好」的条目需要人工处理——系统不会为了凑数编一条改动出来。
                      </p>
                    )}
                    {newHits > 0 && (
                      <p className="note" style={{ marginTop: 6 }}>
                        复检另有 {newHits} 处命中，不在上面的改动明细里，需人工确认。
                      </p>
                    )}
                  </div>
                </>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      <StatusBar usage={sample.usage} />
    </div>
  );
}
