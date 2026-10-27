# 部署记录与环境说明

> 当前线上：**http://43.142.12.100/**（腾讯云 CVM，Ubuntu 24.04）

## 一、机器与路径

| 项 | 值 |
|---|---|
| 主机 | `ubuntu@43.142.12.100`（免密登录已配置，公钥在 `~/.ssh/id_ed25519`） |
| 系统 | Ubuntu 24.04.4 LTS · Python 3.12.3 · Nginx 1.24 |
| 静态文件 | `/var/www/content-guard`（Next.js 静态导出） |
| 后端代码 | `/home/ubuntu/content-guard/backend`（venv 在 `.venv`） |
| 规则文件 | `/home/ubuntu/content-guard/rules.csv` |
| 数据 | `/home/ubuntu/content-guard/data/content_guard.db`（SQLite） |
| 环境变量 | `/home/ubuntu/content-guard/backend/.env`（含 DeepSeek key，权限 600） |
| 服务 | `content-guard.service`（uvicorn 127.0.0.1:8000） |
| 站点配置 | `/etc/nginx/sites-available/content-guard` |

## 二、一键部署

```bash
cd content-guard
HOST=43.142.12.100 bash scripts/deploy.sh
```

脚本做六件事：构建（`USE_MOCK=0` + 同源 API）→ 备份旧站 → rsync → 装依赖 → 装 Nginx/systemd → 健康检查。
**自动备份**到服务器 `~/nginx-backup-<时间>` 与 `~/var-www-backup-<时间>`。

## 三、替换掉的旧项目

| 项 | 处理 |
|---|---|
| 旧站点 | `zero-to-tech`（Next.js，root 指 `/home/ubuntu/zero-to-tech/out`） |
| 旧后端 | `zero-backend.service`（fastapi，0.0.0.0:8000）→ **已 stop + disable** |
| 旧配置 | 已从 `sites-enabled` 移除，原文件仍在 `sites-available/default` |

> 旧项目的代码与静态文件**没有被删除**，只是不再对外服务。要恢复：`sudo systemctl enable --now zero-backend`，并把 `default` 重新软链回 `sites-enabled`。

## 四、验证过的项

- `GET /` `/drafts/` `/workbench/` `/rules/` `/history/` → 200
- `GET /health` → `{"status":"ok","model":"deepseek-chat","rules":40}`
- `POST /api/check`（经 Nginx）→ 2.0s，命中 3 条
- `POST /api/confirm` 两次 → 第二次 `idempotent: true`，`audit_id` 相同
- 公网 `:8000` → 不可访问（安全组已封）
- 页面数据来自线上 API（规则页显示 40 条，非 mock 的 7 条）
- 2026-10-25 重新部署（ADR-008）：`/api/check` → `2442/89`、`/api/rewrite` → `5406/406`，`journalctl -u content-guard | grep llm_usage` 两条日志与响应一致；页面状态条 `7,848 / 495`、`5.4s`

## 四之二、限流与备份（2026-10-26）

**限流**（`deploy/nginx-content-guard.conf`）
- 只作用于会调模型的四个接口：`/api/generate`、`/api/analyze`、`/api/check`、`/api/rewrite`
- 每个 IP：`10r/m`，允许 9 次突发 → 连发第 11 次开始 **429**
- 429 返回 JSON，前端会显示"请求太频繁了，请稍后再试"
- 历史 / 规则 / 确认 / 健康检查**不限流**

验收命令（空 body 不会真的调模型，只走校验）：

```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code} " -X POST http://43.142.12.100/api/analyze \
    -H "Content-Type: application/json" -d '{}'
done
# 期望：422 x 10，然后 429 x 2
```

**备份**
- 脚本：`scripts/backup_db.sh`（SQLite 在线 backup API，WAL 安全；备份后 `integrity_check` + 打表行数）
- 位置：`~/content-guard-backups/content_guard-<时间>.db.gz`，保留 14 天
- 定时：`/etc/cron.d/content-guard-backup`，每天 **03:00**；日志 `~/content-guard-backups/backup.log`
- 每次 `deploy.sh` 都会先跑一次备份

