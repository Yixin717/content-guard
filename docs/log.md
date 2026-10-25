# 开发日志

## D0 · 2026-10-23

**今天做了什么**
- 建 GitHub 公开仓库并推送；`.env` 密钥管理（模板进 git、真值不进）。
- 规则库 39 条：法条 20（`verified`）+ 平台 19（18 条 `platform_official`、1 条 `platform_pending`）。
- 三份官方原文存档：《广告法》2021 修正条文摘录、《广告绝对化用语执法指南》全文、《小红书社区规范》2021.12、《社区公约 2.0》（图片转录）、薯管家推广规范。
- 写 `scripts/verify_rules.py`：字段完整性 + id 唯一 + **quote 逐字比对存档**；负向测试证明改一个字就报红。

**卡在哪**
- 小红书规则页是前端渲染，抓不到正文；只能靠导出的 PDF 与截图。
- 《社区公约 2.0》PDF 正文是图片，靠人工转录，已如实标注"非官方机器可读文本"。

**明天第一件事**：拿 DeepSeek key，跑通 `python -m app.cli`。

---

## D1 · 2026-10-24

**今天做了什么**
- 后端骨架：Python 3.9 venv（DSH 自带 3.12 装 pydantic 因代码签名冲突，改用系统 Python）、FastAPI/httpx/pydantic、ruff + pytest。
- `llm.py`：`response_format=json_object` + 三层兜底（直接解析 → 截取 `{...}` → 回喂错误重试），失败保留原文供分析。
- `rules.py`：CSV 为唯一来源，导出 `data/rules.json`；字符二元组 BM25 检索。
- `generate.py` / `check.py` / `cli.py`：brief → 3 版草稿 → 检索 → 检查 → 违规列表（rule_id + 原文 + 依据 + 改写）。
- 幻觉防护：模型编造的 `rule_id` 会被丢弃并记录（有单测覆盖）。
- 5 个单测 + ruff 全绿。

**实测**
- 正常 brief：3 版草稿，14.8s，tokens 7275/957，全部"未发现明确违规"并附人工复核理由。
- 故意违规文案：6 条全中（ABS-004 全网最低、FLM-001 三天根治、ABS-001 国家级、PLT-001 加V、PLT-010 明星同款、FLM-007 比大牌好用）。

**卡在哪**
- 生成端太"乖"，正常 brief 三版都零违规 → 检查器缺正样本训练机会；D2 要造一批"故意写坏"的 smoke test。
- 检查器只做单轮判断，没有 diff 改写能力（D3）。

**实测补记（用真实笔记做的第一次外测）**
用一条真实小红书笔记（ZARA 皮夹克探店）测出三个不同性质的问题：
1. 误报：「这件真的不一样」被判 ABS-002（同义绝对化）→ 根因是 prompt 缺「哪些不算」的判定纪律；
2. 漏报：「这不买真的是孙子」是侮辱式营销，但规则库无对应条款 → 补 PLT-020；
3. 反向误报：「据说还可能有掉皮」被当作需核实风险 → 实为商家自述缺点，属真实体验。

已修：检查器加三道护栏（rule_id 真实性 / quote 逐字校验 / 置信度 <0.7 转 uncertain）、
prompt 增加判定纪律与反例、规则增至 40 条。样本已存为 `data/eval_cases/001-zara-jacket.json`。

**收尾**：写了 `docs/handover-D1.md`（进度快照/仓库地图/设计决策/技术债/D2 计划/踩坑记录）。

**明天第一件事**：规则扩到 45–50 条 + 10 条 smoke test 记录漏检/误报。

---

## 追加 · 2026-10-24 晚（D2/D3 提前）

**为什么提前**：评测样本暂时找不到（依赖日常积累），但流程上不阻塞，先做改写让闭环跑通。

**做了什么**
- `rewrite.py`：按违规项改写 + 句子级 diff + **改完自动复检**；未清零则再改一轮（最多 2 轮）。
- 改写 prompt 明确禁止「换一种功效表述」（把「根治」改成「改善」仍然是违规）。
- CLI 新增 `--rewrite`（生成链路与 `--check` 链路都支持）。
- 单测 7 个。

**实测**：`全网最低价！三天根治痘痘，国家级品质，加V领福利`
→ 第 1 轮 4 条违规降到 2 条（「根治」被改成「改善」，仍属功效）→ 第 2 轮清零。
**这个案例说明复检是必要的：改写本身也会引入新违规。**

**下一步**：规则扩到 45–50 条；用合成 smoke test 代替真实评测样本（标注"合成"，不与 eval_cases 混）。

---

## 追加 · 2026-10-24 晚（D4 提前）

**做了什么**
- `db.py`：SQLite 五表（products / drafts / checks / confirmations / rules），CSV 为规则唯一来源、DB 只做副本。
- `api.py` + `schemas.py`：7 个接口，Pydantic 前置校验，LLM 异常统一 504，`/api/confirm` 用 `UNIQUE(draft_id)` 实现幂等。
- `tests/test_api.py`：5 个接口测试（422 校验、类别过滤、生成→检查→确认幂等、404），全部用 dependency override 替换 LLM，不触网。
- 单测 7 → 12 个。

