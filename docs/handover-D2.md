# D2 交接文档

> 更新时间：2026-10-25（D6 部署上线后）
> 适用对象：**没参与过这个项目的新会话**
> 目标：只读本文件 + 它指的文件，就能无歧义接手

---

## 0. 一眼看懂

- **项目**：Content Guard —— 小红书带货文案的「发布前体检」。商家把要发的文案贴进来（或让 AI 写一版），系统按 40 条规则逐条检查、**每条违规指回具体条款**，自动给出合规改写，人工确认后导出。
- **现在到哪**：**D0–D6 主体已完成并上线** → http://43.142.12.100/ （HTTP，无域名）。D2 的规则扩容与访谈、D8 的评测**未做**。
- **一句话结论**：产品内核是「检查与修订」，生成只是入口（ADR-001）；生成结果也必须内置自检（ADR-003）。**别把它当成"AI 文案生成器"来改。**

---

## 1. 进度快照（全部当场核对过）

| 项 | 数值 / 状态 | 核对方式 |
|---|---|---|
| Git 提交数 | **36** | `git rev-list --count HEAD` |
| 是否已推送 | **是**，`main...origin/main` 无差异 | `git status -sb` |
| 工作区 | **干净**（无未提交改动） | `git status --short` |
| 后端测试 | **14 passed** | `cd backend && .venv/bin/pytest -q` |
| 规则总数 | **40** | `python3 scripts/verify_rules.py` |
| 规则可信分档 | verified 20 / platform_official 19 / platform_pending 1 | 同上 |
| 规则类别 | 绝对化 10 / 虚假宣传 10 / 平台 20 | 同上 |
| 后端接口 | 7 个（health/generate/check/rewrite/confirm/history/rules） | `backend/app/api.py` |
| 数据库表 | 5 张（products/drafts/checks/confirmations/rules） | `backend/app/db.py` |
| 前端页面 | 5 个 + 全局错误页 | `frontend/app/` |
| 线上健康 | `{"status":"ok","model":"deepseek-chat","rules":40}` | `curl http://43.142.12.100/health` |
| 线上改写链路 | 实测 before 2 → after 0 | `POST /api/check` → `/api/rewrite` |
| 评测样本 | **1 条**（`data/eval_cases/001-zara-jacket.json`） | `ls data/eval_cases` |
| CI | 已配置 3 个 job，**首次运行结果待确认** | `.github/workflows/ci.yml` |

---

## 2. 未提交改动

**当前没有未提交改动**（`git status --short` 为空）。

以下文件被 `.gitignore` 排除、**故意不入库**，新会话不要试图提交它们：

| 路径 | 原因 |
|---|---|
| `.env` | 含 DeepSeek key（线上在服务器 `~/content-guard/backend/.env`） |
| `backend/.venv/`、`frontend/node_modules/`、`frontend/.npm-cache/` | 依赖，可重装 |
| `frontend/out/`、`frontend/.next/` | 构建产物 |
| `data/*.db`、`out/*.json` | 运行时数据 |
| `designs/prototype/screens/*` | **例外：这些截图已入库**，是 README/演示素材 |

> 若接手时 `git status` 不为空：先看 `git diff --stat`，把改动归类成"设计稿 / 代码 / 文档"，分别确认后再提交，**不要 `git add -A` 一把梭**——历史上就是因为这个习惯误删过演示数据。

---

## 3. 本轮做完的事 + 与计划的偏差

### 3.1 做完的事（按主题）

| 主题 | 产出 |
|---|---|
| 设计与原型 | `designs/prototype/`（可点 HTML 原型，5 个状态）；`docs/ui-structure.md`、`docs/ui-style.md` |
| 产品决策 | ADR-002（双入口、不做落地页）、ADR-003（生成即自检） |
| 后端加固 | `check` 自动建档返回 `draft_id`；`generate` 内置自检+自动改写（`backend/app/api.py`）；CORS 放行本地任意端口 |
| 前端 | Next.js 14.2.35 + App Router + 静态导出；5 页 + 错误页；`lib/api.js` 统一数据层（mock 可切真接口） |
| 部署 | 上线公网 IP；Nginx + systemd + 一键脚本 + 备份；`docs/deploy.md` |
| CI | 规则校验 / 后端 lint+测试 / 前端构建 三个 job |
| 线上事故修复 | 改写结果字段不一致导致白屏（详见 §5） |

### 3.2 与计划的偏差

