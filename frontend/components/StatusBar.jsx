import { RULE_COUNT } from "@/lib/mock";

export default function StatusBar({ meta }) {
  return (
    <div className="statusbar">
      <span>规则库 {RULE_COUNT} 条</span>
      <span className="dot hide-sm">·</span>
      <span className="hide-sm">法条核验 20 / 平台官方 19 / 待补 1</span>
      <span className="spacer" />
      {meta && (
        <>
          <span className="mono hide-sm">{meta.tokens || "tokens 9,254 / 1,198"}</span>
          <span className="dot hide-sm">·</span>
          <span className="hide-sm">耗时 {meta.elapsed || "15.7s"}</span>
          <span className="dot hide-sm">·</span>
        </>
      )}
      <span>deepseek-chat</span>
    </div>
  );
}
