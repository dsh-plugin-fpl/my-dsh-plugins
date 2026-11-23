# my-dsh-plugins

FPL 的 DeepSeek Harness 插件联合开发工作区：集中维护架构、Agent 开发规则、插件版本组合和联动验收，各插件保留独立仓库与发布能力。

`dsh-core` 独立提供公共模型、Agent、本地模型、任务与资源服务及 FPL 看板。DSH 通过可选连接层接入，业务状态由独立服务持有。视觉创作工坊与视频剪辑工坊各自提供独立服务，通过公开 Core 协议与受限工坊交接组合能力。

## 获取与初始化

```sh
git clone --recurse-submodules https://github.com/dsh-plugin-fpl/my-dsh-plugins.git
cd my-dsh-plugins
python3 scripts/workspace.py status
python3 scripts/workspace.py check
```

已普通克隆时，运行 `python3 scripts/workspace.py bootstrap` 初始化固定版本。需要 Git 和 Python 3.10+，无需安装 Python 包；有 uv 时可将 `python3` 换为 `uv run --no-project python`。

| 命令 | 行为 |
| --- | --- |
| `python3 scripts/workspace.py bootstrap` | 初始化尚未检出的直接子模块，已有修改或版本偏移时停止 |
| `python3 scripts/workspace.py status` | 只读查看分支、提交、修改、版本差异及缓存的 upstream 信息 |
| `python3 scripts/workspace.py check` | 只读检查登记、gitlink、初始化、固定版本和文档；失败返回非零 |

脚本从自身位置定位工作区，可从其他目录调用。不会自动拉取最新版本、提交或推送；`status` 不执行 fetch。子模块清单唯一来源为 `.gitmodules`，每次总仓库提交的 gitlink 固定整套版本。

## 插件

| 插件 | 仓库 | 当前状态与职责 |
| --- | --- | --- |
| dsh-core | [dsh-plugin-fpl/dsh-core](https://github.com/dsh-plugin-fpl/dsh-core) | 独立公共服务与 FPL 看板，包含模型、五种 Agent、本地模型、任务与资源；DSH 保留连接层 |
| dsh-visual-workshop | [dsh-plugin-fpl/dsh-visual-workshop](https://github.com/dsh-plugin-fpl/dsh-visual-workshop) | 视觉创作工坊独立服务与原 FPL 界面，画布、设定、分镜、三维预演和 Core 生成；DSH 提供登记与工具 |
| dsh-video-editor | [dsh-plugin-fpl/dsh-video-editor](https://github.com/dsh-plugin-fpl/dsh-video-editor) | 视频剪辑独立服务与原时间线界面，素材处理、FFmpeg 预览/导出、片段交接；DSH 提供登记与工具 |

新增应用按 [插件接入流程](docs/adding-plugins.md) 登记，整套版本由总仓库固定。

## 整套开发入口

在本目录启动 Agent，先读取 [AGENTS.md](AGENTS.md)，修改插件前再读取插件自身规则。

- [架构与契约](docs/architecture.md)：职责、依赖方向、共享接口与联动原则。
- [开发流程](docs/development.md)：分支、跨仓库提交、版本更新与恢复。
- [新增插件](docs/adding-plugins.md)：新仓库接入与最低验收要求。
- [决策记录](docs/decisions.md)：工作区边界及工具行为的原因。
- [联动验收目录](tests/integration/README.md)：整套能力与后续应用交接的验收入口。

临时验收输出放 `.local/`，持久本地运行状态放 `.runtime/`。从 [dsh-core 使用说明](dsh-core/README.md) 开始配置和接入。

## 工坊运行与验收

分别按 [视觉工坊](dsh-visual-workshop/README.md) 与 [剪辑工坊](dsh-video-editor/README.md) 安装自身环境，运行各自 `node scripts/application.mjs start` 和 `open`。默认监听 9360 / 9361，Core 使用 9310；DSH 插件只连接服务。首次使用为空配置，旧 FPL 数据不自动迁入。

三服务与打包安装验收：先构建三个插件 tarball，再运行 `dsh-core/.runtime/worker-venv/bin/python scripts/verify_workshops.py`。需要 DSH CLI、FFmpeg 和 Chrome；使用 19310 / 19360 / 19361 / 19362 隔离端口，报告与截图位于 `.local/workshops-integration/`。详见 [联动验收](tests/integration/README.md)。