```bash
bash ~/content-guard/scripts/backup_db.sh          # 手动备份
ls -lt ~/content-guard-backups/*.db.gz | head -5  # 最近几次
tail -20 ~/content-guard-backups/backup.log
```

**恢复演练**（每月做一次，别等真出事才试）：

```bash
LATEST=$(ls -t ~/content-guard-backups/*.db.gz | head -1)
gzip -dc "$LATEST" > /tmp/restore.db
python3 -c "import sqlite3;db=sqlite3.connect('/tmp/restore.db');print(db.execute('PRAGMA integrity_check').fetchone()[0])"
```

真要恢复线上：`sudo systemctl stop content-guard` → 把解压的 db 覆盖到 `~/content-guard/data/content_guard.db`（先备份现场）→ 删掉同目录 `-wal/-shm` → `start` → `curl /health`。

> 边界：备份和数据库在**同一台机器**上，整机故障会一起丢。异地备份（对象存储）还没做。

## 四之三、2026-10-27 部署 v1.1 + 新首屏 + 规则库入口

**部署内容**
- 后端：`prompts.py` v1.1 判定纪律（B 例外 + G–M），与本地 md5 一致
- 前端：H1 `Content Guard`、副标题「发布前先过一遍，帮你稳稳过关！」；顶栏与状态条新增「规则库」入口
- 运维：`deploy.sh` 同步 `data/` 时排除 `*.db-*`，避免本地 `-wal/-shm` 覆盖线上库

**结果**
- 备份：`~/nginx-backup-2026-10-27-2031`、`~/var-www-backup-2026-10-27-2031`；数据库 `content_guard-2026-10-27-2032.db.gz`（32K）
- `/` `/workbench/` `/history/` `/rules/` 全部 200；`/health` → `rules: 40`
- 线上首页文案已是新版；首页有 2 个 `/rules/` 入口（顶栏 + 状态条）
- 线上 `prompts.py` md5 与本地一致（`8f8d84a9…`）

> 注意：`deploy.sh` 会用 `USE_MOCK=0` 重新构建 `frontend/out`；本地静态预览若要继续用 mock，
> 需要再跑一次 `npm run build`（默认 mock）。

## 五、常用运维命令

```bash
ssh ubuntu@43.142.12.100
sudo systemctl status content-guard      # 服务状态
sudo journalctl -u content-guard -n 50   # 后端日志
sudo journalctl -u content-guard -f | grep llm_usage   # 每次请求的 tokens/耗时（ADR-008，可与页面状态条对账）
sudo tail -f /var/log/nginx/access.log   # 访问日志
sudo systemctl restart content-guard     # 重启后端
sudo nginx -t && sudo systemctl reload nginx
```

> 若线上状态条仍显示写死的 `9,254 / 15.7s`，说明跑的还是 ADR-008 之前的版本，重新部署即可。
> 部署后，页面数字应等于该任务 `llm_usage path=/api/check …` 与 `path=/api/rewrite …` 两条日志的
> `tokens_in/tokens_out` 之和（口径见 ADR-008）。

## 六、还没做的

- **HTTPS**：目前是 HTTP。需要域名 + 证书（腾讯云免费 DV），配好后 80 → 301 → 443。用户已决定暂不做。
- **告警**：备份失败、服务挂掉、证书过期都没有主动通知；目前只能看日志。可选：每日 `curl /health` + 检查备份文件日期，失败发邮件/Server 酱。
- **异地备份**：备份与数据库同机，整机故障会一起丢；对象存储未接。
- ~~**限流**：可用 Nginx `limit_req`~~ → ✅ 2026-10-26 已完成（10 次/分钟，第 11 次 429）
- ~~**备份**：SQLite 未做定时备份~~ → ✅ 2026-10-26 已完成（每日 03:00，保留 14 天，含恢复演练）。
- ~~**v1.1 部署**~~ → ✅ 2026-10-27 已完成（见 §四之三）。
