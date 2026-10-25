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

- **HTTPS**：目前是 HTTP。需要域名 + 证书（腾讯云免费 DV），配好后 80 → 301 → 443。
- **限流**：`/api/generate` 无鉴权，公网可被刷（每次约 2 分钱）。可用 Nginx `limit_req` 按 IP 限速。
- **备份**：SQLite 未做定时备份。
