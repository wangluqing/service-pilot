from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

Category = Literal["设备故障", "物流查询", "退换货", "发票问题", "其他"]
AnalysisSource = Literal["rules", "llm", "llm_fallback_rules"]
LLM_ERROR_KINDS = ("config_missing", "timeout", "http_error", "output_invalid")


class AnalyzeRequest(BaseModel):
    """分析请求。

    @param message - 售后原文，4到3000字符
    """

    message: str = Field(min_length=4, max_length=3000)


class LLMCallMeta(BaseModel):
    """单次模型调用的非敏感元数据，不进入 API 响应。

    @param model - 服务端配置的模型名
    @param latency_ms - 调用耗时（毫秒）
    @param prompt_tokens - 输入 token，上游未返回时为空
    @param completion_tokens - 输出 token，上游未返回时为空
    """

    model: str
    latency_ms: int = Field(ge=0)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMDraft(BaseModel):
    """模型草稿。缺字段、非法类别或过长摘要时整体失败，不降级成「其他」。

    @param category - 只能是既定五类
    @param summary - 去掉首尾空白后 1 到 100 字
    @param order_id - 必须出现该字段；无订单号时为 null
    """

    model_config = ConfigDict(extra="ignore")

    category: Category
    summary: str = Field(min_length=1, max_length=100)
    order_id: str | None

    @field_validator("summary")
    @classmethod
    def summary_must_have_text(cls, value: str) -> str:
        """去掉空白后仍须在长度限制内。

        @param value - 模型给出的摘要
        @returns 规范化后的摘要
        """

        text = value.strip()
        if not text or len(text) > 100:
            raise ValueError("summary length is invalid")
        return text

    @field_validator("order_id", mode="before")
    @classmethod
    def order_id_must_be_text_or_null(cls, value: object) -> str | None:
        """订单号只接受字符串或 null，数字等其他类型视为校验失败。

        @param value - 模型原文中的 order_id
        @returns 去掉空白后的文本；空串视为 null
        """

        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("order_id must be a string or null")
        text = value.strip()
        return text or None


class TicketAnalysis(BaseModel):
    """对外工单分析结果。订单、保修、优先级由业务规则填写。

    @param source - rules、llm 或 llm_fallback_rules
    """

    category: Category
    summary: str
    order_id: str | None = None
    order_found: bool = False
    warranty_status: str = "未核实"
    priority: str = "普通"
    department: str = "售后客服"
    missing_information: list[str] = Field(default_factory=list)
    needs_human_review: bool = True
    reasons: list[str] = Field(default_factory=list)
    source: AnalysisSource = "rules"
    _call_meta: LLMCallMeta | None = PrivateAttr(default=None)


class TicketCreate(BaseModel):
    """人工确认后的入库请求。

    @param message - 售后原文
    @param confirmed_by - 确认人
    """

    message: str = Field(min_length=4, max_length=3000)
    confirmed_by: str = Field(min_length=2, max_length=80)
