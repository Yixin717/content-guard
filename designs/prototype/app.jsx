/* Content Guard 原型 —— 入口页 + 三栏工作台
   交互：点编号 / 卡片 / 下划线三栏联动；卡片可展开条款；一键改写（模拟 900ms）*/

const { useState, useEffect, useMemo } = React;

/* ---------- 图标（Lucide 内联，1.5px 线宽） ---------- */
function Icon({ name, size = 15, className = "" }) {
  const paths = {
    check: <path d="M20 6 9 17l-5-5" />,
    alert: (
      <>
        <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
        <path d="M12 9v4" />
        <path d="M12 17h.01" />
      </>
    ),
    minus: <path d="M5 12h14" />,
    chevron: <path d="m9 18 6-6-6-6" />,
    back: <path d="m15 18-6-6 6-6" />,
    arrow: (
      <>
        <path d="M5 12h14" />
        <path d="m12 5 7 7-7 7" />
      </>
    ),
    copy: (
      <>
        <rect x="9" y="9" width="12" height="12" rx="2" />
        <path d="M5 15V5a2 2 0 0 1 2-2h10" />
      </>
    ),
    download: (
      <>
        <path d="M12 15V3" />
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <path d="m7 10 5 5 5-5" />
      </>
    ),
    edit: (
      <>
        <path d="M12 20h9" />
        <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

/* ---------- 文本切分：把 quote 变成可点的高亮片段 ---------- */
function segments(text, ranges) {
  const sorted = ranges.filter((r) => r.start >= 0).sort((a, b) => a.start - b.start);
  const out = [];
  let cursor = 0;
  for (const r of sorted) {
    if (r.start < cursor) continue; // 重叠的跳过
    if (r.start > cursor) out.push({ text: text.slice(cursor, r.start) });
    out.push({ text: text.slice(r.start, r.end), ...r });
    cursor = r.end;
  }
  if (cursor < text.length) out.push({ text: text.slice(cursor) });
  return out;
}

function highlightRanges(text, violations) {
  return violations
    .map((v) => {
      const start = text.indexOf(v.quote);
      return { start, end: start + v.quote.length, n: v.n, severity: v.severity };
    })
    .filter((r) => r.start >= 0);
}

/* ---------- 顶栏 ---------- */
function TopBar({ stage, canConfirm, onBack }) {
  const steps =
    stage === "entry"
      ? ["粘贴"]
      : stage === "checked"
      ? ["原文", "检查", "改写"]
      : ["原文", "检查", "改写", "确认"];
  const current = stage === "entry" ? 0 : stage === "checked" ? 1 : stage === "rewritten" ? 3 : 2;

  return (
    <div className="topbar">
      {onBack && (
        <button className="btn btn-text btn-sm" onClick={onBack} title="返回入口">
          <Icon name="back" />
        </button>
      )}
      <span className="brand">Content Guard</span>
      <div className="steps">
        {steps.map((s, i) => (
          <span key={s} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            {i > 0 && <span className="sep">›</span>}
            <span className={i === current ? "on" : ""}>{s}</span>
          </span>
        ))}
      </div>
      <div className="spacer" />
      {stage !== "entry" && (
        <>
          <button className="btn btn-text btn-sm" title="回到原文编辑">
            <Icon name="edit" /> 编辑原文
          </button>
          <button className="btn btn-primary btn-sm" disabled={!canConfirm}>
            <Icon name="download" /> 确认并导出
          </button>
        </>
      )}
    </div>
  );
}

/* ---------- 入口页 ---------- */
function Entry({ onStart }) {
  const [text, setText] = useState(
    "姐妹们，这条裤子全网最低价！三天根治大腿根的痘印，国家级品质，加V领福利。我自己穿了三个月，洗完不皱，垂感一直在。69 两条，周末截止。"
  );
  const empty = text.trim().length === 0;

  return (
    <div className="entry-wrap">
      <div className="entry">
        <h1>发布前，先过一遍</h1>
        <p className="sub">把要发的小红书文案贴进来，我告诉你哪一句会出事、违反哪一条，并给出改好的版本。</p>

        <div className="composer">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="粘贴你的标题 + 口播脚本（也可以只贴一段）"
          />
          <div className="composer-foot">
            <span className="meta">已粘贴 {text.length} 字</span>
            <span className="meta">·</span>
            <span className="meta">规则库 {RULE_COUNT} 条</span>
            <div className="spacer" />
            <button className="btn btn-primary" disabled={empty} onClick={() => onStart("bad")}>
              开始检查 <Icon name="arrow" size={14} />
            </button>
          </div>
        </div>

        <p className="alt-entry">
          还没有文案？<a onClick={() => onStart("clean")}>让 AI 先写一版 →</a>
        </p>

        <div className="recent">
          <h2>最近</h2>
          {RECENT.map((r) => (
            <div className="recent-row" key={r.title} onClick={() => onStart(r.n ? "bad" : "clean")}>
              <span className="t">{r.title}</span>
              <span className="n" style={r.n ? undefined : { color: "var(--ink-40)" }}>
                {r.n ? `${r.n} 处问题` : "通过"}
              </span>
              <span className="d">{r.date}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ---------- 左栏：原文 ---------- */
function SourceColumn({ sample, activeN, onPick }) {
  const ranges = highlightRanges(sample.text, sample.violations);
  const parts = segments(sample.text, ranges);

  return (
    <div className="col">
      <div className="col-head">
        <h3>原文</h3>
        <span className="count">{sample.text.length} 字</span>
        <div className="spacer" />
        <span className="count">{sample.violations.length ? `${sample.violations.length} 处标记` : "无标记"}</span>
      </div>
      <div className="doc">
        <div className="title">{sample.title}</div>
        <p>
          {parts.map((p, i) =>
            p.n ? (
              <span
                key={i}
                className={`hl hl-${p.severity}${p.n === activeN ? " active" : ""}`}
                onClick={() => onPick(p.n)}
              >
                {p.text}
                <span className={`num ${p.severity}`}>{p.n}</span>
              </span>
            ) : (
              <React.Fragment key={i}>{p.text}</React.Fragment>
            )
          )}
        </p>
      </div>
    </div>
  );
}

/* ---------- 中栏：诊断 ---------- */
function DiagnosisColumn({ sample, activeN, onPick }) {
  const [expanded, setExpanded] = useState(activeN || sample.violations[0]?.n || null);
  const v = sample.violations;

  useEffect(() => {
    if (activeN) setExpanded(activeN);
  }, [activeN]);

  if (!v.length) {
    return (
      <div className="col">
        <div className="col-head">
          <h3>诊断</h3>
          <span className="count">0 处</span>
        </div>
        <div className="coverage">
          <div className="ok">
            <Icon name="check" /> 已核 {sample.coverage.rules} 条规则，未发现明确违规
          </div>
          <div className="label" style={{ marginBottom: 6 }}>仍需人工确认</div>
          <ul>
            {sample.coverage.manual.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
          <p className="note">
            “未检出”不等于“可以发”。平台还会结合账号历史、图片与视频做判断，本工具只检查文本。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="col">
      <div className="col-head">
        <h3>诊断</h3>
        <span className="count">
          {v.length} 处 · 高危 {v.filter((x) => x.severity === "high").length}
        </span>
      </div>
      <div className="cards">
        {v.map((item) => (
          <div
            key={item.n}
            className={`card${item.n === activeN ? " active" : ""}`}
            onClick={() => {
              onPick(item.n);
              setExpanded(item.n);
            }}
          >
            <div className="card-top">
              <span className={`pill pill-${item.severity}`}>
                {item.severity === "high" ? "高危" : item.severity === "medium" ? "中危" : "低危"}
              </span>
              <span className="rule-id mono">{item.rule_id}</span>
              <div className="spacer" style={{ flex: 1 }} />
              <span className="rule-id mono">{item.confidence.toFixed(2)}</span>
            </div>
            <h4>{item.rule_title}</h4>
            <p className="quote">“{item.quote}”</p>
            <div className="source">
              {item.source}
              <span style={{ color: "rgba(0,0,0,.2)" }}>·</span>
              <span style={{ color: "var(--blue)" }}>看条款</span>
            </div>

            {expanded === item.n && (
              <div className="expand">
                <div className="label">条款原文</div>
                <div className="clause">{item.clause}</div>
                <div className="label">建议改法</div>
                <div className="suggest">{item.suggestion}</div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------- 右栏：改写 ---------- */
function RewriteColumn({ sample, stage, onRewrite }) {
  const loading = stage === "rewriting";
  const done = stage === "rewritten";

  if (!sample.violations.length) {
    return (
      <div className="col">
        <div className="col-head">
          <h3>改写</h3>
        </div>
        <div className="panel-pad">
          <div className="summary">
            <div className="big">可以发布</div>
            <div className="hint">
              文本层面未发现问题。发布前请自行确认商品资质、账号报备，若内容由 AI 辅助生成，记得标注「AI 生成」。
            </div>
            <div className="row">
              <button className="btn btn-ghost btn-sm"><Icon name="copy" size={14} /> 复制正文</button>
              <button className="btn btn-text btn-sm">再检查一次</button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const rw = sample.rewrite;

  return (
    <div className="col">
      <div className="col-head">
        <h3>改写</h3>
        <span className="count">{done ? `下降 100% · ${rw.rounds} 轮` : loading ? "改写中…" : "待改写"}</span>
      </div>
      <div className="panel-pad">
        {loading ? (
          <div className="summary">
            <div className="big">正在改写 {sample.violations.length} 处…</div>
            <div className="hint">保留价格、规格等事实信息，只改违规表达，改完自动复检。</div>
            <div className="skeleton">
              <span /><span /><span /><span />
            </div>
          </div>
        ) : (
          <>
            <div className="result-bar">
              <Icon name="check" size={14} /> 复检通过：{rw.changes.length} 处已修，剩余 0 处
              <span style={{ flex: 1 }} />
              <button className="btn btn-text btn-sm" style={{ color: "var(--blue)" }} onClick={onRewrite}>
                重新改写
              </button>
            </div>
            <div className="rewrite-text">
              <div className="title">
                {segments(rw.title, highlightRanges(rw.title, [])).map((p, i) => (
                  <span key={i}>{p.text}</span>
                ))}
              </div>
              <p>
                {segments(
                  rw.text,
                  rw.changes
                    .map((c) => {
                      const start = rw.text.indexOf(c.after);
                      return { start, end: start + c.after.length, n: c.n, severity: "medium" };
                    })
                    .filter((r) => r.start >= 0)
                ).map((p, i) =>
                  p.n ? (
                    <span key={i} className="add" title={`改动 ${p.n}`}>
                      {p.text}
                    </span>
                  ) : (
                    <React.Fragment key={i}>{p.text}</React.Fragment>
                  )
                )}
              </p>
            </div>

            <div className="changes">
              <div className="label" style={{ marginBottom: 8 }}>改动明细</div>
              {rw.changes.map((c) => (
                <div className="change" key={c.n}>
                  <span className="idx">{c.n}</span>
                  <div>
                    <span className="del">{c.before}</span>
                    <span className="arrow">→</span>
                    <span className="ins">{c.after}</span>
                    <div style={{ color: "var(--ink-40)", fontSize: 12, marginTop: 2 }}>{c.reason}</div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/* ---------- 工作台 ---------- */
function Workbench({ initialSample, initialStage, onBack }) {
  const [sampleKey, setSampleKey] = useState(initialSample || "bad");
  const sample = sampleKey === "bad" ? SAMPLE_BAD : SAMPLE_CLEAN;
  const [stage, setStage] = useState(
    initialStage || (sample.violations.length ? "rewritten" : "checked")
  );
  const [activeN, setActiveN] = useState(1);

  const canConfirm = stage === "rewritten" || !sample.violations.length;

  function startRewrite() {
    setStage("rewriting");
    setTimeout(() => setStage("rewritten"), 900);
  }

  // 首次进入：先显示复查结果，再自动改写（不再让用户多点一次）
  const [booting, setBooting] = useState(!initialStage && sample.violations.length > 0);
  useEffect(() => {
    if (!booting) return;
    const t = setTimeout(() => {
      setStage("rewriting");
      setTimeout(() => { setStage("rewritten"); setBooting(false); }, 800);
    }, 400);
    return () => clearTimeout(t);
  }, [booting]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <TopBar
        stage={stage === "rewriting" ? "checked" : stage}
        canConfirm={canConfirm}
        onBack={onBack}
      />
      {new URLSearchParams(location.search).get("dev") === "1" && (
        <div style={{ display: "flex", gap: 8, padding: "8px 20px", background: "#fff", borderBottom: "1px solid var(--line)" }}>
          <button className="btn btn-text btn-sm" onClick={() => { setSampleKey("bad"); setStage("checked"); setActiveN(1); }}>
            有问题的样本
          </button>
          <button className="btn btn-text btn-sm" onClick={() => { setSampleKey("clean"); setStage("checked"); }}>
            无违规样本
          </button>
        </div>
      )}
      <div className="workbench">
        <SourceColumn sample={sample} activeN={activeN} onPick={setActiveN} />
        <DiagnosisColumn sample={sample} activeN={activeN} onPick={setActiveN} />
        <RewriteColumn sample={sample} stage={stage} onRewrite={startRewrite} />
      </div>
      <StatusBar sample={sample} stage={stage} />
    </div>
  );
}

/* ---------- 底部状态条 ---------- */
function StatusBar({ sample, stage }) {
  return (
    <div className="statusbar">
      <span>规则库 {RULE_COUNT} 条</span>
      <span className="dot">·</span>
      <span>法条核验 20 / 平台官方 19 / 待补 1</span>
      <span className="spacer" />
      {stage === "rewritten" && sample.rewrite ? (
        <>
          <span className="mono">tokens 9,254 / 1,198</span>
          <span className="dot">·</span>
          <span>耗时 15.7s</span>
          <span className="dot">·</span>
        </>
      ) : null}
      <span>deepseek-chat</span>
    </div>
  );
}

/* ---------- 根 ---------- */
function App() {
  const params = new URLSearchParams(location.search);
  const initialView = params.get("view") === "workbench" ? "workbench" : "entry";
  const [view, setView] = useState(initialView);

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      {view === "entry" ? (
        <>
          <TopBar stage="entry" canConfirm={false} />
          <Entry onStart={() => setView("workbench")} />
        </>
      ) : (
        <Workbench
          initialSample={params.get("sample")}
          initialStage={params.get("stage")}
          onBack={() => setView("entry")}
        />
      )}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