| 计划 | 实际 | 原因 |
|---|---|---|
| D2：规则扩到 45–50 条 | **未做**，仍 40 条 | 真实案例驱动补更准；40 条已够跑通全链路 |
| D2：2–3 位商家访谈 | **未做** | 需要用户本人约人，AI 无法代做 |
| D5：前端 | ✅ 提前完成 | 原型定稿后照着实现很快 |
| D6：部署 + HTTPS | 部署✅／HTTPS ❌ | 没有域名，先用 IP + HTTP |
| D8：24 条评测集 + 指标 | **未做**，仅 1 条样本 | 用户反馈"真实样本难找"，已改为日常积累（backlog B-005） |
| D10：PRD | **未做** | — |
| D10：CI | ✅ 提前完成 | 不依赖外部条件 |
| D11：3 分钟视频 | **未做** | — |

**净结果：工程进度比计划快约 4 天，但"证据类交付物"（评测、访谈、PRD）全部落后。**

---

## 4. 被否掉的方案（比做成的更值钱）

| # | 试了什么 | 为什么否掉 | 替代方案 |
|---|---|---|---|
| 1 | 三栏 500/400/444 + **点击违规弹出 480px 条款抽屉** + 字符级 diff 视图 | 组件多、状态多；740px 里塞不下"原文 vs 改写"并排对比 | **左原文 / 中诊断 / 右改写**，条款在卡片内联展开，左右并排本身就是 diff（少两个组件） |
| 2 | 首页做营销落地页（Hero + 功能 + CTA） | 工具型产品，用户打开就是要用，落地页只是障碍 | 首屏 = 大粘贴框 + 最近记录 |
| 3 | 检查与生成做成**两张等权大卡** | 逼用户在首页先做一次选择，违背"检查是默认动作" | 生成降级为 ghost 按钮「生成一版 →」 |
| 4 | 在选稿页**故意留一句「全网最低」**，让演示能看到违规命中 | 拿用户信任换演示效果——用户买的就是"你懂条款" | **ADR-003**：生成即自检，命中自动改写，通过才返回 |
| 5 | diff 用**红/绿**（行业惯例） | DESIGN.md 调色板里**没有绿色**；红绿色盲最普遍 | 红（删除）+ 蓝（新增），全部取自调色板，且红蓝对色弱友好 |
| 6 | 严重度用**红色深浅三档**表示 | 投影仪/不同屏幕上三档红几乎不可分 | 颜色 + 线型双编码（实线 2px / 实线 1.5px / 虚线） |
| 7 | 微调模型学小红书语气 | 样本不够、规则一变就要重训、容易连"全网最低"一起学 | few-shot + 风格清单（backlog B-007） |
| 8 | 规则页默认纯 mock 数据 | 出现"共 7 条"与状态条"40 条"自相矛盾的画面 | 规则/历史**优先读真接口**，后端没起才退回样例 |
| 9 | 用 390px 宽截图判断移动端是否溢出 | headless Chrome 最小视口是 500px，390 截图是"500 渲染 + 390 裁剪"的假象，白改两轮 CSS | 在页面里量 `innerWidth / scrollWidth` |

---

## 5. 未决问题 / 已知 bug / 坑

### 5.1 已知 bug（都还没修，按危险度排序）

| # | 问题 | 位置 | 影响 |
|---|---|---|---|
| **B1** | **状态条数字是写死的**（`tokens 9,254 / 1,198`、`15.7s`） | `frontend/app/workbench/page.jsx:322` | demo/面试时会被当成真实指标——**这是最危险的一条，属于"假数字"** |
| **B2** | 首页"最近"是静态 mock 列表 | `frontend/app/page.jsx:9`、`:143` | 与真实历史不一致 |
| **B3** | mock 模式下确认接口用假 `draft_id` | `frontend/lib/api.js`（`confirm`） | 接真后端会 404；线上 `USE_MOCK=0` 故不受影响 |
| **B4** | `/api/generate` 约 19s，前端只有"生成中…" | `frontend/app/page.jsx`（`busy` 态） | ADR-003 要求分阶段进度（生成中/自检中/修复中），未实现 |
| **B5** | 无 HTTPS、无 API 限流 | `deploy/nginx-content-guard.conf` | 明文传输；`/api/generate` 公网可刷（每次约 2 分钱） |
| B6 | `PLT-002 诱导互动` 仍是 `platform_pending` | `rules.csv` | 该条引用不可逐字验证 |
| B7 | SQLite 无定时备份 | `data/content_guard.db` | 服务器故障即丢数据 |

