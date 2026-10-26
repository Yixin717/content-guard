# D1 交接文档

> **已被 `handover-D3.md` 取代**。本文件是 D1 当时的快照，只用来查「本地怎么跑」「规则三档可信度的由来」。

> 更新时间：2026-10-24（D1 结束）
> 适用对象：明天的自己 / 任何接手这个仓库的人
> 目标：**5 分钟内知道"现在在哪、为什么这么定、下一步做什么"**

---

## 0. 一眼看懂

**做什么**：小红书商家输入商品卖点 → 生成 3 版短视频带货文案 → 按《广告法》与小红书规则检查 → 每条违规指回条款 → 给合规改写 → 人工确认后导出。

**当前进度**：D1 完成。**CLI 端到端跑通**（生成 + 检查 + 引用），尚无 API、数据库、前端、部署。

**一句话结论（ADR-001）**：产品内核是**检查与修订**，生成只是入口。

---

## 1. 进度快照

| 项 | 数值 | 备注 |
|---|---|---|
| Git 提交 | 14 个 | 全部已推送 `Yixin717/content-guard` |
| 规则条数 | **40** | 绝对化 10 / 虚假宣传 10 / 平台 20 |
| 规则可信状态 | `verified` 20 · `platform_official` 19 · `platform_pending` 1 | 见 §4.1 |
| 官方原文存档 | 5 份 | 《广告法》《绝对化用语执法指南》《社区规范》《社区公约 2.0》《薯管家推广规范》 |
| 评测样本 | 1 条真实笔记 | `data/eval_cases/001-zara-jacket.json` |
| 单元测试 | 6 个 | JSON 兜底 2 / 规则 2 / 幻觉过滤 1 / suspected+引用校验 1 |
| 代码检查 | ruff 全绿 | `target-version=py39` |
| 首次端到端实测 | 14.8s，tokens 7275 in / 957 out | 3 版草稿 + 3 次检查（当时 39 条规则） |
| 检查器实测 | 故意违规文案 6→3 条全中；真实笔记误报已修 | 见 §4.5 |

**验收对照（计划 D1 要求）**

| 计划要求 | 状态 |
|---|---|
| `python -m app.cli "..."` 打印 3 版草稿 + 违规列表 | ✅ |
| `rules.json` 30 条以上 | ✅ 40 条 |
| 至少 5 次 commit | ✅ 14 次 |
| 能说清"JSON 输出失败时程序怎么处理" | ✅ 见 §4.2 |
| 前端 Next.js 脚手架（先空页面） | ⏸ **未做**，合并到 D5（见 §7） |

---

## 2. 仓库地图

```
content-guard/
├── README.md                 门面：定位、快速开始、规则库说明
├── rules.csv                 ★ 规则唯一事实来源（40 条，15 列）
├── .env.example              环境变量模板（真值 .env 不入库）
│
├── backend/
│   ├── app/
│   │   ├── config.py         .env 加载、路径、价格（未配置时按 0，不猜）
│   │   ├── llm.py            DeepSeek 客户端 + JSON 三层兜底
│   │   ├── rules.py          CSV → Rule；导出 JSON；字符二元组 BM25
│   │   ├── prompts.py        写作/审核 system prompt + 判定纪律 + 反例
│   │   ├── generate.py       3 个角度各生成一版
│   │   ├── check.py          检索 → LLM 核对 → 三道护栏 → 置信度分流
│   │   └── cli.py            命令行入口（生成 / --check / --json）
│   ├── tests/test_pipeline.py 6 个不依赖网络的单测
│   ├── pyproject.toml        ruff + pytest 配置
│   └── requirements.txt
│
├── data/
│   ├── rules.json            rules.csv 的派生产物（前端/评测用）
│   └── eval_cases/           评测样本（目前 1 条）
│
├── docs/
│   ├── plan.md               14 天总计划（原始）
│   ├── log.md                逐日日志（D0 / D1 已写）
│   ├── decisions.md          ADR-001 产品定位决策
│   ├── backlog.md            想法池 B-001 ~ B-004
│   ├── handover-D1.md        ← 本文件
│   └── sources/              官方原文存档（引用底本，可逐字核对）
│
└── scripts/
    ├── verify_rules.py       规则真实性校验（字段/唯一/逐字比对/反例提醒）
    ├── export_rules_json.py  CSV → JSON
    └── init_env.sh           交互式写入 .env 并验证 key
```

---

## 3. 怎么跑起来（复现 3 步）

```bash
cd "/Users/yixin/Documents/deepseek-harness/default-workspace/content-guard"

# 1) 密钥（只需一次；写 .env，600 权限，不进 git）
bash scripts/init_env.sh

# 2) 依赖（Python 3.9；见 §8 坑 1）
cd backend && /usr/bin/python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 3) 跑
.venv/bin/python -m app.cli "杭州女装小店，冰丝阔腿裤，遮胯显瘦，69 元两条"
.venv/bin/python -m app.cli --check "全网最低，三天根治痘痘，加V领福利"
```

**验证当前状态健康**

