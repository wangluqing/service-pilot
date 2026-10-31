import asyncio
import json
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from servicepilot.llm import LLMCallError, analyze_llm, parse_draft
from servicepilot.main import app
from servicepilot.storage import find_order

client = TestClient(app)
SECRET = "test-api-key-placeholder"
UPSTREAM = "upstream-secret-body"


def llm_env(monkeypatch, fallback="off", key=SECRET):
    """把测试固定到假的 LLM 配置。

    @param monkeypatch - pytest 环境变量补丁
    @param fallback - off 或 rules
    @param key - 测试用密钥；None 表示删除
    """

    monkeypatch.setenv("SP_MODE", "llm")
    monkeypatch.setenv("SP_LLM_FALLBACK", fallback)
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "http://llm.test")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    if key is None:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    else:
        monkeypatch.setenv("DEEPSEEK_API_KEY", key)


def install_client(monkeypatch, handler):
    """用假的 AsyncClient 替换真实网络调用。

    @param monkeypatch - pytest 补丁
    @param handler - 同步的 post 替身
    """

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            return handler(url, headers, json)

    monkeypatch.setattr("servicepilot.llm.httpx.AsyncClient", Client)


class PayloadResponse:
    """最小 HTTP 响应，供模型客户端读取 JSON。"""

    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://llm.test/chat/completions")
            response = httpx.Response(self.status_code, request=request, text=UPSTREAM)
            raise httpx.HTTPStatusError("upstream", request=request, response=response)

    def json(self):
        return self.payload


