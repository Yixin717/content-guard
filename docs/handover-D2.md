# D2 交接文档

> 更新时间：2026-10-25（B-008「假数字」修复后；线上仍是修复前的版本）
> 适用对象：**没参与过这个项目的新会话**
> 目标：只读本文件 + 它指的文件，就能无歧义接手

---

## 0. 一眼看懂

- **项目**：Content Guard —— 小红书带货文案的「发布前体检」。商家把要发的文案贴进来（或让 AI 写一版），系统按 40 条规则逐条检查、**每条违规指回具体条款**，自动给出合规改写，人工确认后导出。
- **现在到哪**：**D0–D6 主体已完成并上线** → http://43.142.12.100/ （HTTP，无域名）。**第一批改造（条款原文 / 一次算完 / 编号一致 / 高亮 / 配色 / 去 AI 标志）已上线**；第二批（历史 + 匿名设备号）未做；D2 的规则扩容与访谈、D8 的评测**未做**。
- **一句话结论**：产品内核是「检查与修订」，生成只是入口（ADR-001）；生成结果也必须内置自检（ADR-003）；**页面上的数字必须来自后端 `usage`，不许写死**（ADR-008）。**别把它当成"AI 文案生成器"来改。**


---

## 1. 进度快照（全部当场核对过）

| 项 | 数值 / 状态 | 核对方式 |
|---|---|---|
| Git 提交数 | **42** | `git rev-list --count HEAD` |
| 是否已推送 | **是**，`main...origin/main` 无差异 | `git status -sb` |
| 工作区 | **干净**（无未提交改动） | `git status --short` |
| 后端测试 | **23 passed** | `cd backend && .venv/bin/pytest -q` |
| 规则总数 | **40** | `python3 scripts/verify_rules.py` |
| 规则可信分档 | verified 20 / platform_official 19 / platform_pending 1 | 同上 |
| 规则类别 | 绝对化 10 / 虚假宣传 10 / 平台 20 | 同上 |
| 后端接口 | 8 个（health/generate/check/analyze/rewrite/confirm/history/rules） | `backend/app/api.py` |
| 数据库表 | 5 张（products/drafts/checks/confirmations/rules） | `backend/app/db.py` |
| 前端页面 | 5 个 + 全局错误页 | `frontend/app/` |
| 检查-改写一致性 | 改动条数 = 违规条数（后端强制，`unresolved` 单独标）；问题按**原文顺序**编号 | `POST /api/analyze`、`backend/tests/test_api.py` |
| 线上健康 | `{"status":"ok","model":"deepseek-chat","rules":40}` | `curl http://43.142.12.100/health` |
| 线上版本 | **已部署 ADR-008 + ADR-009** | 工作台无「改写中」；状态条无模型名 |
| 线上对账 | analyze 5817/689（5.2s，3 次调用）→ 4 处违规 / 4 条改动，编号 1:1 | 2026-10-25 21:06 实测 |
| 线上改写链路 | 实测 4 处 → 0 处（1 轮），`start/end` 与 `after` 完全一致 | `POST /api/analyze` |
| 评测样本 | **1 条**（`data/eval_cases/001-zara-jacket.json`） | `ls data/eval_cases` |
| CI | 3 个 job 全绿 | `31415ca`/`5a756e1`/`f8cc484` 的 run 均 success |


---

## 2. 未提交改动

**当前没有未提交改动**（`git status --short` 为空）。

以下文件被 `.gitignore` 排除、**故意不入库**，新会话不要试图提交它们：

| 路径 | 原因 |
|---|---|
| `.env` | 含 DeepSeek key（线上在服务器 `~/content-guard/backend/.env`） |
| `backend/.venv/`、`frontend/node_modules/`、`frontend/.npm-cache/` | 依赖，可重装 |
| `frontend/out/`、`frontend/.next/` | 构建产物 |
| `data/*.db`、`data/*.db-wal`、`data/*.db-shm`、`out/*.json` | 运行时数据 |
| `designs/prototype/screens/*` | **例外：这些截图已入库**，是 README/演示素材 |

