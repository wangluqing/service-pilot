import logging
import os
import time
from contextvars import ContextVar
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .domain import AnalyzeRequest, TicketAnalysis, TicketCreate
from .engine import analyze_rules
from .llm import LLMCallError, analyze_llm
from .storage import find_order, list_tickets, save_ticket

load_dotenv()
logger = logging.getLogger("servicepilot")
logger.setLevel(logging.INFO)
app = FastAPI(title="ServicePilot V0.2", version="0.2.0")
ROOT = Path(__file__).resolve().parents[2]
REQUEST_ID_HEADER = "X-Request-ID"
request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
LLM_ERROR_RESPONSES = {
    "config_missing": (503, "LLM模式未配置DEEPSEEK_API_KEY"),
    "timeout": (504, "模型服务超时"),
    "http_error": (502, "模型服务调用失败"),
    "output_invalid": (502, "模型输出未通过校验"),
}
FALLBACK_KINDS = {"timeout", "http_error", "output_invalid"}


def safe_analysis_mode() -> str | None:
    """Return only recognized analysis modes for request metadata logs."""

    mode = os.getenv("SP_MODE", "rules").strip().lower()
    return mode if mode in {"rules", "llm"} else None


def real_llm_web_authorized() -> bool:
    """Return whether an operator explicitly authorized local Web LLM testing."""

    return os.getenv("SP_REAL_LLM_WEB_AUTHORIZED", "false").strip().lower() == "true"


@app.middleware("http")
async def request_metadata(request: Request, call_next):
    """Attach a server-generated request ID and emit one allowlisted log event."""

    request_id = str(uuid4())
    token = request_id_context.set(request_id)
    started = time.perf_counter()
    error_kind = None
    try:
        try:
            response = await call_next(request)
        except Exception:
            error_kind = "unhandled_exception"
            response = JSONResponse(status_code=500, content={"detail": "Internal server error"})

        response.headers[REQUEST_ID_HEADER] = request_id
        if error_kind is None and response.status_code >= 400:
            error_kind = f"http_{response.status_code}"

        route = request.scope.get("route")
        route_template = getattr(route, "path", None) or "<unmatched>"
        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "http_request_complete request_id=%s route=%s status_code=%s "
            "duration_ms=%.3f mode=%s error_kind=%s",
            request_id,
            route_template,
            response.status_code,
            duration_ms,
            safe_analysis_mode(),
            error_kind,
        )
        return response
    finally:
        request_id_context.reset(token)


def db_path() -> str:
    """解析 SQLite 路径。

    @returns 数据库文件路径
    """

    value = os.getenv("SP_DB_PATH", "data/servicepilot.db")
    path = Path(value)
    return str(path if path.is_absolute() else ROOT / path)


def read_fallback() -> str:
    """读取降级开关。只有显式 rules 才允许降级。

    @returns off 或 rules
    """

    value = os.getenv("SP_LLM_FALLBACK", "off").strip().lower()
    if value in {"", "off"}:
        return "off"
    if value == "rules":
        return "rules"
    raise HTTPException(500, "SP_LLM_FALLBACK配置无效")


def raise_llm_http(exc: LLMCallError) -> None:
    """把模型错误转成不含密钥和原文的 HTTP 错误。

    @param exc - 已分类的模型错误
    """

    status, detail = LLM_ERROR_RESPONSES.get(exc.kind, (502, "模型服务不可用"))
    logger.warning("llm call failed kind=%s", exc.kind)
    raise HTTPException(status, detail) from None


async def run_analysis(message: str) -> TicketAnalysis:
    """按 SP_MODE 分析工单。规则模式不调用模型。

    @param message - 用户原文
    @returns 分析结果
    """

    mode = os.getenv("SP_MODE", "rules").strip().lower()
    if mode == "rules":
        return analyze_rules(message)
    if mode != "llm":
        raise HTTPException(500, "SP_MODE配置无效")
    fallback = read_fallback()
    try:
        return await analyze_llm(message)
    except LLMCallError as exc:
        if exc.kind in FALLBACK_KINDS and fallback == "rules":
            logger.warning("llm fallback to rules kind=%s", exc.kind)
            analysis = analyze_rules(message)
            return analysis.model_copy(update={"source": "llm_fallback_rules"})
        raise_llm_http(exc)


@app.get("/", response_class=HTMLResponse)
def home():
    return (ROOT / "web" / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "mode": os.getenv("SP_MODE", "rules"),
        "real_llm_web_authorized": real_llm_web_authorized(),
    }


@app.get("/orders/{order_id}")
def order(order_id: str):
    row = find_order(order_id.upper())
    if not row:
        raise HTTPException(404, "模拟订单不存在")
    return row


@app.post("/analyze", response_model=TicketAnalysis)
async def analyze(req: AnalyzeRequest):
    return await run_analysis(req.message)


@app.post("/tickets")
async def create_ticket(req: TicketCreate):
    analysis = await run_analysis(req.message)
    ticket_id = save_ticket(db_path(), req.message, analysis.model_dump_json(), req.confirmed_by)
    return {"ticket_id": ticket_id, "analysis": analysis, "status": "已记录（教学模拟人工确认）"}


@app.get("/tickets")
def tickets():
    return list_tickets(db_path())
