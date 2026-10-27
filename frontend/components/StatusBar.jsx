import Link from "next/link";
import { RULE_COUNT } from "@/lib/mock";
import { hasUsage } from "@/lib/usage";

const fmt = (n) => Number(n || 0).toLocaleString("en-US");

/* 状态条只显示后端真实返回的 usage（B-008）。
   没有数字就不显示这一段，绝不拿写死的样例值凑数。
   也不显示模型名与规则分档：前者是内部实现，后者写死了会过期。 */
export default function StatusBar({ usage }) {
  const real = hasUsage(usage);
  const showTokens = real && (usage.tokens_in > 0 || usage.tokens_out > 0);
  const showElapsed = real && usage.elapsed_ms > 0;

  return (
    <div className="statusbar">
      <Link href="/rules/" className="status-link">规则库 {RULE_COUNT} 条</Link>
      <span className="spacer" />
      {showTokens && (
        <span className="mono hide-sm">
          tokens {fmt(usage.tokens_in)} / {fmt(usage.tokens_out)}
        </span>
      )}
      {showTokens && showElapsed && <span className="dot hide-sm">·</span>}
      {showElapsed && <span className="hide-sm">耗时 {(usage.elapsed_ms / 1000).toFixed(1)}s</span>}
    </div>
  );
}
