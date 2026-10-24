"""全局配置：从仓库根目录的 .env 读取，缺省值保证本地能跑。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# backend/app/config.py -> backend/app -> backend -> 仓库根
REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


class Settings:
    api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    app_env: str = os.getenv("APP_ENV", "local")

    # 价格只在评测里用来算成本；未配置时按 0 处理，绝不猜
    price_input_per_m: float = float(os.getenv("DEEPSEEK_PRICE_INPUT", "0") or 0)
    price_output_per_m: float = float(os.getenv("DEEPSEEK_PRICE_OUTPUT", "0") or 0)

    rules_csv: Path = REPO_ROOT / "rules.csv"
    rules_json: Path = REPO_ROOT / "data" / "rules.json"
    out_dir: Path = REPO_ROOT / "out"

    @classmethod
    def require_key(cls) -> str:
        if not cls.api_key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY，请先运行 bash scripts/init_env.sh")
        return cls.api_key


settings = Settings()