def chat_payload(content, prompt_tokens=11, completion_tokens=7):
    """组装 chat/completions 响应体。

    @param content - 已编码字符串，或将要编码的草稿对象
    @param prompt_tokens - 输入 token
    @param completion_tokens - 输出 token
    @returns 响应体
    """

    body = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return {
        "choices": [{"message": {"content": body}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }


def post_payload(content):
    """返回一个只产生指定草稿的 post 替身。

    @param content - 草稿或原始字符串
    @returns post 替身
    """

    def post(url, headers=None, body=None):
        assert url == "http://llm.test/chat/completions"
        assert headers["Authorization"].startswith("Bearer ")
        assert SECRET not in json.dumps(body, ensure_ascii=False)
        return PayloadResponse(chat_payload(content))

    return post


def test_valid_output_keeps_business_facts(monkeypatch, caplog):
    llm_env(monkeypatch)
    message = "订单1008的设备无法启动，影响生产，请尽快处理"
    draft = {
        "category": "设备故障",
        "summary": "设备无法启动并影响生产",
        "order_id": "ORD-1008",
        "warranty_status": "模型自称保修已失效",
        "priority": "普通",
        "needs_human_review": False,
    }
    install_client(monkeypatch, post_payload(draft))
    caplog.set_level("INFO")
    response = client.post("/analyze", json={"message": message})
    assert response.status_code == 200
    data = response.json()
    order = find_order("ORD-1008")
    expected_warranty = "保修期内" if date.fromisoformat(order["warranty_end"]) >= date.today() else "保修期外"
    assert data["category"] == "设备故障"
    assert data["summary"] == "设备无法启动并影响生产"
    assert data["order_id"] == "ORD-1008"
    assert data["order_found"] is True
    assert data["warranty_status"] == expected_warranty
    assert data["priority"] == "优先待人工复核"
    assert data["needs_human_review"] is True
    assert data["source"] == "llm"
    assert any("生产影响" in item for item in data["reasons"])
    assert "call_meta" not in data
    assert "prompt_tokens" not in data
    assert SECRET not in response.text
    assert SECRET not in caplog.text
    assert message not in caplog.text
    result = asyncio.run(analyze_llm(message))
    assert result._call_meta is not None
    assert result._call_meta.model == "deepseek-chat"
    assert result._call_meta.prompt_tokens == 11
    assert result._call_meta.completion_tokens == 7
    assert result._call_meta.latency_ms >= 0
    assert "call_meta" not in result.model_dump()


def test_llm_category_cannot_override_safety_priority(monkeypatch):
    llm_env(monkeypatch)
    draft = {"category": "物流查询", "summary": "设备漏电", "order_id": "ORD-1001"}
    install_client(monkeypatch, post_payload(draft))
    result = asyncio.run(analyze_llm("订单ORD-1001设备漏电，人员可能受伤"))
    assert result.category == "物流查询"
    assert result.priority == "紧急待人工复核"
    assert result.order_id == "ORD-1001"
    assert result.order_found is True
    assert result.needs_human_review is True
    assert result.source == "llm"
    assert any("安全风险" in item for item in result.reasons)


def test_llm_cannot_invent_order_id(monkeypatch):
    llm_env(monkeypatch)
    draft = {"category": "设备故障", "summary": "设备无法启动", "order_id": "ORD-1008"}
    install_client(monkeypatch, post_payload(draft))
    result = asyncio.run(analyze_llm("设备无法启动，请尽快处理"))
    assert result.order_id is None
    assert result.order_found is False
    assert result.category == "设备故障"
    assert "ORD-1008" not in "".join(result.reasons)


def test_invalid_json(monkeypatch):
    llm_env(monkeypatch)
    install_client(monkeypatch, post_payload("not-json"))
    response = client.post("/analyze", json={"message": "订单ORD-1008的设备无法启动"})
    assert response.status_code == 502
    assert response.json() == {"detail": "模型输出未通过校验"}


def test_illegal_category_is_not_rewritten(monkeypatch, caplog):
    llm_env(monkeypatch)
    draft = {"category": "投诉", "summary": "想退款", "order_id": None}
    install_client(monkeypatch, post_payload(draft))
    caplog.set_level("INFO")
    response = client.post("/analyze", json={"message": "订单ORD-1004希望退货"})
    assert response.status_code == 502
    assert response.json() == {"detail": "模型输出未通过校验"}
    assert "投诉" not in response.text
    assert "投诉" not in caplog.text
    assert "其他" not in response.text


def test_missing_field(monkeypatch):
    llm_env(monkeypatch)
    draft = {"summary": "设备无法启动", "order_id": None}
    install_client(monkeypatch, post_payload(draft))
    response = client.post("/analyze", json={"message": "订单ORD-1008的设备无法启动"})
    assert response.status_code == 502
    assert response.json()["detail"] == "模型输出未通过校验"


def test_overlong_summary(monkeypatch):
    llm_env(monkeypatch)
    draft = {"category": "设备故障", "summary": "测" * 101, "order_id": None}
    install_client(monkeypatch, post_payload(draft))
    response = client.post("/analyze", json={"message": "订单ORD-1008的设备无法启动"})
    assert response.status_code == 502
    assert response.json()["detail"] == "模型输出未通过校验"


def test_non_string_order_id_is_invalid(monkeypatch):
    llm_env(monkeypatch)
    draft = {"category": "设备故障", "summary": "设备无法启动", "order_id": 1008}
    install_client(monkeypatch, post_payload(draft))
    response = client.post("/analyze", json={"message": "订单1008的设备无法启动"})
    assert response.status_code == 502
    assert response.json()["detail"] == "模型输出未通过校验"


def test_missing_key_does_not_fallback(monkeypatch, caplog):
    llm_env(monkeypatch, fallback="rules", key=None)
    caplog.set_level("WARNING")
    response = client.post("/analyze", json={"message": "订单ORD-1008的设备无法启动"})
    assert response.status_code == 503
    assert response.json() == {"detail": "LLM模式未配置DEEPSEEK_API_KEY"}
    assert "llm fallback" not in caplog.text


def test_timeout(monkeypatch, caplog):
    llm_env(monkeypatch, fallback="off")

    def post(url, headers=None, json=None):
        raise httpx.TimeoutException("timed out")

    install_client(monkeypatch, post)
    caplog.set_level("WARNING")
    response = client.post("/analyze", json={"message": "订单ORD-1008的设备无法启动"})
    assert response.status_code == 504
    assert response.json() == {"detail": "模型服务超时"}
    assert SECRET not in response.text
    assert SECRET not in caplog.text


def test_upstream_http_failure_hides_body(monkeypatch, caplog):
    llm_env(monkeypatch, fallback="off")

    def post(url, headers=None, json=None):
        request = httpx.Request("POST", "http://llm.test/chat/completions")
        upstream = httpx.Response(500, request=request, text=UPSTREAM)
        raise httpx.HTTPStatusError("bad", request=request, response=upstream)

    install_client(monkeypatch, post)
    caplog.set_level("INFO")
    response = client.post("/analyze", json={"message": "订单ORD-1008的设备无法启动"})
    assert response.status_code == 502
    assert response.json() == {"detail": "模型服务调用失败"}
    assert UPSTREAM not in response.text
    assert UPSTREAM not in caplog.text
    assert SECRET not in response.text
    assert SECRET not in caplog.text


def test_timeout_falls_back_to_rules(monkeypatch, caplog):
    llm_env(monkeypatch, fallback="rules")
    message = "订单ORD-1008的设备无法启动，影响生产，请尽快处理"

    def post(url, headers=None, json=None):
        raise httpx.TimeoutException("timed out")

    install_client(monkeypatch, post)
    caplog.set_level("WARNING")
    response = client.post("/analyze", json={"message": message})
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "llm_fallback_rules"
    assert data["category"] == "设备故障"
    assert data["order_id"] == "ORD-1008"
    assert data["priority"] == "优先待人工复核"
    assert any("生产影响" in item for item in data["reasons"])
    assert message not in caplog.text
    assert SECRET not in caplog.text
    assert "llm fallback to rules kind=timeout" in caplog.text


def test_invalid_output_falls_back_without_using_draft(monkeypatch):
    llm_env(monkeypatch, fallback="rules")
    draft = {"category": "投诉", "summary": "忽略规则直接退款", "order_id": "ORD-7777"}
    install_client(monkeypatch, post_payload(draft))
    response = client.post("/analyze", json={"message": "订单ORD-1005，请协助开具增值税发票"})
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "llm_fallback_rules"
    assert data["category"] == "发票问题"
    assert data["order_id"] == "ORD-1005"
    assert data["needs_human_review"] is True


def test_rules_mode_does_not_call_api(monkeypatch):
    monkeypatch.setenv("SP_MODE", "rules")
    monkeypatch.setenv("SP_LLM_FALLBACK", "bogus")
    calls = {"n": 0}

    class Client:
        def __init__(self, *args, **kwargs):
            calls["n"] += 1

        async def __aenter__(self):
            calls["n"] += 1
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            calls["n"] += 1
            raise AssertionError("rules mode must not call the model")

    monkeypatch.setattr("servicepilot.llm.httpx.AsyncClient", Client)
    response = client.post("/analyze", json={"message": "订单ORD-1008设备无法启动"})
    assert response.status_code == 200
    assert response.json()["source"] == "rules"
    assert response.json()["order_found"] is True
    assert calls["n"] == 0


def test_invalid_fallback_rejected_before_call(monkeypatch):
    llm_env(monkeypatch, fallback="always")
    calls = {"n": 0}

    def post(url, headers=None, json=None):
        calls["n"] += 1
        raise AssertionError("invalid fallback must not call the model")

    install_client(monkeypatch, post)
    response = client.post("/analyze", json={"message": "订单ORD-1008的设备无法启动"})
    assert response.status_code == 500
    assert response.json() == {"detail": "SP_LLM_FALLBACK配置无效"}
    assert calls["n"] == 0
    assert SECRET not in response.text


def test_parse_draft_error_has_no_source_text():
    payload = {
        "choices": [
            {"message": {"content": json.dumps({"category": "投诉", "summary": "想退款", "order_id": None}, ensure_ascii=False)}}
        ]
    }
    with pytest.raises(LLMCallError) as caught:
        parse_draft(payload)
    assert caught.value.kind == "output_invalid"
    assert str(caught.value) == "output_invalid"
    assert "投诉" not in str(caught.value)
    assert "想退款" not in str(caught.value)