```bash
python3 scripts/verify_rules.py          # 应输出：全部通过（0 项警告，0 项失败）
cd backend && .venv/bin/python -m pytest -q   # 应 6 passed
.venv/bin/ruff check app tests           # 应 All checks passed
```

---

## 4. 关键设计（为什么这么写）

### 4.1 规则可信度分三档，而不是"有/没有"

| 状态 | 含义 | 校验方式 |
|---|---|---|
| `verified` | 《广告法》《执法指南》条文 | `quote` 与官方原文逐字比对 |
| `platform_official` | 小红书官方文档/官方账号内容 | `quote` 与存档原文逐字比对 |
| `platform_pending` | 只拿到概述，无原文 | 允许存在，但必须写明"待补" |

**为什么不合并**：法条和平台规则的可信度、变动频率、判定口径完全不同。混在一起，面试被问"你这规则哪来的"就答不干净。
**当前唯一 pending**：`PLT-002 诱导互动`（规则中心前端渲染，取不到正文）。

### 4.2 结构化输出的三层兜底（计划里要求"能说清"的那条）

1. **第一层**：`response_format={"type":"json_object"}` + `json.loads`
2. **第二层**：失败则 `_extract_json()` 从 markdown 围栏或前后缀里截最外层 `{...}`
3. **第三层**：仍失败 → 把错误信息回喂给模型，`temperature` 降到 0 重试一次

全部失败抛 `LLMError`，**保留原始返回文本**（`exc.raw`），供后续做失败样本分析。

### 4.3 三道工程护栏（被真实误报逼出来的）

1. **rule_id 必须真实存在** → 模型编造的 id 直接丢弃，记入 `dropped_unknown_rule_ids`
2. **quote 必须逐字出现在草稿里** → 只"概括"不"引用"的，丢弃并记入 `dropped_quotes`
3. **置信度 < 0.7 不进 violations** → 转入 `uncertain`（待确认），避免误报污染信任

### 4.4 `suspected` 通道：规则库不完备时不要硬套条款

真实测试发现：遇到"规则没覆盖但明显有问题"的表述，模型会**就近硬套一条错误条款**（把"不买是孙子"套成"淫秽赌博"）。
处理方式：给模型第三条路——`suspected`（无 rule_id，只有 quote + reason），直接进人工复核。
**副产品**：`suspected` 高频出现的内容，就是下一步该补的规则。

### 4.5 反例（counter_examples）是防误报的第一道墙

10 条绝对化规则都填了"**不算违规**"的例子，并进入 prompt。效果来自真实事故：

| 表述 | 修复前 | 修复后 |
|---|---|---|
| 「这件真的不一样」 | 误报 ABS-002 | 不报 |
| 「据说还可能有掉皮」 | 被标为需核实风险 | 不报（自述缺点属真实体验） |
| 「这不买真的是孙子」 | 只在 reason 里提一句 | 命中 PLT-020 |

### 4.6 生成结果自带 AI 声明

返回字段里有 `disclosure: "本内容由 AI 辅助生成，已人工确认"`。
依据《社区公约 2.0》「你在创作中使用了AI辅助工具，请主动标明」——**工具产出的就是 AI 文案，不声明等于帮用户违规**（backlog B-001，已落地）。

---

## 5. 产品判断（会影响后面怎么排期）

### 5.1 内核是检查，不是生成（ADR-001）

- 生成负责"让用户愿意进来"，检查负责"让用户敢发出去"，改写负责"让用户愿意付钱"
- **必然后果**：D5 前端必须有"粘贴已有文案检查"的入口；D3 的改写是核心功能，不是附属
- **可推翻条件**：若访谈发现商家根本没时间自己写，生成权重上调，但检查不能砍

### 5.2 评测节奏：现在攒样本，D8 才算指标

- **现在不跑指标**：pipeline 在 D2/D3 还会大改，现在测的数字明天就作废，且会误以为"已经评测过"
- **现在开始攒样本**：真实笔记是最贵的资产，一条"平台边界模糊"的样本顶十条编造的
- 标注必须写 `notes`，并注明**哪些是故意不报的反例**

### 5.3 账号级规则不进检查器

推广占比 ≤20%、不连续 2 篇、模板化内容、经营身份——都需要账号历史数据，单篇判不了。硬塞会制造大量误报，只写进 PRD（backlog B-003）。

---

## 6. 已知问题 / 技术债

### 高（会影响 D2/D3）

| # | 问题 | 影响 | 计划 |
|---|---|---|---|
| H1 | 生成端太"乖"，正常 brief 三版零违规 | 缺正样本，检查器没被真正考验 | D2 造"故意写坏"的 smoke test |
| H2 | 检查器只做单轮判断，无改写、无 diff | 价值只兑现一半 | D3 |
| H3 | 评测样本仅 1 条，指标未跑 | 简历上的数字暂无依据 | D8 |

### 中

| # | 问题 | 计划 |
|---|---|---|
| M1 | 尚无 API / DB / 前端 / 部署 | D4 / D5 / D6 |
| M2 | `PLT-002 诱导互动` 仍是 `platform_pending` | 需人工截图补原文 |
| M3 | 成本算不出来（未配置单价） | 评测前配 `.env` 价格，或明确写"未统计" |
| M4 | 无 CI（ruff + pytest 靠手动） | D10 |

