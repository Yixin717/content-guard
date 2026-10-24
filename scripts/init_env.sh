#!/usr/bin/env bash
# 交互式写入 .env 并验证 DeepSeek key 是否可用。
# 用法：bash scripts/init_env.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"

echo "==> 初始化 $ENV_FILE"
if [[ -f "$ENV_FILE" ]]; then
  read -r -p ".env 已存在，覆盖？[y/N] " ans
  [[ "${ans:-N}" =~ ^[Yy]$ ]] || { echo "已取消"; exit 0; }
fi

read -r -s -p "请粘贴 DeepSeek API key（输入不会回显）: " KEY
echo
[[ -n "${KEY:-}" ]] || { echo "key 为空，退出"; exit 1; }

umask 077
cat > "$ENV_FILE" <<ENVEOF
DEEPSEEK_API_KEY=${KEY}
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
APP_ENV=local
ENVEOF
unset KEY
chmod 600 "$ENV_FILE"
echo "==> 已写入（权限 600），文件不会被 git 跟踪"

echo "==> 验证 key..."
if ! command -v curl >/dev/null; then echo "缺少 curl，跳过验证"; exit 0; fi
set +e
resp="$(curl -sS -m 20 https://api.deepseek.com/user/balance \
  -H "Authorization: Bearer $(grep '^DEEPSEEK_API_KEY=' "$ENV_FILE" | cut -d= -f2-)")"
code=$?
set -e
if [[ $code -ne 0 ]]; then
  echo "❌ 网络请求失败（curl 退出码 $code）"; exit 1
fi
if [[ "$resp" == *"is_available"* ]]; then
  echo "✅ key 有效。余额信息："
  echo "$resp"
else
  echo "⚠️ 返回内容异常（key 可能无效）："
  echo "${resp:0:300}"
  exit 1
fi

echo
echo "下一步：进入 D1，写 FastAPI 脚手架与 CLI"
