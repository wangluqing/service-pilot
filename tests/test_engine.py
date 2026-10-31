import pytest

from servicepilot.engine import analyze_rules, finalize

def test_device_and_order():
    result = analyze_rules("订单ORD-1008的设备无法启动，影响生产，请尽快处理")
    assert result.category == "设备故障"
    assert result.order_id == "ORD-1008"
    assert result.order_found is True
    assert result.priority == "优先待人工复核"
    assert result.needs_human_review is True

def test_missing_order():
    result = analyze_rules("设备故障无法启动，麻烦处理")
    assert result.order_found is False
    assert "订单号" in result.missing_information
    assert "有效订单信息" in result.missing_information
    assert any("缺少可验证的订单号" in item for item in result.reasons)
    assert result.needs_human_review is True

def test_invalid_order():
    result = analyze_rules("订单ORD-9999要开发票")
    assert result.category == "发票问题"
    assert result.order_found is False

def test_safety():
    result = analyze_rules("订单ORD-1001设备漏电，人员可能受伤")
    assert result.priority == "紧急待人工复核"
    assert result.needs_human_review is True
    assert any("安全风险" in item for item in result.reasons)

def test_unknown():
    result = analyze_rules("你好，我有一些问题想咨询")
    assert result.category == "其他"


def test_ordinary_ticket_still_requires_human_review():
    result = analyze_rules("订单ORD-1003设备出现异响")
    assert result.priority == "普通"
    assert result.order_found is True
    assert result.missing_information == []
    assert result.needs_human_review is True
    assert result.reasons == ["所有建议均需人工确认，系统不自动批准退款、保修或赔偿"]


def test_order_1008_normalized():
    result = analyze_rules("订单1008的设备无法启动")
    assert result.order_id == "ORD-1008"
    assert result.order_found is True
    assert result.source == "rules"


def test_lowercase_order_id():
    result = analyze_rules("订单ord-1008无法启动")
    assert result.order_id == "ORD-1008"
    assert result.order_found is True


def test_bare_number_is_not_order():
    result = analyze_rules("设备无法启动1008次了")
    assert result.order_id is None


def test_phone_number_is_not_order():
    result = analyze_rules("设备无法启动，联系电话13800138000")
    assert result.order_id is None


def test_production_is_not_safety_incident():
    result = analyze_rules("订单ORD-1008的设备无法启动，影响生产，请尽快处理")
    assert result.priority == "优先待人工复核"
    assert any("生产影响" in item for item in result.reasons)
    assert not any("安全" in item for item in result.reasons)


def test_safety_and_production_stay_distinct():
    result = analyze_rules("订单ORD-1001设备漏电，影响生产")
    assert result.priority == "紧急待人工复核"
    assert any("安全风险" in item for item in result.reasons)
    assert any("生产影响" in item for item in result.reasons)


def test_unknown_category_is_rejected():
    with pytest.raises(ValueError):
        finalize("设备无法启动请处理", "投诉", None, "无法启动")


def test_fabricated_order_is_dropped():
    result = finalize("设备无法启动，请尽快处理", "设备故障", "ORD-1008", "无法启动", source="llm")
    assert result.order_id is None
    assert result.order_found is False
    assert result.source == "llm"
    assert "ORD-1008" not in "".join(result.reasons)


def test_text_order_overrides_different_suggestion():
    result = finalize("订单ORD-1008无法启动", "设备故障", "ORD-9999", "无法启动", source="llm")
    assert result.order_id == "ORD-1008"
    assert result.order_found is True
    assert any("未能在原文中核对" in item for item in result.reasons)
