# ServicePilot V0.3 API 契约基线

## 1. 文档状态与范围

- 任务：`V03-T01`
- 契约基线：提交 `afc45f8911bcbc1159d66bcb3971718ca519671d` 上的现有业务实现
- 适用范围：当前 FastAPI HTTP 接口和本地教学演示行为
- 非目标：本文档不实现 V0.3 规划能力，不授权真实 LLM 调用，不改变业务规则

本文档固定当前可观察行为，供后续 V0.3 变更做回归对照。除非特别标为“已实现”，规划中的能力均不得从本文档推断为已经完成。

## 2. 通用契约与安全边界

- 服务入口：`src/servicepilot/main.py` 中的 FastAPI `app`。
- 默认分析模式：环境变量 `SP_MODE` 未配置时为 `rules`。
- 请求和响应媒体类型：JSON；`GET /` 的 HTML 页面不在本 API 契约范围内。
- 输入校验：请求模型由 Pydantic 校验；校验失败使用 FastAPI 标准 `422` JSON 响应。
- 人工复核：`TicketAnalysis.needs_human_review` 当前始终为 `true`。
- 模型边界：LLM 只产生类别、摘要和订单候选草稿；订单、订单存在性、保修、优先级、部门、风险和人工复核由共享 Python 规则核验或决定。
- 数据边界：接口仅用于模拟数据和本地教学演示，无生产级鉴权、授权、租户隔离或审计能力。
- 日志边界：V03-T02 已实现请求完成事件的白名单日志；字段和限制见 `docs/request_id_logging_v03.md`。
- request ID：服务端为每个进入 FastAPI 的请求生成 UUID4，并在可控响应的 `X-Request-ID` 响应头中返回；客户端同名请求头不会被接受或复用。响应体结构不变。
- 真实 LLM：V0.3 当前状态为 `NOT_AUTHORIZED`。常规测试仅使用规则模式或 Mock。

## 3. 共享响应模型：TicketAnalysis

`POST /analyze` 和 `POST /tickets` 中的 `analysis` 使用以下当前字段：

| 字段 | 类型 | 当前含义 |
|---|---|---|
| `category` | string | 五类之一：设备故障、物流查询、退换货、发票问题、其他 |
| `summary` | string | 规则模式截取原文；LLM 模式使用校验后的模型摘要 |
| `order_id` | string 或 null | 经原文提取与核对后的规范订单号 |
| `order_found` | boolean | 是否在模拟订单 CSV 中找到 |
| `warranty_status` | string | 未核实、保修期内或保修期外 |
| `priority` | string | 普通、优先待人工复核或紧急待人工复核 |
| `department` | string | 共享 Python 规则给出的演示部门 |
| `missing_information` | string 数组 | 当前缺失信息，例如订单号、有效订单信息 |
| `needs_human_review` | boolean | 当前恒为 `true` |
| `reasons` | string 数组 | 共享规则产生的核对、风险和人工复核原因 |
| `source` | string | `rules`、`llm` 或 `llm_fallback_rules` |

`source` 只说明分析路径。订单、安全风险、业务加急、优先级、保修和人工复核不得归因于 LLM 独立能力。

## 4. GET /health

### 用途

返回应用存活状态和当前配置的分析模式。

### 请求

- 无路径、查询或请求体参数。

### 成功响应

- 状态码：`200`
- 当前结构：

```json
{"status": "ok", "mode": "rules", "real_llm_web_authorized": false}
```

`mode` 直接读取 `SP_MODE`，当前端点不校验该值是否合法。`real_llm_web_authorized` 是非敏感布尔状态：只有 `SP_REAL_LLM_WEB_AUTHORIZED=true` 时为 `true`，供本地 Web 判断是否允许在 LLM 模式提交分析；默认关闭，不包含 API Key 或其他凭据。

### 已实现错误

- 无显式业务错误。
- 运行时框架或环境异常的具体响应：`NOT_VERIFIED`。

### 安全边界

- 不返回 API Key、数据库路径或模型配置详情。
- 该响应只表示进程可响应，不是下游依赖健康检查。

### 测试

- `tests/test_api.py::test_health`

## 5. GET /orders/{order_id}

### 用途

从 `data/orders.csv` 查询一条模拟订单。仅供教学演示。

### 请求

- 路径参数 `order_id`：字符串；服务端先转换为大写再精确匹配。

### 成功响应

- 状态码：`200`
- 当前结构：包含 `order_id`、`product_model`、`purchase_date`、`warranty_end`、`order_status` 的 CSV 行对象。

### 已实现错误

- `404`：模拟订单不存在，响应 detail 为“模拟订单不存在”。
- 订单 CSV 缺失、损坏或读取失败时的稳定错误契约：`NOT_VERIFIED`。

### 安全边界

- 当前无鉴权，不得接入真实订单数据或描述为生产查询接口。

### 测试

- `tests/test_api.py::test_order_lookup_contract`
- `tests/test_engine.py` 中的订单提取和核对测试

## 6. POST /analyze

### 用途

分析模拟售后工单，不写入 SQLite。

### 请求

```json
{"message": "订单ORD-1008设备无法启动"}
```

- `message`：必填字符串，长度 4 至 3000 字符。

### 成功响应

- 状态码：`200`
- 响应：完整 `TicketAnalysis`。
- 规则模式的 `source` 为 `rules`。
- Mock LLM 成功的 `source` 为 `llm`。
- 模型超时、HTTP 错误或非法输出且显式配置规则降级时，`source` 为 `llm_fallback_rules`。

### 已实现错误

