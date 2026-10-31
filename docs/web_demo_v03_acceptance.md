# ServicePilot V0.3 Web 演示验收说明

## 1. 范围与边界

V03-T03 只改进单页分析体验，不增加前端框架、构建系统或联网依赖，不修改服务端业务规则，也不实现最近工单列表。真实 DeepSeek 调用仍为 `NOT_AUTHORIZED`；页面只允许默认规则模式，LLM 选项明确禁用。

页面用于安全模拟数据的教学与工程演示，不处理真实客户数据，不提供自动批准退款、赔偿、保修、派遣或免除人工复核的能力。

## 2. 已实现的可观察行为

- 显示 ServicePilot V0.3 定位、模拟数据声明和人工确认边界。
- 支持安全模拟示例、空输入提示、清空输入和分析期间按钮禁用。
- 按当前 `TicketAnalysis` 字段展示类别、摘要、订单核验、保修、优先级、部门、缺失信息、原因、来源和人工复核状态。
- 来源映射固定为 `rules`、`llm` 和 `llm_fallback_rules`，不把共享 Python 规则能力归因于 LLM。
- 风险提示首先使用结构化的 `missing_information` 和 `priority`；具体依据原样列出 `reasons`。当前 API 没有独立风险类型代码，因此更细粒度的组合风险分类属于功能限制。
- 区分未开始、分析中、成功、422、500、502、503、504、网络失败、非 JSON 响应和未知失败。
- 错误响应存在 `X-Request-ID` 时显示并允许复制；不存在时不生成替代值。
- 所有动态文本通过 `textContent` 或 DOM 节点 API 渲染，不使用 `innerHTML` 拼接不可信内容。
- 不在控制台输出工单、凭据或完整响应，也不使用浏览器存储保存工单原文。

## 3. 离线自动化验证

```powershell
$env:PYTHON_DOTENV_DISABLED="1"
$env:PYTHONDONTWRITEBYTECODE="1"
$env:SP_MODE="rules"
$env:SP_LLM_FALLBACK="off"
uv run --offline pytest -q -p no:cacheprovider
```

`tests/test_web.py` 对字段、来源、错误状态、安全 DOM 使用、外部依赖、浏览器持久化、request ID 和重复提交保护进行静态契约检查。该检查不能替代真实浏览器交互验收。

## 4. 人工浏览器验收步骤

在明确的规则模式环境中启动本地服务，不配置或调用真实 DeepSeek：

1. 打开首页，确认桌面布局、模拟数据声明和人工复核声明清晰可见。
2. 缩窄浏览器窗口至移动端宽度，确认输入区、结果区和按钮无水平溢出。
3. 分别使用安全模拟文本检查：有效订单设备故障、缺少订单号、潜在安全风险、业务加急和普通咨询。
4. 对照 `/analyze` JSON 确认页面字段、来源、缺失信息和原因一致。
5. 输入空白和少于四字符的内容，确认分别出现本地提示和 422 安全提示。
6. 使用测试环境模拟 500、502、503、504、网络中断和非 JSON 响应，确认不显示上游正文、堆栈或秘密。
7. 确认响应提供 `X-Request-ID` 时页面显示该值；无响应头时不显示伪造值。
8. 快速重复点击分析按钮，确认请求期间按钮禁用，结束后恢复。
9. 检查规则、Mock LLM 和 Mock fallback 的来源标签。Mock 结果不得描述为真实 LLM 运行。
10. 确认页面没有保存或查询最近工单的新增入口；该范围属于 V03-T04。

## 5. 验收状态

- 规则模式已有人工浏览器截图，截图确认页面来源显示为 `rules`。该截图只证明已展示的规则模式场景，不代表第 4 节全部桌面端场景均已完成人工验收。
- Mock LLM 与 Mock fallback 已通过离线自动化测试，分别验证 `source=llm` 与 `source=llm_fallback_rules`；这不是浏览器交互验收，也不是真实模型推理。
- Mock LLM 与 Mock fallback 的浏览器交互状态为 `NOT_VERIFIED`。
- 移动端布局与交互的人工验收状态为 `NOT_VERIFIED`。
- 真实 LLM 调用状态为 `NOT_AUTHORIZED`，不得调用真实 DeepSeek API。
