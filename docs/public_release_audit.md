# ServicePilot V0.3 公开候选安全审计

## 范围

本报告适用于独立目录 `ServicePilot_Public`。该目录是从私有开发项目选择性导出的公开候选，不包含原 Git 历史，也不代表已经创建或发布 GitHub 仓库。

候选内容来自导出时经过审阅的源工作树。真实 LLM Web 授权开关在源项目中尚属未提交变更，因此本候选只把它描述为当前导出代码的能力，不声称它已经存在于源项目的已提交 Git 历史。

## 纳入资产

- FastAPI 应用、领域模型、规则引擎、DeepSeek 兼容客户端和本地存储代码；
- 单页 Web 演示；
- API、规则、LLM Mock、Web 与安全日志测试；
- 人工构造的模拟订单；
- `pyproject.toml`、`uv.lock`、`.env.example` 与 `.gitignore`；
- V0.3 API、request ID、安全日志和 Web 验收文档；
- 用户提供的本地 Web 演示截图。

## 明确排除

- `.git`、分支、标签和私有提交历史；
- `.env`、API Key、个人凭证；
- SQLite 数据库、缓存、日志和冒烟运行目录；
- V0.2 gold/draft、原始 LLM 运行包、评估 CSV、报告和来源审计文档；
- 内部开发过程文档和历史运行元数据。

## 数据与评估政策

公开候选不包含 V0.2 冻结金标准，因此不存在修改后继续冒充原金标准的情况。历史内部实验结果不进入 README，也不得宣传为生产准确率、稳定性或真实客户效果。

公开包当前没有独立的正式评估数据集。pytest 结果只证明代码与离线契约测试通过，不代表生产性能或真实 LLM 准确率。

## 安全边界

- `.env` 已被忽略；`.env.example` 不含凭据；
- 规则模式默认启用，真实 LLM Web 授权默认关闭；
- LLM 自动化测试使用本地替身，不访问真实服务；
- 请求日志只记录白名单元数据，不记录工单正文、凭据、Prompt 或完整模型输出；
- Web 不使用外部 CDN、远程字体或浏览器存储保存工单原文；
- 本项目不具备生产级鉴权、审计和数据保护能力。

## 截图检查

`docs/images/servicepilot-web-demo.png` 展示模拟工单分析页面。检查未发现 API Key、个人联系方式、敏感文件路径或调试控制台内容。截图的来源标签不能单独证明真实 DeepSeek 调用。

## 依赖与许可证

Python 依赖由 `pyproject.toml` 声明并由 `uv.lock` 锁定。候选包未新增依赖。直接依赖和全部传递依赖均在独立安装环境中读取了许可证元数据与打包的 LICENSE/NOTICE 文件，详见 `docs/third_party_licenses.md`。

项目采用标准 MIT License：`Copyright (c) 2026 Jack Wang`，并在 `pyproject.toml` 中声明为 MIT。未发现依赖许可证冲突。当前源码仓库不 vendoring 第三方包；若未来分发 wheel 集合、可执行文件或容器镜像，须重新生成并随附第三方许可证与 NOTICE 清单。

## 独立复现结果

在候选目录创建独立 `.venv`，执行 `uv sync --offline --extra dev` 后，以规则模式、禁用 dotenv 和关闭真实 LLM Web 授权运行测试：`51 passed, 1 warning`。warning 是既有的 Starlette TestClient/httpx 弃用提示。测试期间没有真实模型调用。

## 发布结论

候选包已补充项目许可证、完成独立环境测试和敏感信息扫描，可进入人工发布审批。创建远程仓库、推送和设置公开可见性仍需分别取得人工批准。
