# Third-party license audit

本清单依据 `uv.lock` 对应的独立安装环境及 Python distribution metadata 生成，适用于 ServicePilot V0.3 公开候选。项目源码本身采用 MIT License。

## Direct dependencies

| Package | Version | Declared license |
|---|---:|---|
| fastapi | 0.143.3 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause |
| python-dotenv | 1.2.4 | BSD-3-Clause |
| pydantic | 2.14.1 | MIT |
| pytest (development) | 9.1.1 | MIT |

## Transitive dependencies

| Package | Version | Declared license |
|---|---:|---|
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| certifi | 2026.7.22 | MPL-2.0 |
| click | 8.5.0 | BSD-3-Clause |
| colorama | 0.4.6 | BSD-3-Clause (verified from packaged license text) |
| h11 | 0.16.0 | MIT |
| httpcore | 1.0.9 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| iniconfig | 2.3.1 | MIT |
| opentelemetry-api | 1.45.1 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pluggy | 1.7.0 | MIT |
| pydantic-core | 2.50.1 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause |
| starlette | 1.8.0 | BSD-3-Clause |
| typing-inspection | 0.4.4 | MIT |
| typing-extensions | 4.16.0 | PSF-2.0 |

## Compatibility and obligations

- 未发现会阻止 ServicePilot 采用 MIT License 的依赖许可证冲突。
- MIT、BSD-2-Clause、BSD-3-Clause 和 PSF-2.0 要求在再分发相应软件时保留版权与许可证文本。
- Apache-2.0 要求保留许可证、变更说明，并在上游提供 NOTICE 时保留相关 NOTICE。当前安装分发包为 `opentelemetry-api` 提供 LICENSE，但没有打包 NOTICE；`packaging` 声明 Apache-2.0 OR BSD-2-Clause，可按其许可选择处理。
- MPL-2.0 是文件级 copyleft。当前公开仓库没有复制或修改 certifi 源文件，只通过锁定依赖引用；如果未来随二进制或离线包再分发 certifi，应同时提供其 MPL-2.0 文本及对应源码获取方式，并保持对修改文件的 MPL-2.0 约束。
- 当前 GitHub 候选只分发本项目源码和锁文件，不 vendoring 第三方包源码或 wheel。用户通过包管理器安装时，各分发包自带的 license metadata/files 由安装包提供。

## NOTICE review

独立安装环境中的所有第三方分发包均声明了许可证，并包含 LICENSE 或等价许可证文件。Pygments 还包含 AUTHORS。未发现名为 NOTICE 的打包文件，因此当前仓库没有需要复制的上游 NOTICE；若发布形式改为捆绑 wheel、可执行文件或容器镜像，必须重新生成随附许可证与 NOTICE 清单。