> **2026-10-25 补**：`data/content_guard.db-wal`、`.db-shm` 曾被误提交（`.gitignore` 只写了 `*.db`，盖不住这两个后缀），已 `git rm --cached` 并补规则。这类文件入库没有任何意义，还会让 `git status` 一直脏。
>
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
| 工作台一致性（ADR-009） | `/api/analyze` 一次算完；改写改为逐条局部替换；改动条数 = 违规条数；条款原文内联；蓝字高亮；配色 #FFFAF0/#FFFDF7 |
| 数据真实性（B-008） | 状态条改真实 `usage`；后端三接口补 `usage` 并全量累计；每请求一行 `llm_usage` 日志；首页「最近」改读 `/api/history`（ADR-008） |

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
| 10 | **只把页面里的两个字符串换掉**（"读一下接口 usage 就行"） | `check`/`rewrite` 的 `response_model` 里压根没有 `usage` 字段——改完只是换了个假数字，而且 `grep` 验收还查不出来 | **ADR-008**：后端三接口补 `usage` 且全量累计 + 每请求一行日志，前端只透传；没数字就不显示 |

---

## 5. 未决问题 / 已知 bug / 坑

### 5.1 已知 bug（按危险度排序）

| # | 问题 | 位置 | 状态 / 影响 |
|---|---|---|---|
| ~~B1~~ | ~~状态条数字是写死的~~ | `frontend/app/workbench/page.jsx`、`components/StatusBar.jsx` | ✅ **已修**（ADR-008）：改读 `usage`，无数字不显示。桩数据实测 1234/210 + 800/150 → `tokens 2,034 / 360`、`2.6s` |
| ~~B2~~ | ~~首页"最近"是静态 mock 列表~~ | `frontend/app/page.jsx` | ✅ **已修**：改读 `GET /api/history`（标题 / 来源 / 确认时间） |
| **B3** | mock 模式下确认接口用假 `draft_id` | `frontend/lib/api.js`（`confirm`） | 未修。接真后端会 404；线上 `USE_MOCK=0` 故不受影响 |
| **B4** | `/api/generate` 约 19s，前端只有"生成中…" | `frontend/app/page.jsx`（`busy` 态） | 未修。ADR-003 要求分阶段进度（生成中/自检中/修复中），未实现 |
| **B5** | 无 HTTPS、无 API 限流 | `deploy/nginx-content-guard.conf` | 未修。明文传输；`/api/generate` 公网可刷（每次约 2 分钱） |
| B6 | `PLT-002 诱导互动` 仍是 `platform_pending` | `rules.csv` | 未修。该条引用不可逐字验证 |
| B7 | SQLite 无定时备份 | `data/content_guard.db` | 未修。服务器故障即丢数据 |

### 5.2 坑（踩过的，带位置）

