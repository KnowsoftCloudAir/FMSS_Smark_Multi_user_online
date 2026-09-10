"""
Render / ASGI entrypoint.
Use: uvicorn app:app --host 0.0.0.0 --port $PORT
  or: gunicorn -k uvicorn.workers.UvicornWorker app:app
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND))

from main import app  # noqa: E402  FastAPI instance
