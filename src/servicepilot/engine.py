import re
from datetime import date

from .domain import AnalysisSource, TicketAnalysis
from .storage import find_order

KEYWORDS = {
    "设备故障": ("无法启动", "故障", "损坏", "不开机", "报警", "漏电", "异响", "停机", "不能启动"),
    "物流查询": ("物流", "发货", "快递", "运输", "到货", "配送"),
    "退换货": ("退款", "退货", "换货", "退换"),
    "发票问题": ("发票", "开票", "税号"),
}
DEPARTMENTS = {
    "设备故障": "技术售后",
    "物流查询": "物流客服",
    "退换货": "售后客服",
    "发票问题": "财务客服",
    "其他": "售后客服",
}
SAFETY_TERMS = ("漏电", "冒烟", "起火", "人身", "受伤")
BUSINESS_URGENCY_TERMS = ("影响生产", "停产", "产线停机")
ORDER_TOKEN = re.compile(
    r"(?:(?:订单号|订单|单号)\s*[:：]?\s*)?(?:ORD[-\s]*)?(\d{4,8})",
    re.IGNORECASE,
)
ORDER_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9])ORD[-\s]?(\d{4,8})(?!\d)", re.IGNORECASE),
    re.compile(r"订单号\s*[:：]?\s*(?:ORD[-\s]?)?(\d{4,8})(?!\d)", re.IGNORECASE),
    re.compile(r"订单\s*[:：]?\s*(?:ORD[-\s]?)?(\d{4,8})(?!\d)", re.IGNORECASE),
    re.compile(r"单号\s*[:：]?\s*(?:ORD[-\s]?)?(\d{4,8})(?!\d)", re.IGNORECASE),
)


def normalize_order_token(raw: str | None) -> str | None:
    """把单独的订单号片段规范成 ORD- 加数字。

    只接受「1008」「ORD-1008」「订单1008」这类片段，不从整句里捞数字。

    @param raw - 模型或调用方给出的候选
    @returns 规范订单号；无法整段匹配时返回 None
    """

    if raw is None:
        return None
    match = ORDER_TOKEN.fullmatch(raw.strip())
    if not match:
        return None
    return f"ORD-{match.group(1)}"


def extract_order_candidates(message: str) -> list[str]:
    """从原文提取用户明确写出的订单号，并保持出现顺序。

    @param message - 用户原文
    @returns 去重后的 ORD- 订单号
    """

    hits: list[tuple[int, str]] = []
    for pattern in ORDER_PATTERNS:
        for match in pattern.finditer(message):
            hits.append((match.start(), f"ORD-{match.group(1)}"))
    hits.sort(key=lambda item: item[0])
    found: list[str] = []
    for _, order_id in hits:
        if order_id not in found:
            found.append(order_id)
    return found


def resolve_order_id(message: str, suggested: str | None = None) -> tuple[str | None, bool]:
    """候选提取、标准化、原文核对。未在原文出现的候选一律丢弃。

    @param message - 用户原文
    @param suggested - 模型候选，不能单独成为订单号
    @returns 核对后的订单号，以及模型候选是否因对不上原文被忽略
    """

    found = extract_order_candidates(message)
    hinted = normalize_order_token(suggested)
    ignored = bool(hinted and hinted not in found)
    if hinted and hinted in found:
        return hinted, False
    if found:
        return found[0], ignored
    return None, ignored


def detect_safety_risk(message: str) -> bool:
    """判断设备或人身安全风险。生产加急词不在这里。

    @param message - 用户原文
    @returns 命中安全词时为 True
    """

    return any(word in message for word in SAFETY_TERMS)


def detect_business_urgency(message: str) -> bool:
    """判断业务紧急程度，例如影响生产。这不是安全事故。

    @param message - 用户原文
    @returns 命中加急词时为 True
    """

    return any(word in message for word in BUSINESS_URGENCY_TERMS)


def classify_category(message: str) -> str:
    """用关键词给出规则模式类别。

    @param message - 用户原文
    @returns 五类之一
    """

    return next((name for name, words in KEYWORDS.items() if any(word in message for word in words)), "其他")


def classify_rules(message: str) -> tuple[str, str | None, str]:
    """规则模式的类别、订单号和摘要。

    @param message - 用户原文
    @returns 类别、核对后的订单号、摘要
    """

    order_id, _ignored = resolve_order_id(message)
    return classify_category(message), order_id, message.strip()[:100]


def finalize(
    message: str,
    category: str,
    order_id: str | None,
    summary: str,
    source: AnalysisSource = "rules",
) -> TicketAnalysis:
    """用订单库和业务规则生成最终结果。不采纳模型自报的保修、优先级或派单。

    @param message - 用户原文
    @param category - 已经校验过的类别
    @param order_id - 待核对的候选
    @param summary - 摘要
    @param source - 结果来源
    @returns 可返回给调用方的分析结果
    """

    if category not in DEPARTMENTS:
        raise ValueError("unsupported category")
    if source not in ("rules", "llm", "llm_fallback_rules"):
        raise ValueError("unsupported source")
    verified_id, ignored_suggestion = resolve_order_id(message, order_id)
    order = find_order(verified_id) if verified_id else None
    missing: list[str] = []
    reasons: list[str] = []
    if ignored_suggestion:
        reasons.append("模型给出的订单号未能在原文中核对，已忽略")
    if not verified_id:
        missing.append("订单号")
        reasons.append("缺少可验证的订单号")
    elif not order:
        reasons.append("订单号未在模拟订单库中找到")
    warranty = "未核实"
    if order:
        warranty = "保修期内" if date.fromisoformat(order["warranty_end"]) >= date.today() else "保修期外"
    safety_risk = detect_safety_risk(message)
    business_urgency = detect_business_urgency(message)
    if safety_risk:
        reasons.append("涉及潜在安全风险，必须人工处理")
    if business_urgency:
        reasons.append("描述涉及生产影响，需人工核实严重程度")
    if safety_risk:
        priority = "紧急待人工复核"
    elif business_urgency:
        priority = "优先待人工复核"
    else:
        priority = "普通"
    if not order:
        missing.append("有效订单信息")
    return TicketAnalysis(
        category=category,
        summary=summary[:150],
        order_id=verified_id,
        order_found=bool(order),
        warranty_status=warranty,
        priority=priority,
        department=DEPARTMENTS[category],
        missing_information=list(dict.fromkeys(missing)),
        needs_human_review=True,
        reasons=reasons or ["所有建议均需人工确认，系统不自动批准退款、保修或赔偿"],
        source=source,
    )


def analyze_rules(message: str) -> TicketAnalysis:
    """规则模式入口，不访问模型。

    @param message - 用户原文
    @returns 来源为 rules 的分析结果
    """

    category, order_id, summary = classify_rules(message)
    return finalize(message, category, order_id, summary, source="rules")
