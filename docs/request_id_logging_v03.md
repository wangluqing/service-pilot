# ServicePilot V0.3 Request ID 与最小安全日志

## 1. 适用范围

本文记录 V03-T02 已实现的 HTTP request ID 和本地最小安全日志契约。该能力用于工程排错和请求关联，不构成生产级日志、监控或审计系统。

## 2. X-Request-ID 契约

- 每个进入 FastAPI 的 HTTP 请求由服务端生成一个新的 UUID4。
- 响应头名称为 `X-Request-ID`。
- 客户端传入的同名请求头不会被接受、信任或复用。
- 正常响应、FastAPI 422 校验错误、已有业务 HTTP 错误和中间件可控的 500 响应均携带该响应头。
- request ID 不加入响应体，现有 API 响应体结构保持不变。
- 请求之间通过 `ContextVar` 隔离，不使用全局共享的可变 request ID。

## 3. 日志白名单

每个可控 HTTP 响应记录一条 `http_request_complete` 事件。只允许以下字段：

- `request_id`
- FastAPI 路由模板，例如 `/orders/{order_id}`
- HTTP 状态码
- 请求耗时（毫秒）
- 分析模式，仅在值为 `rules` 或 `llm` 时记录
- 错误种类（如可安全获得）

当前实现不会为了补充日志读取请求体、响应体或其他敏感数据。结果来源无法在不读取响应内容或侵入业务路径的情况下安全取得，因此当前事件省略该字段。

## 4. 禁止记录的内容

请求完成事件不得包含：

- API Key、`Authorization` 或 Cookie
- 工单原文、订单原文或其他敏感请求参数
- 原始 URL 查询字符串或真实路径参数值
- 完整 Prompt、完整模型输出或上游响应正文
- 完整异常堆栈
- 其他未经批准的敏感内容

未匹配到路由模板时记录固定值 `<unmatched>`，不回退到真实 URL。

## 5. 异常路径与边界

- FastAPI 产生的 422 和已处理 `HTTPException` 保留原有响应体，并由中间件添加 request ID。
- 路由处理中的未处理 `Exception` 转换为固定的 `500` JSON 响应 `{"detail":"Internal server error"}`，不把异常消息或堆栈暴露给客户端或请求完成日志。
- 连接中断、进程终止、`BaseException`，以及中间件自身在形成响应前失败等情况，无法保证生成可发送的响应头。
- 本地最小日志没有持久化、保留周期、访问控制、完整性保护或生产日志平台集成，不得描述为生产审计能力。

## 6. 并发隔离

中间件在请求开始时设置请求作用域的 `ContextVar`，并在请求结束时通过 token 恢复上下文。并发测试验证多个同时请求产生不同 UUID4，且客户端提供的 ID 不会进入响应。

## 7. 本地离线验证

```powershell
$env:SP_MODE='rules'
$env:SP_LLM_FALLBACK='off'
uv run --offline pytest -q
```

常规验证不需要、也不得调用真实 DeepSeek API。测试使用规则模式、Mock 和临时 SQLite 数据库。