| 坑 | 位置 | 说明 |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` 必须判断"是否定义"，不能判断真假值 | `frontend/lib/api.js:14` | 空字符串是 falsy，用 `\|\|` 会回退成 localhost，线上就变成"浏览器连自己电脑" |
| mock 与后端字段名不一致 → 白屏 | `frontend/lib/api.js`（`normalizeRewrite`） | mock 用 `text`、后端用 `script`；**必须在数据层归一化，UI 不直接读后端字段** |
| **Pydantic `response_model` 会悄悄裁掉没声明的字段** | `backend/app/schemas.py` | 业务层 `to_dict()` 里明明有 `usage`，`CheckResponse` 没写这个字段 → 接口就是不返回。**加字段必须同时改 schema 和调用处**，否则前端拿到 `undefined` 还以为后端没算 |
| **mock 数据没有 `usage`** | `frontend/lib/mock.js` | 本地 mock 模式下状态条**不显示** tokens / 耗时。这是故意的（ADR-008），别为了"看起来完整"补个默认值 |
| **线上 `/api/history` 的 `created_at` 是 ISO 格式** | `frontend/app/page.jsx` | `2026-10-25T15:41:07+08:00`，直接 `slice` 会显示 `10-25T15:41`；先 `replace("T"," ")` 再截 |
| CORS 只放行 3000 端口 | `backend/app/api.py`（`allow_origin_regex`） | 旧版写死 3000，静态预览用 4311/4321 会被拦，且**前端静默退回 mock，页面看不出异常**；现为正则放行 localhost 任意端口 |
| 部署必须关 mock | `scripts/deploy.sh`（构建行） | 首次部署忘了关，线上跑的是假数据 |
| 服务器 8000 被旧项目占用 | 服务器 `zero-backend.service` | 已 `stop` + `disable`，否则新服务起不来 |
| 本地 Python 必须是 3.9 | `backend/.venv` | DSH 自带 3.12 因代码签名装不了 `pydantic_core` |
| 本机常见"端口被旧服务占着" | 8000 / 8010 / 4321 | 起服务前先 `lsof -nP -iTCP:<port> -sTCP:LISTEN`；**不要想当然 kill，先看清是谁的**（本机就出现过误杀预览服务） |
| PDF 里的康熙部首字符 | `scripts/verify_rules.py:46`（`RADICAL_FIX`） | `⻛/⻝/⻓` 与「风/食/长」码位不同，不映射就永远匹配不上 |
| headless Chrome 最小视口 500px | — | 390 宽截图不能判断窄屏溢出 |
| 无头 Chrome 要带 `--user-data-dir` | — | 否则报 `Failed to create headless user data directory container`，`--dump-dom` 输出为空 |
| **React hooks 不能在提前 return 之后** | `frontend/app/workbench/page.jsx` | 曾经把 `useMemo` 写在 `if (!sample) return null` 后面 → React error #310，整页报错。所有 hook 提到 return 之前 |
| **`next build` 会清空 `out/`** | — | 构建后再生成临时 seed 页；先放会被删掉，`http.server` 就只剩 404 |
| 粘贴文案的标题 = 正文第一行 | `backend/app/api.py`（`_resolve_and_check`） | 若同时当 `title` 传给检查器，同一句话会检查两遍、改写可能只改到 title。粘贴场景统一 `title=""` |
| **一次 analyze 约 5–10 秒** | `POST /api/analyze` | 3 次模型调用（检查 + 改写 + 复检）。前端显示真实计时，不要加"假进度" |

### 5.3 明确不做（防止新会话加戏）

以下都是**已经决定不做**的，不要"顺手实现"：

| 不做 | 原因 |
|---|---|
| 真实发布到小红书/平台 API | 需要商家授权与平台合规审批，风险与工作量都超出 2 周项目 |
| 登录 / 多租户 / 权限 | 计划明确砍掉；公开 demo 用限流而非鉴权 |
| 支付 / 计费 | 同上，只写进 PRD |
| 模型微调 / 训练 | 样本不足、规则一变就要重训（B-007 已定：用 few-shot） |
| 自主 Agent / 多步规划 | 合规场景要可审计、可回放，固定流水线更稳（ADR-001 上下文） |
| 全量平台规则库 | 只做 3 类 40 条；"不全"在 PRD 里如实写 |
| 图片 / 视频合规检查 | 本期只查文本，UI 上已写明 |
| 直播间话术 / 商品卡 / 多平台 adapter | 只进 PRD 的迁移章节（P2） |
| 营销落地页 | ADR-002 |
| 深色模式 | P2，仅在 CSS 变量上预留 |

---

## 6. 下一步（每条带验收标准）

### ① ✅ 已完成：干掉所有假数字（2026-10-25，ADR-008）
- 状态条改为**本次任务真实 tokens / 耗时**（来源：后端 `usage`；`check` + `rewrite` 相加）
- 首页"最近"改为 `GET /api/history` 真实数据
- 为了让数字是真的，顺带做了三件原计划没有的事：`check`/`rewrite` 响应补 `usage`、`generate` 补算自检与改写、每请求一行 `llm_usage` 日志
- **验收记录**：
  - `grep -rn "9,254\|15.7s" frontend/` → 无结果 ✅
  - 桩接口（check 1234/210 1.5s + rewrite 800/150 1.1s）→ 页面 `tokens 2,034 / 360`、`耗时 2.6s` ✅
  - `/drafts` 生成入口 4321/777 12.3s → `tokens 4,321 / 777`、`耗时 12.3s` ✅
  - 线上对账**尚未做**，因为下面这一条还没做 ↓

### ② ✅ 已完成：部署 + 线上对账（2026-10-25 16:11）
- 执行 `HOST=43.142.12.100 bash scripts/deploy.sh`（自动备份到服务器 `~/nginx-backup-2026-10-25-1610` 与 `~/var-www-backup-2026-10-25-1610`）
- **验收记录**：
  - 线上 JS chunk 里 `9,254` **已消失**（逐个 chunk grep 无结果）
  - `/api/check` → `usage 2442/89`（1247ms）；`/api/rewrite` → `5406/406`（4186ms、3 次调用）
  - `sudo journalctl -u content-guard | grep llm_usage` 两条日志与响应数字**完全一致**
  - 把这两组真实 usage 喂给页面 → 状态条显示 `tokens 7,848 / 495`、`耗时 5.4s`，**等于两条日志之和** ✅
- 本地那两个旧 uvicorn（8000/8010）仍是旧代码，要用 `usage` 需重启

### ③ 第二批：历史记录 + 匿名设备号（用户已定方案 C）
- 新增事件表（方案 C）：每次检查一条记录，字段含 owner / 状态 / 问题数 / 结论快照
- 匿名设备号：localStorage UUID + `X-Owner-Id` 请求头（不用 cookie，避免本地跨端口 SameSite 问题）
- 首页「最近」与历史页：**标题（或首句）+ 时间 + 几处问题**，按设备隔离；查过就算，不要求确认
- 历史点开可恢复那次任务；线上老记录（无主）不展示
- **验收**：两个不同浏览器/隐身窗口互相看不到对方记录；同一文案查 3 次出现 3 条

### ④ 限流 + HTTPS 前置
- Nginx 加 `limit_req`（按 IP，如 10 次/分钟），超限返回 429
- **验收**：连续快速请求 `/api/generate` 第 11 次返回 429；把测试命令与结果写进 `docs/deploy.md`。

### ⑤ 评测集 12 条 + 跑第一轮指标
- 从用户日常笔记补到 12 条，写 `eval/run_eval.py`
- **验收**：脚本输出 `recall / false_positive / citation_accuracy` 三项数字，报告落到 `eval/report-v1.md`。
- **注意**：`.gitignore` 里有 `eval/*.json`，样本继续放 `data/eval_cases/`，别放 `eval/`（backlog B-009）。

---

## 7. 新会话开场：按这个顺序读

1. **本文件**（你正在读）
2. `docs/decisions.md` —— ADR-001 ~ ADR-009，**所有"为什么这么选"都在这里**
3. `docs/log.md` —— 最后两条（线上崩溃修复、假数字修复）
4. `docs/deploy.md` —— 线上在哪、怎么改、怎么回滚
5. `docs/handover-D1.md` §3、§4 —— 本地怎么跑、规则三档可信度的由来
6. `docs/ui-structure.md` / `docs/ui-style.md` —— **改前端前必读**，否则会改回被否掉的方案
7. `docs/backlog.md` —— 想过但没做的事
8. `docs/plan.md` §9 —— 原始 14 天节奏（只作参考，已被多处提前）

**先跑这四条确认环境是活的**：

```bash
git log --oneline -5
cd backend && .venv/bin/pytest -q          # 期望 23 passed
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
| 用量对账 | `sudo journalctl -u content-guard \| grep llm_usage`（线上）、直接看终端 stderr（本地） |

> 起服务前先 `lsof -nP -iTCP:<port> -sTCP:LISTEN` 看一眼：本机经常有旧 uvicorn 占着 8000/8010，静态预览也可能已被占用。

