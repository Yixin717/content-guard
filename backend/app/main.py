"""uvicorn 入口：uvicorn app.main:app --reload"""

from .api import app  # noqa: F401

__all__ = ["app"]