### 5.2 坑（踩过的，带位置）

| 坑 | 位置 | 说明 |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` 必须用 `??` 不能用 `\|\|` | `frontend/lib/api.js:14` | 空字符串是 falsy，`\|\|` 会回退成 localhost，线上就变成"浏览器连自己电脑" |
| mock 与后端字段名不一致 → 白屏 | `frontend/lib/api.js:38`（`normalizeRewrite`） | mock 用 `text`、后端用 `script`；**必须在数据层归一化，UI 不直接读后端字段** |
| CORS 只放行 3000 端口 | `backend/app/api.py:58` | 静态预览用 4311/4321 会被拦，且**前端静默退回 mock，页面看不出异常** |
| 部署必须关 mock | `scripts/deploy.sh`（构建行） | 首次部署忘了关，线上跑的是假数据 |
| 服务器 8000 被旧项目占用 | 服务器 `zero-backend.service` | 已 `stop` + `disable`，否则新服务起不来 |
| 本地 Python 必须是 3.9 | `backend/.venv` | DSH 自带 3.12 因代码签名装不了 `pydantic_core` |
| PDF 里的康熙部首字符 | `scripts/verify_rules.py:46`（`RADICAL_FIX`） | `⻛/⻝/⻓` 与「风/食/长」码位不同，不映射就永远匹配不上 |
| headless Chrome 最小视口 500px | — | 390 宽截图不能判断窄屏溢出 |

---

## 6. 下一步（只列 3 条，每条带验收标准）

### ① 干掉所有假数字（最高优先）
- 状态条改为**本次请求真实 tokens / 耗时**（来源：接口 `usage` 字段，后端已在 `meta` 里返回）
- 首页"最近"改为 `GET /api/history` 真实数据
- **验收**：`grep -rn "9,254\|15.7s" frontend/` 无结果；工作台刷新后状态条数字与 `journalctl` 中该次请求的 token 数一致。

### ② 限流 + HTTPS 前置
- Nginx 加 `limit_req`（按 IP，如 10 次/分钟），超限返回 429
- **验收**：连续快速请求 `/api/generate` 第 11 次返回 429；把测试命令与结果写进 `docs/deploy.md`。

### ③ 评测集 12 条 + 跑第一轮指标
- 从用户日常笔记补到 12 条，写 `eval/run_eval.py`
- **验收**：脚本输出 `recall / false_positive / citation_accuracy` 三项数字，报告落到 `eval/report-v1.md`。

---

## 7. 新会话开场：按这个顺序读

1. **本文件**（你正在读）
2. `docs/decisions.md` —— ADR-001 ~ ADR-007，**所有"为什么这么选"都在这里**
3. `docs/log.md` —— 最后两条（部署上线、线上崩溃修复）
4. `docs/deploy.md` —— 线上在哪、怎么改、怎么回滚
5. `docs/handover-D1.md` §3、§4 —— 本地怎么跑、规则三档可信度的由来
6. `docs/ui-structure.md` / `docs/ui-style.md` —— **改前端前必读**，否则会改回被否掉的方案
7. `docs/backlog.md` —— 想过但没做的事
8. `docs/plan.md` §9 —— 原始 14 天节奏（只作参考，已被多处提前）

**先跑这四条确认环境是活的**：

```bash
git log --oneline -5
cd backend && .venv/bin/pytest -q          # 期望 14 passed
cd .. && python3 scripts/verify_rules.py   # 期望 "全部通过（0 项警告，0 项失败）"
curl -s http://43.142.12.100/health        # 期望 rules: 40
```

---

## 8. 环境与访问（不做这一步会卡住）

| 项 | 值 |
|---|---|
| 线上地址 | http://43.142.12.100/ |
| 服务器 | `ssh ubuntu@43.142.12.100`（已免密，公钥在 `~/.ssh/id_ed25519`） |
| 部署 | `HOST=43.142.12.100 bash scripts/deploy.sh`（自动备份旧站） |
| 本地前端 | `cd frontend && npm run dev`（默认 mock） |
| 本地后端 | `cd backend && .venv/bin/uvicorn app.main:app --port 8000` |
| 本地静态预览 | `python3 -m http.server 4321 --directory frontend/out` |
| DeepSeek key | 本地 `.env`；线上 `~/content-guard/backend/.env` |
