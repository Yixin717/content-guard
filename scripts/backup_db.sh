#!/usr/bin/env bash
# 每日备份 SQLite（服务器上跑；由 /etc/cron.d/content-guard-backup 触发）
#
# 为什么用 Python 的 backup API 而不是 cp：
# - 库开了 WAL，直接 cp 可能拿到"一半写一半没写"的文件；
# - sqlite3.backup() 是 SQLite 官方的在线备份接口，会自己处理锁和 WAL。
#
# 用法：bash scripts/backup_db.sh
#   DB_PATH  默认 ~/content-guard/data/content_guard.db
#   OUT_DIR  默认 ~/content-guard-backups
#   KEEP_DAYS 默认 14 天
set -euo pipefail

DB_PATH="${DB_PATH:-$HOME/content-guard/data/content_guard.db}"
OUT_DIR="${OUT_DIR:-$HOME/content-guard-backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date +%F-%H%M)"
TARGET="$OUT_DIR/content_guard-$STAMP.db.gz"
TMP="$OUT_DIR/.tmp-$STAMP.db"

mkdir -p "$OUT_DIR"

if [ ! -f "$DB_PATH" ]; then
  echo "[backup] 数据库不存在：$DB_PATH" >&2
  exit 1
fi

python3 - "$DB_PATH" "$TMP" <<'PY'
import sqlite3
import sys

src_path, dst_path = sys.argv[1], sys.argv[2]
src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
dst = sqlite3.connect(dst_path)
try:
    with dst:
        src.backup(dst)
    status = dst.execute("PRAGMA integrity_check").fetchone()[0]
    if status != "ok":
        raise SystemExit(f"[backup] 备份文件自检失败：{status}")
    tables = [r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    counts = {t: dst.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    print(f"[backup] 自检通过，表：{counts}")
finally:
    src.close()
    dst.close()
PY

gzip -c "$TMP" > "$TARGET"
rm -f "$TMP"

# 只保留最近 N 天；备份不是越多越好，磁盘也要钱
find "$OUT_DIR" -name 'content_guard-*.db.gz' -mtime +"$KEEP_DAYS" -delete

echo "[backup] 完成：$TARGET（$(du -h "$TARGET" | cut -f1)），保留 $KEEP_DAYS 天"
