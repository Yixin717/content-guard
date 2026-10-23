# Content Guard · 商家内容合规与生成助手

输入商品卖点 → 生成 3 版小红书短视频带货文案 → 按广告法与平台规则检查 → 每条违规指回条款 → 给出合规改写 → 人工确认后导出。

**为什么做**：1–3 人的小商家团队没有专职合规，通常是「发布后被限流」才发现问题，且平台只说"涉嫌违规"，不说哪句话、违反哪条。这个项目把合规从"发布后检查"前移到"生成时就有护栏"。

**当前状态**：D0（2026-10-23）—— 规则库 v1（30 条）+ 真实性校验脚本已完成，代码尚未开始。

**技术栈**：FastAPI + SQLite + Next.js + Nginx + systemd，部署于腾讯云 CVM；模型 DeepSeek `deepseek-chat`。

## 规则库

`rules.csv` 共 30 条，3 类各 10 条：

| 类别 | 前缀 | 依据 |
|---|---|---|
| 绝对化用语 | `ABS` | 《广告法》第九条 + [《广告绝对化用语执法指南》(2023)](https://www.samr.gov.cn/ggjgs/tzgg/art/2023/art_183b5cb48d9e4f0dba67f9f912a913ba.html) |
| 虚假宣传 / 医疗功效 | `FLM` | 《广告法》第十一、十二、十三、十七、十八、二十五、二十八条 |
| 平台违禁 / 引流 / 诱导 | `PLT` | 小红书社区规范与商家规则 |

**每条规则都带 `source`（条款号）、`source_url`、`quote`（原文摘录）、`fetched_at`、`status`。**

- `status=verified`（20 条）：`quote` 必须与 `docs/sources/` 下的官方原文**逐字一致**
- `status=platform_pending`（10 条）：小红书规则页由前端渲染，暂无法取得可引用原文，标注待人工截图补录

### 校验

```bash
python3 scripts/verify_rules.py               # 字段完整性 + id 唯一 + quote 逐字比对
python3 scripts/verify_rules.py --check-urls  # 额外检查来源链接是否 200
```

校验不过即退出码 1。**改一个字都会报红**，这是"规则不是编的"的机器证明。

## 文档

- [14 天执行计划](docs/plan.md)
- [来源存档](docs/sources/)：《广告法》(2021 修正) 条文摘录、《广告绝对化用语执法指南》全文

## 目录

```
rules.csv          规则源（30 条）
scripts/           工具脚本（verify_rules.py）
docs/plan.md       14 天计划
docs/sources/      官方原文存档（引用底本）
backend/           FastAPI 服务、规则引擎、评测脚本（D1 起）
frontend/          Next.js 工作台 / 历史 / 规则页（D5 起）
```
