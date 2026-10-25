/* 页面间传参：sessionStorage（静态导出下没有服务端，刷新也能保住当前任务） */

export function setJSON(key, value) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {}
}

export function getJSON(key, fallback = null) {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

export const K = {
  check: "cg:check",
  drafts: "cg:drafts",
  picked: "cg:picked",
};
