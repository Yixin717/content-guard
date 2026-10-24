"""生成：一个 brief → 3 个角度各一版草稿（每版一次调用，便于失败重试与按角度调参）。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .llm import LLM
from .prompts import ANGLES, WRITER_SYSTEM, build_generate_prompt


class DraftPayload(BaseModel):
    title: str = Field(min_length=1, max_length=60)
    hook: str = ""
    script: str = Field(min_length=10)
    selling_points: List[str] = Field(default_factory=list)
    disclosure: str = "本内容由 AI 辅助生成，已人工确认"


@dataclass
class Draft:
    id: str
    angle: str
    angle_name: str
    title: str
    hook: str
    script: str
    selling_points: List[str]
    disclosure: str
    usage: Dict[str, int] = field(default_factory=dict)

    def text(self) -> str:
        return f"{self.title}\n{self.hook}\n{self.script}"


def generate_drafts(
    brief: str,
    tone: str = "亲切、像朋友聊天",
    platform: str = "xiaohongshu",
    llm: Optional[LLM] = None,
    angles: Optional[List[str]] = None,
) -> List[Draft]:
    llm = llm or LLM()
    drafts: List[Draft] = []
    for key, name, hint in ANGLES:
        if angles and key not in angles:
            continue
        prompt = build_generate_prompt(brief, name, hint, tone, platform)
        payload, usage = llm.chat_json(WRITER_SYSTEM, prompt, DraftPayload)
        drafts.append(
            Draft(
                id=uuid.uuid4().hex[:8],
                angle=key,
                angle_name=name,
                title=payload.title.strip(),
                hook=payload.hook.strip(),
                script=payload.script.strip(),
                selling_points=[p.strip() for p in payload.selling_points if p.strip()],
                disclosure=payload.disclosure.strip(),
                usage=usage,
            )
        )
    return drafts
