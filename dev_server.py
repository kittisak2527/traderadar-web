"""Run the dashboard locally:  python dev_server.py  ->  http://localhost:8000

Serves the static front-end and the same /api routes that Vercel runs.
Needs: pip install fastapi uvicorn numpy
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "api"))

import uvicorn  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from index import app  # noqa: E402

app.mount("/static", StaticFiles(directory=os.path.join(ROOT, "static")), name="static")


@app.get("/")
def home():
    return FileResponse(os.path.join(ROOT, "index.html"))


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", 8000)))
