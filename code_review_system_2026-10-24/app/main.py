import base64
import binascii
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.knowledge.routes import router as knowledge_router


app = FastAPI(
    title="智能代码审查与漏洞修复系统",
    description="基于大语言模型与静态分析的代码审查系统基础框架",
    version="0.1.0",
)


LAN_PASSWORD = os.environ.get("CODE_REVIEW_LAN_PASSWORD")


@app.middleware("http")
async def require_mobile_login(request: Request, call_next):
    if LAN_PASSWORD:
        authorization = request.headers.get("authorization", "")
        scheme, _, encoded = authorization.partition(" ")
        try:
            credentials = base64.b64decode(encoded, validate=True).decode("utf-8")
            username, password = credentials.split(":", 1)
        except (ValueError, UnicodeDecodeError, binascii.Error):
            username, password = "", ""

        if (
            scheme.lower() != "basic"
            or not secrets.compare_digest(username, "review")
            or not secrets.compare_digest(password, LAN_PASSWORD)
        ):
            return PlainTextResponse(
                "需要登录才能访问代码审查系统。",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Code Review System"'},
            )

        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return PlainTextResponse("请求来源不匹配。", status_code=403)

    return await call_next(request)

app.include_router(router, prefix="/api")
app.include_router(knowledge_router, prefix="/api")

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="frontend")


@app.get("/", tags=["系统"])
def root() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")
