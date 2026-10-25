"use client";

import { useRouter } from "next/navigation";
import Icon from "./Icon";

const STEPS = {
  entry: null,
  drafts: ["生成", "选稿", "检查", "改写"],
  checked: ["原文", "检查", "改写"],
  rewritten: ["原文", "检查", "改写", "确认"],
};

export default function TopBar({ stage = "entry", entryLabel = "粘贴", canConfirm, onConfirm, onBack }) {
  const router = useRouter();
  const steps = stage === "entry" ? [entryLabel] : STEPS[stage] || [];
  const current = stage === "entry" ? 0 : stage === "drafts" ? 1 : stage === "rewritten" ? 3 : 1;
  const showActions = stage !== "entry" && stage !== "drafts";

  return (
    <div className="topbar">
      {onBack && (
        <button className="btn btn-text btn-sm" title="返回" onClick={onBack}>
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
      {showActions && (
        <>
          <button className="btn btn-text btn-sm" onClick={() => router.push("/")}>
            <Icon name="edit" /> 编辑原文
          </button>
          <button className="btn btn-primary btn-sm" disabled={!canConfirm} onClick={onConfirm}>
            <Icon name="download" /> 确认并导出
          </button>
        </>
      )}
    </div>
  );
}
