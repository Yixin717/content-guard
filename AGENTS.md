# AGENTS.md

> 给 AI 助手 / 新协作者的最短入口。项目全貌、当前状态、待办以 **[docs/handover-D4.md](docs/handover-D4.md)** 为准。

## 这是什么

Content Guard：小红书带货文案的「发布前合规体检」。贴文案 → 按 40 条可溯源规则逐句检查 →
每条违规指回原句 + 条款原文 → 逐条改写 → 人工确认导出。生成只是次入口。

- 线上：http://43.142.12.100/
- 仓库：`git@github.com:Yixin717/content-guard.git`
- 技术栈：FastAPI + SQLite + Next.js（静态导出）+ Nginx + systemd；模型 DeepSeek `deepseek-chat`

## 先读什么

1. **[docs/handover-D4.md](docs/handover-D4.md)** —— 当前权威：进度、代码地图、评测、待办、坑
2. **[docs/decisions.md](docs/decisions.md)** —— ADR-001~012，所有"为什么这么选"
3. **[docs/PRD.md](docs/PRD.md)** / **[eval/report-v1.md](eval/report-v1.md)** —— 产品定义与评测证据

历史快照（不要当现状）：`handover-D1/D2/D3.md`、`plan.md`。

## 硬约束（违反即返工）

1. **中文交流**；先讨论清楚再改代码，不要边讨论边动手。
2. **不改产品方向**：不要把它改成"AI 文案生成器"；不要加登录/支付；不要承诺平台一定通过。
3. **拒绝假数字**：页面上的 tokens / 耗时 / 条数只能来自接口或日志；mock 宁可不显示。
4. **问题必须可定位**：每条违规要有原句 + 条款原文；不要"另有 N 处需人工"这种没有落点的提示。
5. **改动数 = 违规数**：`len(violations) == len(rewrite.changes)`，编号 1:1。
6. **改 prompt 或规则必须重跑评测**：`backend/.venv/bin/python eval/run_eval.py`，
   并在 `eval/report-v1.md` 写清新旧口径；不要用测试集调参后只报好数字。
7. **分批交付**：做完一批先给用户验收，再开下一批。
8. **不要提交** `.env`、`*.db`、`eval/runs/`、`frontend/out/`、`node_modules/`。

## 常用命令

```bash
cd content-guard

# 后端
cd backend && .venv/bin/pytest -q          # 期望 29 passed
.venv/bin/ruff check app tests             # 期望 All checks passed
cd .. && python3 scripts/verify_rules.py   # 期望 0 警告 0 失败

# 前端
cd frontend && npm run dev                 # mock，localhost:3000
npm run build                              # 静态导出到 out/

# 评测（同一批 24 条；改口径时用 --from-raw 零成本重算）
backend/.venv/bin/python eval/run_eval.py --out eval/results-v1.1.md

# 部署（会备份旧站 + 数据库，健康检查失败即中断）
HOST=43.142.12.100 bash scripts/deploy.sh
```

## 目录速查

| 路径 | 内容 |
|---|---|
| `backend/app/` | 9 个接口、检查器、逐条改写、规则、prompt、DB |
| `frontend/app/` | 入口 / 选稿 / 工作台 / 历史 / 规则 + 错误页 |
| `eval/` | 评测脚本、报告、逐条结果（`runs/` 不入库） |
| `data/eval_cases/` | 24 条真实样本（JSON） |
| `docs/` | D4 交接、ADR、PRD、日志、部署、来源存档 |
| `rules.csv` | 规则唯一事实来源；改完必须 `verify_rules.py` |

## 现在还有什么没做

见 D4 §8。优先级：**P1-1 `uncertain` 展示出口 → P1-2 检索修复 → P1-3 规则 v2 → P1-4 新正样本**；
视频、简历条目需要用户本人做。
