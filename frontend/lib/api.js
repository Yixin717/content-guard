/* 数据层：默认走 mock，环境变量一换就接真实 FastAPI。
   所有页面只依赖这里导出的函数，切换后端不改 UI 代码。 */

import {
  DRAFTS,
  RULES,
  SAMPLE_BAD,
  SAMPLE_CLEAN,
  RECENT,
} from "./mock";
import { ownerId } from "./owner";

export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== "0";
// 注意用 ??：部署到同一域名下时要传空字符串走相对路径（经 Nginx 反代）
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE !== undefined
    ? process.env.NEXT_PUBLIC_API_BASE
    : "http://127.0.0.1:8000";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function request(path, { method = "GET", body } = {}) {
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  // 匿名设备号：后端据此隔离记录，没有登录也能"各看各的"
  const owner = ownerId();
  if (owner) headers["X-Owner-Id"] = owner;
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail = (data && data.detail) || `HTTP ${res.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

/* 数据层归一化：UI 只消费这里吐出来的形状，不直接读后端字段（ADR-006）。 */

/* 一处违规 = 一条改动（ADR-009）。后端给 start/end；mock 没有，就按 after 在文中定位。 */
function normalizeChange(c, i, text) {
  const after = c.after || "";
  let start = typeof c.start === "number" ? c.start : -1;
  let end = typeof c.end === "number" ? c.end : -1;
  if (start < 0 && after && text) {
    const idx = text.indexOf(after);
    if (idx >= 0) {
      start = idx;
      end = idx + after.length;
    }
  }
  return {
    n: c.n ?? i + 1,
    rule_id: c.rule_id || "",
    rule_title: c.rule_title || "",
    before: c.before || "",
    after,
    reason: c.reason || "",
    status: c.status || (after ? "fixed" : "unresolved"),
    start,
    end,
  };
}

function normalizeRewrite(rw, text) {
  if (!rw) return null;
  const rewritten = rw.script ?? rw.text ?? "";
  return {
    title: rw.title || "",
    text: rewritten,
    changes: (rw.changes || []).map((c, i) => normalizeChange(c, i, rewritten)),
    rounds: rw.rounds || 1,
    unresolved: rw.unresolved ?? 0,
    usage: rw.usage || null,
  };
}

function normalizeDraft(d, i) {
  return {
    ...d,
    n: d.n ?? i + 1,
    script: d.script ?? d.text ?? "",
    rule_id: d.rule_id || "",
    rule_title: d.rule_title || "",
    clause: d.clause || "",
    source_url: d.source_url || "",
    severity: d.severity || "medium",
    confidence: d.confidence ?? 0,
  };
}

function normalizeAnalyze(res) {
  const script = res.script || "";
  return {
    draftId: res.draft_id || null,
    title: res.title || "",
    script,
    violations: (res.violations || []).map(normalizeDraft),
    uncertain: (res.uncertain || []).map(normalizeDraft),
    suspected: res.suspected || [],
    humanReview: !!res.human_review,
    reason: res.reason || "",
    rewrite: normalizeRewrite(res.rewrite, script),
    rewriteError: res.rewrite_error || null,
    usage: res.usage || null,
  };
}

/* ---------- 生成 ---------- */
export async function generate(brief, tone) {
  if (!USE_MOCK) {
    const data = await request("/api/generate", {
      method: "POST",
      body: { brief, tone, platform: "xiaohongshu" },
    });
    return { drafts: data.drafts || [], usage: data.usage || null };
  }
  await sleep(900);
  return { drafts: DRAFTS, usage: null };
}

/* ---------- 检查 + 改写（一次算完）----------
   ADR-009：页面只发这一个请求，服务端内部检查→改写→复检，
   这样"检查出几处"和"改动几处"必然一致。 */
export async function analyze(content) {
  if (!USE_MOCK) {
    return normalizeAnalyze(await request("/api/analyze", { method: "POST", body: { content } }));
  }
  await sleep(900);
  const risky = /全网最低|国家级|根治|加V|最好的|第一/.test(content || "");
  const sample = risky ? SAMPLE_BAD : SAMPLE_CLEAN;
  return normalizeAnalyze({
    draft_id: risky ? "d_mock_bad" : "d_mock_clean",
    script: content,
    violations: sample.violations || [],
    uncertain: [],
    suspected: [],
    human_review: false,
    reason: "",
    rewrite: sample.rewrite
      ? {
          ...sample.rewrite,
          before_violations: sample.violations?.length || 0,
          after_violations: 0,
          remaining: 0,
          violation_reduction: 1,
        }
      : null,
    usage: null,
  });
}

/* ---------- 确认 ---------- */
export async function confirm(draftId, finalContent) {
  if (!USE_MOCK) {
    return request("/api/confirm", {
      method: "POST",
      body: { draft_id: draftId, final_content: finalContent, reviewer: "yixin" },
    });
  }
  await sleep(300);
  return { ok: true, audit_id: Date.now() % 10000, idempotent: false };
}

/* ---------- 历史 ----------
   查过就算一条记录，按匿名设备号隔离（ADR-010）。
   mock 模式下也优先读真实接口：后端没启动才退回样例，避免页面空白。 */
function normalizeEvent(it) {
  return {
    id: it.id,
    draftId: it.draft_id || null,
    title: it.title || "",
    count: it.violation_count ?? 0,
    remaining: it.remaining_count ?? 0,
    status: it.status || "checked",
    createdAt: it.created_at || "",
  };
}

export async function history() {
  const fetchItems = async () => (await request("/api/history?limit=20")).items.map(normalizeEvent);
  if (!USE_MOCK) return fetchItems();
  try {
    return await fetchItems();
  } catch {
    /* 后端未启动，用样例 */
  }
  await sleep(200);
  return RECENT.map((r, i) => ({
    id: 1000 + i,
    draftId: `d_mock_${i}`,
    title: r.title,
    count: r.n,
    remaining: 0,
    status: "checked",
    createdAt: r.date,
  }));
}

/* 点开一条历史：拿回当次的分析快照，直接恢复工作台 */
export async function getEvent(id) {
  if (!USE_MOCK) {
    const data = await request(`/api/events/${id}`);
    return { ...data, analyze: normalizeAnalyze(data.result || {}) };
  }
  await sleep(200);
  const sample = SAMPLE_BAD;
  return {
    id,
    title: sample.title,
    status: "checked",
    created_at: "",
    analyze: normalizeAnalyze({
      draft_id: "d_mock_bad",
      script: sample.text,
      violations: sample.violations,
      rewrite: sample.rewrite
        ? { ...sample.rewrite, before_violations: sample.violations.length, after_violations: 0 }
        : null,
    }),
  };
}

/* ---------- 规则 ---------- */
export async function rules() {
  if (!USE_MOCK) return (await request("/api/rules")).items;
  try {
    return (await request("/api/rules")).items;
  } catch {
    /* 后端未启动，用样例（只有 7 条，用于看样式） */
  }
  await sleep(150);
  return RULES;
}

export { RULE_COUNT } from "./mock";
