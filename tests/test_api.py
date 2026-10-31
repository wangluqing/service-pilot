import json
import logging
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from fastapi.testclient import TestClient

from servicepilot.main import REQUEST_ID_HEADER, app, db_path

client = TestClient(app)


def request_id(response) -> str:
    value = response.headers[REQUEST_ID_HEADER]
    assert UUID(value).version == 4
    return value


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "mode": "rules",
        "real_llm_web_authorized": False,
    }
    request_id(response)


def test_health_reports_explicit_llm_web_authorization(monkeypatch):
    monkeypatch.setenv("SP_MODE", "llm")
    monkeypatch.setenv("SP_REAL_LLM_WEB_AUTHORIZED", "true")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "mode": "llm",
        "real_llm_web_authorized": True,
    }


def test_llm_web_authorization_is_strict_and_defaults_closed(monkeypatch):
    monkeypatch.setenv("SP_MODE", "llm")
    monkeypatch.setenv("SP_REAL_LLM_WEB_AUTHORIZED", "yes")

    response = client.get("/health")

    assert response.json()["real_llm_web_authorized"] is False


def test_analyze():
    response = client.post("/analyze", json={"message": "订单ORD-1008设备无法启动"})
    assert response.status_code == 200
    data = response.json()
    assert data["order_found"] is True
    assert data["source"] == "rules"
    assert data["needs_human_review"] is True
    request_id(response)


def test_validation():
    response = client.post("/analyze", json={"message": "hi"})
    assert response.status_code == 422
    request_id(response)


def test_order_lookup_contract():
    response = client.get("/orders/ord-1008")
    assert response.status_code == 200
    assert response.json()["order_id"] == "ORD-1008"
    missing = client.get("/orders/ord-9999")
    assert missing.status_code == 404
    request_id(missing)


def test_unhandled_exception_has_controlled_500_and_request_id(monkeypatch):
    def fail_lookup(_order_id):
        raise RuntimeError("test-only failure")

    monkeypatch.setattr("servicepilot.main.find_order", fail_lookup)
    response = client.get("/orders/ORD-1008")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    request_id(response)


def test_request_ids_are_unique_and_client_value_is_ignored():
    supplied = "client-controlled-request-id"
    first = client.get("/health", headers={REQUEST_ID_HEADER: supplied})
    second = client.get("/health")

    first_id = request_id(first)
    second_id = request_id(second)
    assert first_id != supplied
    assert first_id != second_id


def test_concurrent_requests_have_isolated_request_ids():
    def fetch_id(_index):
        return request_id(client.get("/health"))

    with ThreadPoolExecutor(max_workers=8) as executor:
        ids = list(executor.map(fetch_id, range(16)))

    assert len(set(ids)) == len(ids)


def test_safe_request_log_matches_response_and_omits_path_and_query(caplog):
    caplog.set_level(logging.INFO, logger="servicepilot")
    path_marker = "sensitive-path-marker"
    query_marker = "sensitive-query-marker"

    response = client.get(f"/orders/{path_marker}?token={query_marker}")
    response_id = request_id(response)
    request_logs = [
        record.getMessage()
        for record in caplog.records
        if record.name == "servicepilot" and record.getMessage().startswith("http_request_complete")
    ]

    assert len(request_logs) == 1
    event = request_logs[0]
    assert f"request_id={response_id}" in event
    assert "route=/orders/{order_id}" in event
    assert "status_code=404" in event
    assert "duration_ms=" in event
    assert "mode=rules" in event
    assert "error_kind=http_404" in event
    for forbidden in (path_marker, query_marker):
        assert forbidden not in event


def test_safe_request_log_omits_request_body_and_credentials(caplog):
    caplog.set_level(logging.INFO, logger="servicepilot")
    body_marker = "private-ticket-body-marker"
    authorization_marker = "secret-authorization-marker"
    cookie_marker = "secret-cookie-marker"

    response = client.post(
        "/analyze",
        json={"message": body_marker},
        headers={
            "Authorization": f"Bearer {authorization_marker}",
            "Cookie": f"session={cookie_marker}",
        },
    )
    response_id = request_id(response)
    request_logs = [
        record.getMessage()
        for record in caplog.records
        if record.name == "servicepilot" and record.getMessage().startswith("http_request_complete")
    ]

    assert response.status_code == 200
    assert len(request_logs) == 1
    assert f"request_id={response_id}" in request_logs[0]
    for forbidden in (body_marker, authorization_marker, cookie_marker):
        assert forbidden not in request_logs[0]


def test_ticket_save_and_query_contract(monkeypatch, tmp_path):
    database = tmp_path / "first" / "tickets.db"
    monkeypatch.setenv("SP_DB_PATH", str(database))
    monkeypatch.setenv("SP_MODE", "rules")

    payload = {
        "message": "订单ORD-1008设备无法启动",
        "confirmed_by": "演示审核员甲",
    }
    created = client.post("/tickets", json=payload)

    assert created.status_code == 200
    created_data = created.json()
    assert created_data["ticket_id"] == 1
    assert created_data["status"] == "已记录（教学模拟人工确认）"
    assert created_data["analysis"]["category"] == "设备故障"
    assert created_data["analysis"]["source"] == "rules"

    listed = client.get("/tickets")
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["id"] == created_data["ticket_id"]
    assert rows[0]["message"] == payload["message"]
    assert rows[0]["confirmed_by"] == payload["confirmed_by"]
    assert json.loads(rows[0]["analysis_json"]) == created_data["analysis"]
    assert database.is_file()
    assert db_path() == str(database)


def test_ticket_list_is_newest_first(monkeypatch, tmp_path):
    database = tmp_path / "second" / "tickets.db"
    monkeypatch.setenv("SP_DB_PATH", str(database))
    monkeypatch.setenv("SP_MODE", "rules")

    first = client.post(
        "/tickets",
        json={"message": "订单ORD-1008设备无法启动", "confirmed_by": "演示审核员甲"},
    )
    second = client.post(
        "/tickets",
        json={"message": "订单ORD-1005需要开具发票", "confirmed_by": "演示审核员乙"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    rows = client.get("/tickets").json()
    assert [row["id"] for row in rows] == [2, 1]
    assert [row["confirmed_by"] for row in rows] == ["演示审核员乙", "演示审核员甲"]
    assert json.loads(rows[0]["analysis_json"])["category"] == "发票问题"
    assert json.loads(rows[1]["analysis_json"])["category"] == "设备故障"


def test_ticket_databases_are_isolated(monkeypatch, tmp_path):
    first_database = tmp_path / "isolated-a.db"
    second_database = tmp_path / "isolated-b.db"
    monkeypatch.setenv("SP_MODE", "rules")
    monkeypatch.setenv("SP_DB_PATH", str(first_database))
    assert client.post(
        "/tickets",
        json={"message": "订单ORD-1008设备无法启动", "confirmed_by": "演示审核员甲"},
    ).status_code == 200

    monkeypatch.setenv("SP_DB_PATH", str(second_database))
    assert client.get("/tickets").json() == []
    assert first_database.is_file()
    assert second_database.is_file()
