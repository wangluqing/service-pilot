from pathlib import Path


WEB_PAGE = Path(__file__).resolve().parents[1] / "web" / "index.html"


def page_text() -> str:
    return WEB_PAGE.read_text(encoding="utf-8")


def test_web_source_and_error_mappings_are_explicit():
    page = page_text()

    for source, label in (
        ("rules", "规则分析"),
        ("llm", "LLM 分析"),
        ("llm_fallback_rules", "LLM 失败后规则降级"),
    ):
        assert source in page
        assert label in page

    for status in ("422", "500", "502", "503", "504"):
        assert f'{status}: [' in page
    assert "网络错误" in page
    assert "响应格式错误" in page


def test_web_renders_ticket_analysis_fields_and_review_boundaries():
    page = page_text()

    for field in (
        "category",
        "summary",
        "order_id",
        "order_found",
        "warranty_status",
        "priority",
        "department",
        "missing_information",
        "needs_human_review",
        "reasons",
        "source",
    ):
        assert f"data.{field}" in page

    assert "所有分析结果均需人工确认" in page
    assert "不提供自动审批、退款、赔偿、保修批准或自动派遣" in page
    assert "真实 DeepSeek 调用状态为 NOT_AUTHORIZED" in page


def test_web_uses_safe_dom_rendering_and_no_browser_persistence():
    page = page_text()

    assert ".textContent" in page
    assert "createElement" in page
    assert "innerHTML" not in page
    assert "localStorage" not in page
    assert "sessionStorage" not in page
    assert "console." not in page
    assert "https://" not in page
    assert "http://" not in page


def test_web_handles_request_id_and_prevents_duplicate_submit():
    page = page_text()

    assert 'response.headers.get("X-Request-ID")' in page
    assert "analyzeButton.disabled = true" in page
    assert 'select id="mode" aria-describedby="mode-note" disabled' in page


def test_web_syncs_backend_mode_and_blocks_unauthorized_llm():
    page = page_text()

    assert 'fetch("/health"' in page
    assert "backendMode = health.mode" in page
    assert "modeSelect.value = backendMode" in page
    assert "if (!canAnalyze())" in page
    assert "为避免真实模型调用，本页面已禁止分析" in page
    assert "previousMode !== backendMode" in page
    assert "resetOutput()" in page


def test_web_requires_explicit_authorization_for_llm_mode():
    page = page_text()

    assert "health.real_llm_web_authorized === true" in page
    assert 'backendMode === "llm" && llmWebAuthorized' in page
    assert "if (llmWebAuthorized)" in page
    assert "本地 Web 测试已由操作人员显式授权" in page
    assert "analyzeButton.disabled = !canAnalyze()" in page
