#!/usr/bin/env bash
# 一键部署到腾讯云 CVM（Ubuntu）
# 前置：本机已能 `ssh ubuntu@<HOST>` 免密登录
# 用法：HOST=43.142.12.100 bash scripts/deploy.sh
set -euo pipefail

HOST="${HOST:?需要设置 HOST，例如 HOST=43.142.12.100}"
USER_NAME="${USER_NAME:-ubuntu}"
REMOTE="ssh ${USER_NAME}@${HOST}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> 1/6 本地构建前端（静态导出）"
cd "$ROOT/frontend"
# 线上必须用真实接口：USE_MOCK=0，API_BASE 为空 → 走同源 /api/（Nginx 反代）
NEXT_PUBLIC_USE_MOCK=0 NEXT_PUBLIC_API_BASE= npm run build

echo "==> 2/6 备份旧站点并准备目录"
$REMOTE "STAMP=\$(date +%F-%H%M); sudo cp -a /etc/nginx/sites-available ~/nginx-backup-\$STAMP 2>/dev/null || true; sudo cp -a /var/www ~/var-www-backup-\$STAMP 2>/dev/null || true; echo \"已备份到 ~/nginx-backup-\$STAMP 与 ~/var-www-backup-\$STAMP\""
$REMOTE "sudo mkdir -p /var/www/content-guard && sudo chown -R ${USER_NAME}:${USER_NAME} /var/www/content-guard && mkdir -p ~/content-guard"

echo "==> 3/6 同步静态文件与后端代码"
rsync -az --delete "$ROOT/frontend/out/" "${USER_NAME}@${HOST}:/var/www/content-guard/"
rsync -az --exclude '.venv' --exclude '__pycache__' --exclude '*.db' \
  "$ROOT/backend/" "${USER_NAME}@${HOST}:~/content-guard/backend/"
rsync -az "$ROOT/rules.csv" "${USER_NAME}@${HOST}:~/content-guard/rules.csv"
rsync -az "$ROOT/data/" --exclude '*.db' "${USER_NAME}@${HOST}:~/content-guard/data/"
scp "$ROOT/.env" "${USER_NAME}@${HOST}:~/content-guard/backend/.env"

echo "==> 4/6 安装 Python 依赖"
$REMOTE "cd ~/content-guard/backend && (test -d .venv || python3 -m venv .venv) && .venv/bin/pip install --quiet -r requirements.txt"

echo "==> 5/6 安装 Nginx 站点与 systemd 服务"
scp "$ROOT/deploy/nginx-content-guard.conf" "${USER_NAME}@${HOST}:/tmp/content-guard.nginx"
scp "$ROOT/deploy/content-guard.service" "${USER_NAME}@${HOST}:/tmp/content-guard.service"
$REMOTE "sudo mv /tmp/content-guard.nginx /etc/nginx/sites-available/content-guard \
  && sudo ln -sf /etc/nginx/sites-available/content-guard /etc/nginx/sites-enabled/content-guard \
  && sudo rm -f /etc/nginx/sites-enabled/default \
  && sudo nginx -t \
  && sudo systemctl reload nginx \
  && sudo mv /tmp/content-guard.service /etc/systemd/system/content-guard.service \
  && sudo systemctl daemon-reload \
  && sudo systemctl enable --now content-guard \
  && sudo systemctl restart content-guard"

echo "==> 6/6 健康检查"
sleep 3
curl -s "http://${HOST}/health" || { echo "健康检查失败，登录看日志：sudo journalctl -u content-guard -n 50"; exit 1; }
echo
echo "✅ 部署完成：http://${HOST}/"
