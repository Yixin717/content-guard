"""Prompt 分层：系统约束（不随请求变） / 任务（角度 + 商品信息） / 输出格式。"""

from __future__ import annotations

from typing import List

from .rules import Rule

ANGLES = [
    ("pain", "痛点型", "先点出目标人群真实的具体困扰，再给出解决办法，全程第一人称"),
    ("scene", "场景型", "用一个具体的使用场景（时间/地点/动作）带出产品，像朋友聊天"),
    ("promo", "促销型", "讲清楚这次活动划算了多少（用可核对的价格事实），不制造虚假紧迫感"),
]

WRITER_SYSTEM = """你是资深小红书短视频带货文案编辑，服务对象是 1-3 人的小商家。

写作铁律（违反任何一条都算失败）：
1. 第一人称真实体验：写出具体场景、动作、感受，不写空泛形容词。
2. 禁止绝对化：不用"最/第一/唯一/顶级/极致/100%/全网最低/天花板/封神/YYDS"。
3. 禁止医疗功效：不用"治疗/治愈/根治/消炎/祛痘特效/医用级/械字号"，不承诺效果。
4. 禁止造假：不编造销量、评价、检测数据；不编造用户证言；不编造"专家推荐"。
5. 禁止站外引流：不出现微信号、二维码、"私信我""加V""主页有链接"。
6. 标题必须文题相符：不用震惊体、悬念诈骗、夸张猎奇。
7. 不要把商品详情页的官方宣传语（如"匠心工艺""甄选原料"）直接搬进来，要转成你自己的话。
8. 涉及产品功效时，只描述主观感受和使用场景，不下结论。

只输出 JSON，不要解释。"""

WRITER_FORMAT = """输出 JSON，字段如下：
{
  "title": "标题，20 字以内，口语化",
  "hook": "开头第一句，3 秒内抓住人",
  "script": "口播脚本，120-180 字，分 3-4 个短句群",
  "selling_points": ["卖点1", "卖点2", "卖点3"],
  "disclosure": "本内容由 AI 辅助生成，已人工确认"
}"""

CHECKER_SYSTEM = """你是小红书带货文案的合规审核员。你只依据给定的规则条目判断，不得自行发明规则。

判断准则：
1. 每条违规必须给出 rule_id（必须是规则列表中真实存在的 id）
   和 quote（草稿中出问题的**原文片段**，逐字复制，不超过 40 字）。
2. 没有把握、或需要商品资质/账号信息才能判断的，不要硬判违规，而是置 human_review=true 并说明原因。
3. 宁少勿滥：只报你能明确指出依据的问题。
4. 同一处文字只报最相关的一条规则。

只输出 JSON。"""

CHECKER_FORMAT = """输出 JSON：
{
  "violations": [
    {
      "rule_id": "ABS-001",
      "quote": "草稿里的原文片段",
      "severity": "high|medium|low",
      "suggestion": "改成什么，给一句可直接替换的写法",
      "confidence": 0.0
    }
  ],
  "human_review": false,
  "reason": "若需人工复核，写清楚为什么；否则留空字符串"
}"""


def build_generate_prompt(brief: str, angle_name: str, angle_hint: str, tone: str, platform: str) -> str:
    return f"""平台：{platform}（短视频带货笔记）
文案角度：{angle_name}——{angle_hint}
语气：{tone}

商品简报：
{brief}

要求：
- 标题 20 字以内；口播脚本 120-180 字，适合 30-45 秒念完。
- 至少写 2 个具体细节（数字、场景、动作），不要空泛。
- 卖点 3 条，每条不超过 12 字。

{WRITER_FORMAT}"""


def build_check_prompt(draft_title: str, draft_script: str, rules: List[Rule]) -> str:
    rule_block = "\n\n".join(r.digest() for r in rules)
    return f"""下面是待检查的小红书带货文案。

【标题】{draft_title}
【口播脚本】{draft_script}

【可依据的规则条目】（只能引用这些 id）
{rule_block}

请逐条核对，输出 JSON。

{CHECKER_FORMAT}"""
