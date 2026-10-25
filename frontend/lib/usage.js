/* 本次任务的真实消耗。
   来源只有后端 usage 字段——前端不许自己编数字（B-008）。
   一个任务可能跨多个请求（检查 → 改写），这里负责相加。 */

export const EMPTY_USAGE = {
  tokens_in: 0,
  tokens_out: 0,
  latency_ms: 0,
  elapsed_ms: 0,
  attempts: 0,
};

export function sumUsage(...usages) {
  const total = { ...EMPTY_USAGE };
  for (const u of usages) {
    if (!u) continue;
    for (const k of Object.keys(total)) total[k] += Number(u[k] || 0);
  }
  return total;
}

export function hasUsage(usage) {
  return !!usage && (usage.tokens_in > 0 || usage.tokens_out > 0 || usage.elapsed_ms > 0);
}