### 低 / 已知但不修

| # | 问题 | 说明 |
|---|---|---|
| L1 | 《社区公约 2.0》为人工读图转录 | 存档内已声明：标点统一、断行合并，非官方机器文本 |
| L2 | 只用 Python 3.9 语法 | 见 §8 坑 1；不影响功能 |
| L3 | 无登录/多租户/支付 | 计划明确不做 |

---

## 7. 下一步（D2，2026-10-25）

**主题**：规则 v2 + Checker 加固 + 开始访谈

**任务**
1. 规则 40 → 45~50 条（补：酒类、教育培训、母乳替代、未成年人劝诱、低俗擦边细化）
2. 造 10 条 smoke test：3 条干净 + 7 条故意违规，记录漏检/误报
3. 把用户提供的真实笔记全部转成 `eval_cases`
4. 约 2–3 位访谈（小红书/抖音小卖家、代运营），写笔记

**验收**
- 10 条 smoke test 中抓到 ≥ 8 条已知违规
- 每条违规都有 `rule_id` + 原文 `quote`
- 2 份访谈笔记（每份 5–8 行）

**明确不做（防加戏）**
- 不做前端、不做改写、不做 API（那是 D3/D4/D5）
- 不为"规则条数"凑数：每条必须能逐字溯源或有明确出处

---

## 8. 踩过的坑（省下一个人的两小时）

**坑 1：DSH 自带 Python 3.12 装不了 pydantic**
`pydantic_core.so` 的签名与解释器 Team ID 不一致，`dlopen` 失败。
**解法**：用系统 `/usr/bin/python3`（3.9.6）建 venv，代码保持 3.9 兼容（`typing.List` 而非 `list[...]`，ruff 已配 `target-version=py39`）。

**坑 2：PDF 里的"康熙部首"字符**
《社区规范》PDF 用 `⻛/⻝/⻓` 代替「风/食/长」，码位不同导致 quote 永远匹配不上。
**解法**：`verify_rules.py` 里做部首映射 + NFKC + 去空白后再比对。

**坑 3：小红书规则页全是前端渲染**
`fe.xiaohongshu.com`、`school.xiaohongshu.com` 抓到的都是 SPA 空壳。
**解法**：只能靠用户导出的 PDF / 截图存档；`docs/sources/xiaohongshu/README.md` 写明了补录 SOP。

**坑 4：模型在"必须找出点什么"的压力下会硬凑**
真实笔记只应报 1 条，却报了一条不相干的绝对化用语。
**解法**：prompt 增加"判定纪律"与反例；低置信度分流；允许空结果 + human_review。

---

## 9. 下次开工 checklist（5 分钟）

1. 读本文件 §1 进度快照
2. `git log --oneline -5` 看最近改了什么
3. `python3 scripts/verify_rules.py` 确认规则库健康
4. `cd backend && .venv/bin/python -m pytest -q` 确认代码健康
5. 读 `docs/log.md` 最后一条"明天第一件事"
6. 定今天唯一的"必须完成"，写进 log


---

## 10. 后续更新（D1 之后）

**2026-10-24 晚：D3 的改写能力已提前完成**

| 变更 | 说明 |
|---|---|
| 新增 `backend/app/rewrite.py` | 按违规项改写、句子级 diff、自动复检、最多 2 轮 |
| CLI 新参数 | `--rewrite`（生成链路与 `--check` 链路均可） |
| 单测 | 6 → 7 个（新增句子级 diff 测试） |
| 规则库 | 39 → 40（新增 PLT-020 侮辱/道德绑架式营销） |

**实测**：`全网最低价！三天根治痘痘，国家级品质，加V领福利` 从 4 条违规 → 2 条（第一轮）→ 0 条（第二轮）。
**教训**：改写会把「根治」改成「改善」，仍然违规——**所以改完必须复检，不能只靠模型自称改好了**。

**评测样本**：真实笔记暂时收集困难，改为两条腿走路：
1. 合成 smoke test（开发自测用，标注"合成"，不进 eval_cases）
2. 真实样本靠日常积累，D7 前尽量凑到 12–15 条


**2026-10-24 晚（续）：D4 的 API 与 SQLite 已完成**

| 变更 | 说明 |
|---|---|
| 新增 `backend/app/db.py` | 五表 + seed + 幂等确认（UNIQUE 约束） |
| 新增 `backend/app/api.py` / `schemas.py` / `main.py` | 7 个接口，Pydantic 校验，LLM 异常统一 504 |
| 新增 `backend/tests/test_api.py` | 5 个接口测试，dependency override 替换 LLM |
| 单测总数 | 7 → **12** |

**接口**：`/health`、`/api/generate`、`/api/check`、`/api/rewrite`、`/api/confirm`、`/api/history`、`/api/rules`。
**规律**：`python -m app.db init` 建库并 seed 规则；`uvicorn app.main:app --reload` 起服务，`/docs` 有 Swagger。