**实测（真实 HTTP）**
`/health` 40 条规则；`/api/generate` 8.0s 出 3 版；`/api/check` 零违规 + human_review；
`/api/confirm` 第二次返回 `idempotent: true` 且 audit_id 相同；`/api/history` 1 条。

**卡在哪**
- 生成接口同步阻塞 8–15s，D5 前端需要 loading 态；后续可考虑异步任务。
- 尚无鉴权（计划明确不做多租户，但公开 demo 要防滥用，见 D6 备注）。

---

## 追加 · 2026-10-25（D5 设计阶段）

**做了什么**
- 收集参考：Notion 风格系统（DESIGN.md）、Notion/Linear/Postman 三栏截图、中文文档排版、RStudio diff、雅思作文批改工具。
- 产出两份文档：`docs/ui-style.md`（风格落地 + 素材评估）、`docs/ui-structure.md` §14（三栏改为 原文｜诊断｜改写）。
- 关键决定：红蓝增删（DESIGN.md 无绿色）、严重度颜色+线型双编码、去掉条款抽屉与字符级 diff、Lucide 图标（≤8 个）、不做 logo。
- 做出可点原型：`designs/prototype/`（入口页 + 三栏工作台 + 无违规态 + 改写态）。

**原型的两个简化**
1. 条款内联展开，不做抽屉；
2. 左右并排即 diff，不做字符级对比。

**下一步**：按原型实现 Next.js 前端（D5），并把 check 接口补上 `draft_id`（粘贴模式目前无法改写）。

---

## 追加 · 2026-10-25（D5 前端实现）

**后端补两个阻塞项**
- `POST /api/check {content}` 现在会自动建档并返回 `draft_id`，粘贴模式的"改写"才点得动。
- `POST /api/generate` 内置自检（ADR-003）：生成 → 检查 40 条 → 命中则自动改写（≤2 轮）→ 复检，返回体带 `self_check`。
- 实测：3 版约 19.2s，全部 `passed: true`。
- CORS 放行 `localhost/127.0.0.1` 任意端口（预览端口不固定）。

**前端**
- Next.js 14.2.35（14.2.15 有安全公告，已升级）+ App Router + 静态导出。
- 5 个页面：入口（粘贴/生成双模式）、选稿、工作台（原文/诊断/改写）、历史、规则。
- `lib/api.js` 统一数据层：默认 mock，一个环境变量切真接口；规则/历史优先读真实接口。
- `npm run build` 通过，8 个静态页产出。

---

## 追加 · 2026-10-25（D6 部署上线）

**上线**：http://43.142.12.100/ （腾讯云 CVM，Ubuntu 24.04）

**过程里踩到的三个坑**
1. 服务器 8000 被旧项目 `zero-backend.service` 占着，且旧 Nginx 也反代到 8000 → 先 stop + disable 旧服务才部署成功。
2. 首次构建忘了关 mock，**线上跑的是假数据**（规则页显示 7 条而不是 40 条）→ 部署脚本改为 `USE_MOCK=0 API_BASE=`（同源相对路径）。
3. `NEXT_PUBLIC_API_BASE=""` 被 `||` 回退成 localhost:8000 → 改用 `??` 判断 undefined。

**已验证**：五个页面 200、`/health` 40 条、`/api/check` 2.0s 命中 3 条、`/api/confirm` 幂等、公网 8000 不可达。

**未做**：HTTPS（需域名）、API 限流、SQLite 定时备份。

---

## 追加 · 2026-10-25（线上崩溃修复）

**事故**：手机打开工作台，点了几下后白屏 → `Application error: a client-side exception`。

**根因**：mock 里改写结果字段叫 `text`，真实接口叫 `script`。
`rw.text` 为 undefined，`rw.text.indexOf(...)` 直接抛错，整棵树崩掉。

**修法**
1. `lib/api.js` 增加 `normalizeRewrite` / `normalizeDraft`：**在数据层把两种形状抹平**，UI 不再关心后端字段名。
2. 工作台防御式渲染（`rw?.text || ""`）。
3. 新增 `app/error.jsx`：以后出错显示中文提示 + 重试/回入口，**不再是黑屏英文**。

**顺带修的移动端**：三栏堆叠后每栏仍是 `overflow-y:auto` 且被网格压成固定高度，内容被截断 →
改为 `height:auto` + `overflow:visible` + 整页滚动。

**一条排查记录**：用 390px 宽截图一直看到"右侧被裁"，以为是布局问题；
实测 `innerWidth=500`（headless Chrome 有最小视口 500），390 截图是"500 渲染 + 390 裁剪"的假象。
**结论：headless 截图不能用来判断窄屏溢出，要用 `innerWidth/scrollWidth` 实测。**

---

## D2 · 2026-10-25（设计 → 原型 → 前端 → 上线）

