# Content Guard · 发布前合规体检

把要发的小红书带货文案贴进来 → 按 40 条可溯源规则逐句检查 → 每条违规指回原句和条款 → 逐条改写 → 人工确认导出。
生成只是次入口：没有文案的人可以先让 AI 写一版，生成结果会先过 40 条规则再给你。

**为什么做**：1–3 人的小商家团队没有专职合规，通常是「发布后被限流」才发现问题，且平台只说"涉嫌违规"，不说哪句话、违反哪条。这个项目把合规判断前移到发布前：先看哪句会出事，再决定发不发。

**线上 Demo**：**http://43.142.12.100/** ｜ **当前状态**：工程 + 评测 + PRD 完成，线上 v1.1 —— 规则库 40 条（逐字可溯源）+ CLI + FastAPI/SQLite + **Next.js 前端**（入口 / 选稿 / 工作台 / 历史 / 规则）。**线上已部署 v1.1、新首屏与规则库入口**；评测报告见 [eval/report-v1.md](eval/report-v1.md)，PRD 见 [docs/PRD.md](docs/PRD.md)（12 页 PDF）。

**技术栈**：FastAPI + SQLite + Next.js + Nginx + systemd，部署于腾讯云 CVM；模型 DeepSeek `deepseek-chat`。

## 快速开始

```bash
# 1) 配置密钥（写入 .env，不会进 git）
bash scripts/init_env.sh

# 2) 后端依赖
cd backend && /usr/bin/python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 3) 跑一条 brief：生成 3 版草稿 + 合规检查
.venv/bin/python -m app.cli "杭州女装小店，冰丝阔腿裤，遮胯显瘦，69 元两条"

# 3b) 有违规时自动改写并复检（最多 2 轮）
.venv/bin/python -m app.cli --check "全网最低价，三天根治痘痘" --rewrite

# 4) 只检查一段现成文案（回归/演示用）
.venv/bin/python -m app.cli --check "全网最低价，三天根治痘痘，加V领福利"

# 5) 起前端（默认跑 mock 数据；接真接口见下）
cd frontend && npm install --cache ./.npm-cache && npm run dev     # http://localhost:3000

# 6) 起 API（Swagger: http://127.0.0.1:8000/docs）
cd backend && .venv/bin/python -m app.db init
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 7) 校验规则真实性 & 跑单测
python3 scripts/verify_rules.py
cd backend && .venv/bin/python -m pytest -q
```

### 部署

线上：http://43.142.12.100/ （腾讯云 CVM + Nginx + systemd + 静态导出）。细节见 [部署记录](docs/deploy.md)。

```bash
HOST=43.142.12.100 bash scripts/deploy.sh   # 一键部署（含备份与健康检查）
```

### 前端

- 技术栈：Next.js 14（App Router，静态导出 `output: export`）+ 纯 CSS 令牌（沿用 `designs/prototype` 的设计稿）。
- 默认 `NEXT_PUBLIC_USE_MOCK=1`：生成/检查/改写走内置样例，接口不通也能看界面。
- 接真接口：`NEXT_PUBLIC_USE_MOCK=0 NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000 npm run dev`。
- 规则页、历史页、首页「最近」**优先读真接口**，后端没起才退回样例。
- 状态条上的 tokens / 耗时**只显示后端 `usage` 返回的真实值**；mock 模式下不显示（不编数字，见 ADR-008）。

```bash
cd frontend
npm run dev      # 开发
npm run build    # 静态导出到 out/，D6 交给 Nginx
```

### API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查（返回模型名与规则条数） |
| POST | `/api/generate` | `{brief, tone?}` → 3 版草稿（含自检与自动改写） |
| POST | `/api/check` | `{draft_id}` 或 `{content}` → 违规 / 待确认 / 疑似（只检查） |
| POST | `/api/analyze` | 同参数 → **原文双检 + 逐条改写，一次返回**；改动条数恒等于违规条数；不把改写后的复检当结论（ADR-009） |
| POST | `/api/rewrite` | `{draft_id}` → 改写 + 复检 + diff |
| POST | `/api/confirm` | `{draft_id, final_content}` → 幂等确认，返回审计 id |
| GET | `/api/history?limit=20` | 这台设备查过的记录（查过就算，按 `X-Owner-Id` 隔离） |
| GET | `/api/events/{id}` | 某次检查的快照，用于恢复工作台（越权 404） |
| GET | `/api/rules?category=` | 规则列表 |

