"""让 `import app` 在 pytest 里可用（backend 目录加入 sys.path）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
