/* 数据层：默认走 mock，环境变量一换就接真实 FastAPI。
   所有页面只依赖这里导出的函数，切换后端不改 UI 代码。 */

import {
  DRAFTS,
  RULES,
  SAMPLE_BAD,
  SAMPLE_CLEAN,
  RECENT,
} from "./mock";

export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== "0";
// 注意用 ??：部署到同一域名下时要传空字符串走相对路径（经 Nginx 反代）
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE !== undefined
    ? process.env.NEXT_PUBLIC_API_BASE
    : "http://127.0.0.1:8000";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function request(path, { method = "GET", body } = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
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

/* 把后端返回归一化：后端 rewrite 用 script，mock 用 text；
   以前前端直接读 text，接上真接口就白屏。统一在这里抹平。 */
function normalizeRewrite(rw) {
  if (!rw) return null;
  return {
    title: rw.title || "",
    text: rw.script ?? rw.text ?? "",
    changes: rw.changes || [],
    rounds: rw.rounds || 1,
    before: rw.before_violations,
    after: rw.after_violations,
    // 后端真实消耗；mock 没有，就是 null，不许补一个假数字
    usage: rw.usage || null,
  };
}

function normalizeDraft(d, i) {
  return {
    ...d,
    n: i + 1,
    script: d.script ?? d.text ?? "",
    rule_id: d.rule_id || "",
    rule_title: d.rule_title || "",
    severity: d.severity || "medium",
    confidence: d.confidence ?? 0,
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

/* ---------- 检查 ---------- */
export async function check(content) {
  if (!USE_MOCK) {
    const res = await request("/api/check", { method: "POST", body: { content } });
    return {
      ...res,
      violations: (res.violations || []).map(normalizeDraft),
      rewrite: null,
      usage: res.usage || null,
    };
  }
  await sleep(600);
  const risky = /全网最低|国家级|根治|加V|最好的|第一/.test(content || "");
  return risky ? { ...SAMPLE_BAD, draft_id: "d_mock_bad" } : { ...SAMPLE_CLEAN, draft_id: "d_mock_clean" };
}

/* ---------- 改写 ---------- */
export async function rewrite(draftId) {
  if (!USE_MOCK) {
    return normalizeRewrite(await request("/api/rewrite", { method: "POST", body: { draft_id: draftId } }));
  }
  await sleep(700);
  return SAMPLE_BAD.rewrite;
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
   mock 模式下也优先读真实接口：后端没启动就退回样例数据，避免页面空白 */
export async function history() {
  if (!USE_MOCK) return (await request("/api/history?limit=20")).items;
  try {
    return (await request("/api/history?limit=20")).items;
  } catch {
    /* 后端未启动，用样例 */
  }
  await sleep(200);
  return RECENT.map((r, i) => ({
    audit_id: i + 1,
    draft_id: `d_mock_${i}`,
    title: r.title,
    angle_name: r.n ? "促销型" : "粘贴",
    final_content: r.title,
    reviewer: "yixin",
    created_at: r.date,
  }));
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