> 所有请求都会带 `X-Owner-Id`（浏览器生成的匿名设备号），历史与确认按它隔离；它不是认证，见 ADR-010。
>
> 生成 / 检查 / 分析 / 改写都会返回 `usage`（tokens、模型耗时、请求耗时、调用次数），前端状态条直接显示它；每次请求还会往 stderr 打一行 `llm_usage …` 供 `journalctl` 对账（ADR-008）。

> 环境要求：Python 3.9+（3.12 的 DSH 运行时因代码签名限制装不了 pydantic-core，用系统 Python 即可）。

## 规则库

`rules.csv` 共 40 条：

| 类别 | 前缀 | 依据 |
|---|---|---|
| 绝对化用语 | `ABS` | 《广告法》第九条 + [《广告绝对化用语执法指南》(2023)](https://www.samr.gov.cn/ggjgs/tzgg/art/2023/art_183b5cb48d9e4f0dba67f9f912a913ba.html) |
| 虚假宣传 / 医疗功效 | `FLM` | 《广告法》第十一、十二、十三、十七、十八、二十五、二十八条 |
| 平台违禁 / 引流 / 诱导 | `PLT` | [小红书社区规范 2021.12](docs/sources/xiaohongshu/社区规范-2021.md)、[社区公约 2.0](docs/sources/xiaohongshu/社区公约-2.0.md)、[「薯管家」推广规范](docs/sources/xiaohongshu/推广笔记规范-薯管家.md) |

**每条规则都带 `source`（条款号）、`source_url`、`quote`（原文摘录）、`fetched_at`、`status`。**

| 状态 | 条数 | 含义 | 校验方式 |
|---|---|---|---|
| `verified` | 20 | 《广告法》《绝对化用语执法指南》条文 | `quote` 与官方原文逐字比对 |
| `platform_official` | 19 | 社区规范 / 社区公约 2.0 / 「薯管家」推广规范 | `quote` 与存档原文逐字比对 |
| `platform_pending` | 1 | 规则中心页面前端渲染，未取得可引用原文 | 仅概述，标注待人工截图补录 |

> 平台规则中有一部分（推广占比 ≤20%、不连续两条、模板化内容）**属于账号级指标，单篇文案无法判定**，故意不进检查器，只写进 PRD，避免制造误报。详见 [存档说明](docs/sources/xiaohongshu/README.md)。

### 校验

```bash
python3 scripts/verify_rules.py               # 字段完整性 + id 唯一 + quote 逐字比对
python3 scripts/verify_rules.py --check-urls  # 额外检查来源链接是否 200
```

校验不过即退出码 1。**改一个字都会报红**，这是"规则不是编的"的机器证明。

## 文档导航

| 想知道什么 | 看哪里 |
|---|---|
| 新协作者 / AI 先看 | **[AGENTS.md](AGENTS.md)** |
| 现在做到哪了、怎么接着做 | **[D4 交接文档](docs/handover-D4.md)** ← 先看这个 |
| 产品要做什么、为什么 | [PRD](docs/PRD.md) · [PRD PDF](docs/PRD.pdf) |
| 评测怎么做、结果如何 | [评测报告](eval/report-v1.md) · [评测说明](eval/README.md) |
| 前端长什么样（结构与风格） | [UI 结构说明](docs/ui-structure.md) · [UI 风格落地](docs/ui-style.md) |
| 整体计划与每日目标 | [14 天执行计划](docs/plan.md) |
| 每天做了什么 | [开发日志](docs/log.md) |
| 为什么这么定（取舍） | [决策记录 ADR](docs/decisions.md) |
| 想到了但还没做 | [Backlog](docs/backlog.md) |
| 规则出处与原文 | [来源存档](docs/sources/) · [小红书规则存档](docs/sources/xiaohongshu/README.md) |
| 规则真实性怎么保证 | `python3 scripts/verify_rules.py` |

## 目录

```
rules.csv          规则源（40 条）
backend/           FastAPI + 规则引擎 + 29 个测试
frontend/          Next.js（入口 / 选稿 / 工作台 / 历史 / 规则 + 错误页）
eval/              评测脚本、报告、逐条结果（原始响应在 eval/runs/，不入库）
data/eval_cases/   24 条真实评测样本
docs/              PRD、交接、ADR、日志、来源存档、截图
scripts/           verify_rules / deploy / backup
```