**今天做了什么**
- 定设计：Notion 风格参考落地（`docs/ui-style.md`），三栏语义改为 原文｜诊断｜改写（ADR-004），配色红蓝 + 严重度双编码（ADR-005）。
- 做可点原型 `designs/prototype/`（入口 / 生成表单 / 选稿 / 工作台 / 无违规 / 改写），配 9 张截图。
- 后端：`check` 支持粘贴自动建档并返回 `draft_id`；`generate` 内置自检 + 自动改写（ADR-003）。
- 前端：Next.js 14.2.35 + App Router + 静态导出，5 页 + 错误页，`lib/api.js` 数据层归一化（ADR-006）。
- 部署：http://43.142.12.100/ 上线（Nginx + systemd + 一键脚本 + 自动备份），替换旧项目 zero-to-tech（旧服务已 disable，代码未删）。
- CI：规则校验 / 后端 lint+测试 / 前端构建。
- 修线上白屏：mock 与后端字段名不一致（`text` vs `script`）。

**卡在哪**
- 评测集找不到真实样本（D8 推迟）；访谈未做（需要本人约人）。
- 没有域名，HTTPS 只能等（ADR-007 只解决了同源与 mock）。

**明天第一件事**
- 干掉假数字：状态条 tokens/耗时、首页"最近"列表都接真实数据（见 `docs/handover-D2.md` §6 ①）。

---

## D2 追加 · 2026-10-25（干掉假数字：B-008）

**背景**：交接文档把状态条的 `tokens 9,254 / 1,198`、`15.7s` 列为最危险的 bug。动手后发现原计划（"只改前端读接口 usage"）做不成，因为：

1. 状态条在工作台，但一次任务跨 `/api/check` + `/api/rewrite` 两个请求；
2. 这两个接口的 `response_model` 里没有 `usage` 字段，业务层算好的数字在接口边界被裁掉了；
3. `/api/generate` 只累加写作调用，自检/改写/复检的 token 全没算；
4. `api.py` 没有任何日志，原验收标准"与 journalctl 一致"根本无法执行。

**做了什么**（ADR-008）
- 后端三接口全部返回 `usage`（tokens / llm latency / 请求耗时 / 调用次数）；改写算上前置检查与复检，生成算上自检与自动改写（3 版最多 12 次调用）。
- 每次请求打一行 `llm_usage path=… tokens_in=… elapsed_ms=…` 到 stderr，日志器自带 handler，不依赖 uvicorn 配置。
- 前端 `lib/api.js` 透传、`lib/usage.js` 相加；`StatusBar` 删掉默认值，没有数字就不显示；工作台显示"本次任务合计"。
- 首页「最近」改读 `GET /api/history`（标题 / 来源 / 确认时间），删掉静态 `RECENT`。
- 顺手清掉 git 里误跟踪的 `data/content_guard.db-wal`、`.db-shm`，`.gitignore` 补 `*.db-wal/-shm/-journal`。
- 新增 4 个测试，后端 14 → 18 passed。

**怎么验的**
- 后端测试断言调用次数：改写 = 3 次（前置检查 + 改写 + 复检）、生成 = 12 次（3 版 × 4）。
- 前端不容易测，就起了个**桩接口**（不调模型、数字很好认）重建静态导出，用无头 Chrome 跑真实页面：
  check `1234/210`（1.5s）+ rewrite `800/150`（1.1s）→ 工作台状态条显示 `tokens 2,034 / 360`、`耗时 2.6s`；`/drafts` 显示 `tokens 4,321 / 777`、`耗时 12.3s`。
- `grep -rn "9,254\|15.7s" frontend/` 无结果。

**踩到的坑**
- 本机 8000 / 8010 端口都有旧的 uvicorn 在跑，桩服务绑不上；换成 8791 才干净。**那两个后端跑的是旧代码，要重启才有 `usage` 字段。**
- 真实 `/api/history` 的 `created_at` 是 ISO 格式（带 `T` 和时区），直接 `slice` 会显示出 `10-24T17:26`；要先把 `T` 换成空格再截。
- 为了看效果我随手起了个 4321 静态预览，结果绑失败、把**原本就在跑的那个**当成自己的 —— 后来按文档里的命令重启恢复，并重新用默认（mock）配置构建了 `out/`。

**部署与线上对账（当天 16:11 完成）**
- `HOST=43.142.12.100 bash scripts/deploy.sh` 上线，自动备份到 `~/nginx-backup-2026-10-25-1610`。
- 线上 chunk 里 `9,254` 已消失（逐个 chunk grep 无结果）；`/health` 仍是 `rules: 40`。
- 真实打了一组：`/api/check` → `usage 2442/89`（1247ms）、`/api/rewrite` → `5406/406`（4186ms，`attempts=3`），
  `journalctl -u content-guard | grep llm_usage` 两条日志与响应**逐字一致**。
- 把这两组真实 usage 喂给页面：状态条 `tokens 7,848 / 495`、`耗时 5.4s` = 两条日志之和 ✅
- 本次对账花了约 4 分钱（1 次 check + 1 次 rewrite）。

**下一步第一件事**
- ③ 限流 + HTTPS 前置：Nginx `limit_req`（10 次/分钟），验收是第 11 次返回 429，并把命令与结果写进 `docs/deploy.md`。
- 之后是 ④ 评测集 12 条 + 跑第一轮指标。