| 状态码 | 当前条件 |
|---:|---|
| `422` | 请求体缺失、类型或 message 长度不合法 |
| `500` | `SP_MODE` 或 `SP_LLM_FALLBACK` 配置非法 |
| `502` | 上游 HTTP/网络失败，或模型输出未通过校验且未降级 |
| `503` | LLM 模式缺少 API Key；即使 fallback 为 rules 也不降级 |
| `504` | 模型超时且未降级 |

### 安全边界

- 不保存工单。
- 不返回调用元数据、Token 或 API Key。
- 模型失败不得伪装为 `source=llm` 成功。
- 风险和业务加急来自共享 Python 规则，不是模型独立判断。

### 测试

- `tests/test_api.py::test_analyze`
- `tests/test_api.py::test_validation`
- `tests/test_llm.py::test_valid_output_keeps_business_facts`
- `tests/test_llm.py::test_timeout_falls_back_to_rules`
- `tests/test_llm.py::test_missing_key_does_not_fallback`
- `tests/test_llm.py::test_rules_mode_does_not_call_api`
- `tests/test_engine.py` 中的风险、业务加急、普通工单和缺少订单测试

## 7. POST /tickets

### 用途

重新分析模拟工单，并在人工确认后写入本地 SQLite。

### 请求

```json
{
  "message": "订单ORD-1008设备无法启动",
  "confirmed_by": "演示审核员甲"
}
```

- `message`：必填字符串，长度 4 至 3000 字符。
- `confirmed_by`：必填字符串，长度 2 至 80 字符。

### 成功响应

- 状态码：`200`
- 当前结构：

```json
{
  "ticket_id": 1,
  "analysis": {"source": "rules"},
  "status": "已记录（教学模拟人工确认）"
}
```

上例中的 `analysis` 仅为缩写说明；实际响应包含完整 `TicketAnalysis`。

### 当前持久化结构

SQLite 表保存 `id`、完整 `message`、序列化 `analysis_json`、`confirmed_by` 和 UTC `created_at`。`SP_DB_PATH` 可指定数据库路径；相对路径以项目根目录解析。

### 已实现错误

- `422`：请求体、message 或 confirmed_by 校验失败。
- 分析阶段继承 `POST /analyze` 的 `500`、`502`、`503`、`504` 行为。
- SQLite 创建或写入失败时的稳定错误响应结构：`NOT_VERIFIED`；当前未实现专用映射。

### 安全边界

- 当前端点没有身份认证；“人工确认”由调用方提交的 `confirmed_by` 文本表示，不构成生产审计身份。
- 当前会保存完整 message，只允许模拟数据。
- 当前分析与保存不是面向生产系统定义的原子业务事务：`NOT_VERIFIED`。

### 测试

- `tests/test_api.py::test_ticket_save_and_query_contract`
- `tests/test_api.py::test_ticket_list_is_newest_first`
- `tests/test_api.py::test_ticket_databases_are_isolated`

## 8. GET /tickets

### 用途

返回当前 SQLite 中最近保存的最多 100 条模拟工单。

### 请求

- 无路径、查询或请求体参数。

### 成功响应

- 状态码：`200`
- 当前响应是按 `id DESC` 排序的数组。
- 每一项是 SQLite 原始行，包含 `id`、`message`、`analysis_json`、`confirmed_by`、`created_at`。
- 如果数据库或表尚不存在，当前实现会创建空表并返回空数组。

### 已实现错误

- 无显式业务错误。
- SQLite 创建或读取失败时的稳定错误响应结构：`NOT_VERIFIED`。

### 安全边界与规划差距

- 当前返回完整 message 和 confirmed_by，且没有鉴权，仅限模拟演示。
- V0.3 规划要求页面默认只展示 ID、分类、状态、时间和必要安全摘要；该规划尚未由当前 API 实现。
- 本任务只记录差距，不修改响应或存储行为。

### 测试

- `tests/test_api.py::test_ticket_save_and_query_contract`
- `tests/test_api.py::test_ticket_list_is_newest_first`
- `tests/test_api.py::test_ticket_databases_are_isolated`

## 9. 风险与来源回归矩阵

| 场景 | 当前优先级 | 必须人工复核 | 主要原因来源 | 测试 |
|---|---|---:|---|---|
| 安全风险 | 紧急待人工复核 | 是 | 共享 Python 安全词规则 | `test_safety` |
| 仅业务加急 | 优先待人工复核 | 是 | 共享 Python 业务加急规则 | `test_production_is_not_safety_incident` |
| 安全风险与业务加急 | 紧急待人工复核 | 是 | 两项共享 Python 规则均保留 | `test_safety_and_production_stay_distinct` |
| 普通有效订单 | 普通 | 是 | 默认人工确认规则 | `test_ordinary_ticket_still_requires_human_review` |
| 缺少订单号 | 按风险词决定 | 是 | 订单提取和缺失信息规则 | `test_missing_order` |

分析来源回归由 `tests/test_llm.py` 覆盖 `rules`、`llm` 和 `llm_fallback_rules`。这些来源字段不改变风险规则的归因。

## 10. 当前未实现和 NOT_VERIFIED 项

- `X-Request-ID`：已实现于 V03-T02；连接中断及中间件本身无法形成响应的失败不保证返回该响应头。
- V0.3 最小安全日志字段契约：已实现本地工程排错所需的白名单事件，但不具备生产审计能力。
- 工单列表的最小字段响应模型：未实现；当前返回原始数据库行。
- SQLite 异常的稳定 HTTP 映射：`NOT_VERIFIED`。
- SQLite 生产并发、事务和数据隔离能力：`NOT_VERIFIED`，且不属于 V0.3 原型承诺。
- 生产鉴权、授权、审计和真实客户数据保护：未实现。
- 真实 LLM 评估：`NOT_AUTHORIZED`，不是本契约基线的一部分。
