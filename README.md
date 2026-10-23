# Content Guard · 商家内容合规与生成助手

输入商品卖点 → 生成 3 版小红书短视频带货文案 → 按广告法与平台规则检查 → 每条违规指回条款 → 给出合规改写 → 人工确认后导出。

**为什么做**：1–3 人的小商家团队没有专职合规，通常是「发布后被限流」才发现问题，且平台只说"涉嫌违规"，不说哪句话、违反哪条。这个项目把合规从"发布后检查"前移到"生成时就有护栏"。

**当前状态**：D0（2026-10-23）—— 规则库 v1（31 条）+ 真实性校验脚本已完成，代码尚未开始。

**技术栈**：FastAPI + SQLite + Next.js + Nginx + systemd，部署于腾讯云 CVM；模型 DeepSeek `deepseek-chat`。

## 规则库

`rules.csv` 共 31 条：

| 类别 | 前缀 | 依据 |
|---|---|---|
| 绝对化用语 | `ABS` | 《广告法》第九条 + [《广告绝对化用语执法指南》(2023)](https://www.samr.gov.cn/ggjgs/tzgg/art/2023/art_183b5cb48d9e4f0dba67f9f912a913ba.html) |
| 虚假宣传 / 医疗功效 | `FLM` | 《广告法》第十一、十二、十三、十七、十八、二十五、二十八条 |
| 平台违禁 / 引流 / 诱导 | `PLT` | 小红书社区规范、商家规则、[官方「薯管家」推广规范](docs/sources/xiaohongshu/推广笔记规范-薯管家.md) |

**每条规则都带 `source`（条款号）、`source_url`、`quote`（原文摘录）、`fetched_at`、`status`。**

| 状态 | 条数 | 含义 | 校验方式 |
|---|---|---|---|
| `verified` | 20 | 《广告法》《绝对化用语执法指南》条文 | `quote` 与官方原文逐字比对 |
| `platform_official` | 2 | 平台官方账号发布的规则内容（非规则中心正式条款） | `quote` 与存档原文逐字比对 |
| `platform_pending` | 9 | 小红书规则页前端渲染，未取得可引用原文 | 仅概述，标注待人工截图补录 |

> 平台规则中有一部分（推广占比 ≤20%、不连续两条、模板化内容）**属于账号级指标，单篇文案无法判定**，故意不进检查器，只写进 PRD，避免制造误报。详见 [存档说明](docs/sources/xiaohongshu/README.md)。

### 校验

```bash
python3 scripts/verify_rules.py               # 字段完整性 + id 唯一 + quote 逐字比对
python3 scripts/verify_rules.py --check-urls  # 额外检查来源链接是否 200
```

校验不过即退出码 1。**改一个字都会报红**，这是"规则不是编的"的机器证明。

## 文档

- [14 天执行计划](docs/plan.md)
- [来源存档](docs/sources/)：《广告法》(2021 修正) 条文摘录、《广告绝对化用语执法指南》全文、[小红书推广规范 + 抓取受阻记录](docs/sources/xiaohongshu/README.md)

## 目录

```
rules.csv          规则源（31 条）
scripts/           工具脚本（verify_rules.py）
docs/plan.md       14 天计划
docs/sources/      官方原文存档（引用底本）
backend/           FastAPI 服务、规则引擎、评测脚本（D1 起）
frontend/          Next.js 工作台 / 历史 / 规则页（D5 起）
```
