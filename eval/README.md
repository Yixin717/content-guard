# 评测（eval）

> 目的：回答「它到底准不准」，而不是在简历上写一个没有定义的百分比。
> 详细的方法与取舍见 `docs/handover-D3.md` §6.1；面试版解读见 `eval/report-v1.md`。

## 一次评测的完整流程

```
data/eval_cases/inbox.md     你粘真实笔记（格式见文件顶部）
        │  python3 eval/import_inbox.py
        ▼
data/eval_cases/NNN-短名.json   样本（draft + 空 gold）
        │  AI 按 rules.csv 预标注 → 写入 proposed[]
        ▼
eval/label-sheet.md          逐条勾选表（同意 / 不同意+理由 / 拿不准）
        │  你勾完 → 合并进 ground_truth[]（只收「同意」）
        ▼
python3 eval/run_eval.py     调本地 analyze，算指标
        │
        ├─ eval/runs/<run_id>/raw.json      原始响应（可重算，不入库）
        ├─ eval/runs/<run_id>/metrics.json  指标明细（不入库）
        └─ eval/results-v1.md               数据报告（入库）
                │
                ▼
        eval/report-v1.md    面试版：方法 + 数字 + 错误归因 + 局限（手写，引用 results）
```

## 命令

```bash
cd content-guard

# 1. 导入笔记（先 --dry-run 看一眼）
python3 eval/import_inbox.py --dry-run
python3 eval/import_inbox.py

# 2. 生成标注表（需要样本里已有 proposed；预标注由 AI 完成）
backend/.venv/bin/python eval/label_sheet.py

# 3. 跑评测（默认只跑 main 层；用 venv 的 python，依赖 fastapi/httpx）
backend/.venv/bin/python eval/run_eval.py
backend/.venv/bin/python eval/run_eval.py --layer all
backend/.venv/bin/python eval/run_eval.py --ids 001-zara-jacket

# 4. 不重新调模型，只按新口径重算（改指标定义时用）
backend/.venv/bin/python eval/run_eval.py --from-raw eval/runs/<run_id>/raw.json
```

## 文件

| 文件 | 作用 | 入库 |
|---|---|---|
| `eval/import_inbox.py` | inbox.md → 样本 JSON，严格解析、不猜 | ✅ |
| `eval/label_sheet.py` | 样本 → 逐条勾选表（含「边界项」供确认方向） | ✅ |
| `eval/run_eval.py` | 调 analyze、算指标、生成 `results-v1.md` | ✅ |
| `eval/results-v1.md` | v1 基线数据报告（**不要手改**） | ✅ |
| `eval/results-v1.1.md` | v1.1（改 prompt 后）数据报告 | ✅ |
| `eval/report-v1.md` | 面试版报告：方法、v1→v1.1 对比、错误归因、规则缺口、局限 | ✅ |
| `eval/label-sheet.md` | 给作者勾选的工作文件 | ✅（勾完即归档） |
| `eval/runs/` | 原始响应、指标 JSON、评测专用 SQLite | ❌ 被 `.gitignore` 忽略 |

## 口径（改了要同步改报告）

- **命中** = `rule_id` 严格相等 **且** `quote` 归一化（去空白/全半角/部首差异）后相等或互相包含。
- **召回** = 命中处数 ÷ gold 处数；**误报率** = （报出 − 命中）÷ 报出。
- **引用正确率** = quote 在原文逐字出现 ∧ rule_id 存在 ∧ clause 与 rules.csv 一致（纯机器校验）。
- `uncertain`（confidence < 0.7）**不计入召回**，单独报「灰区」：页面不展示它，对用户等于漏。
- **边界项**（`edge_items`，需要资质/语境才能判，如「护眼」「母婴级」「自评第一名」）不进 gold、也不算误报；
  模型报了记「边界命中」，从 FP 分子分母里同时剔除，另表统计（见报告第 4.4 节）。
- 作者复核时可以给边界项标 `author_verdict: violation`（「我认为这就是违规」）：能挂到现有规则的升进 gold；
  挂不上的留在 `edge_items`，作为**规则缺口**在报告里单列——这是下一版补规则的直接依据，不硬套条款。
- `analyze` 对原文做**两遍独立检查取并集**，所以召回高于单次检查，误报也可能更高。

## 成本与限流

- 每条样本 3 次模型调用（两次检查 + 一次改写），12 条约 0.5 元（按当时实测）。
- 本地跑不受公网限流；公网接口 10 次/分钟，只用于抽 3 条做一致性复核。
- `--from-raw` 不花钱；改指标定义时优先用它。

## 别踩的坑

- 样本放 `data/eval_cases/`，**不要**放 `eval/`（早期 `.gitignore` 的 `eval/*.json` 会静默吃掉，见 backlog B-009；本次已改为忽略 `eval/runs/`）。
- 评测写独立的 `eval/runs/<id>/eval.db`，不碰本地 `data/content_guard.db` 的历史记录。
- 样本 JSON 里的 `ground_truth` 必须是**双方一致**的项；`run_eval.py` 会先自检（规则是否存在、quote 是否在原文里），不通过不会调模型。
