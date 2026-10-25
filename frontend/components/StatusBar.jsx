import { RULE_COUNT } from "@/lib/mock";
import { hasUsage } from "@/lib/usage";

const fmt = (n) => Number(n || 0).toLocaleString("en-US");

/* 状态条只显示后端真实返回的 usage（B-008）。
   没有数字就不显示这一段，绝不拿写死的样例值凑数。 */
export default function StatusBar({ usage }) {
  const real = hasUsage(usage);
  const showTokens = real && (usage.tokens_in > 0 || usage.tokens_out > 0);
  const showElapsed = real && usage.elapsed_ms > 0;

  return (
    <div className="statusbar">
      <span>规则库 {RULE_COUNT} 条</span>
      <span className="dot hide-sm">·</span>
      <span className="hide-sm">法条核验 20 / 平台官方 19 / 待补 1</span>
      <span className="spacer" />
      {showTokens && (
        <>
          <span className="mono hide-sm">
            tokens {fmt(usage.tokens_in)} / {fmt(usage.tokens_out)}
          </span>
          <span className="dot hide-sm">·</span>
        </>
      )}
      {showElapsed && (
        <>
          <span className="hide-sm">耗时 {(usage.elapsed_ms / 1000).toFixed(1)}s</span>
          <span className="dot hide-sm">·</span>
        </>
      )}
      <span>deepseek-chat</span>
    </div>
  );
}
