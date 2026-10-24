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

**明天第一件事**：规则扩到 45–50 条 + 10 条 smoke test 记录漏检/误报。
