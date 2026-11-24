# my-dsh-plugins

FPL 的 DeepSeek Harness 插件联合开发工作区：集中维护架构、Agent 开发规则、插件版本组合和联动验收，各插件保留独立仓库与发布能力。

`dsh-core` 独立提供公共模型、Agent、本地模型、任务与资源服务及 FPL 看板。DSH 通过可选连接层接入，业务状态由独立服务持有。六个工坊各自提供独立服务，通过公开 Core 协议与受限工坊交接组合能力。

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
| dsh-presentation-workshop | [dsh-plugin-fpl/dsh-presentation-workshop](https://github.com/dsh-plugin-fpl/dsh-presentation-workshop) | 演示工坊独立服务、原 FPL 界面、DSH 插件和 Core 统一账号；端口 9362 |
| dsh-thought-workshop | [dsh-plugin-fpl/dsh-thought-workshop](https://github.com/dsh-plugin-fpl/dsh-thought-workshop) | 思绪工坊独立服务、原 FPL 界面、DSH 插件和 Core 统一账号；端口 9363 |
| dsh-galgame-workshop | [dsh-plugin-fpl/dsh-galgame-workshop](https://github.com/dsh-plugin-fpl/dsh-galgame-workshop) | Galgame 工坊独立服务、原 FPL 界面、DSH 插件和 Core 统一账号；端口 9364 |
| dsh-audio-annotation | [dsh-plugin-fpl/dsh-audio-annotation](https://github.com/dsh-plugin-fpl/dsh-audio-annotation) | 录音标注工坊独立服务、原 FPL 界面、DSH 插件和 Core 统一账号；端口 9365 |

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

六个工坊分别在自己的目录 `pnpm setup`，按各自 README 的 `connect-core` 步骤连接 Core 0.5 统一账号，再 `pnpm start` / `pnpm open`。Core 9310，视觉 9360、剪辑 9361、演示 9362、思绪 9363、Galgame 9364、录音标注 9365。新四应用首次为空，原 FPL 数据不自动迁入；思绪官方内容须管理员显式导入。插件托管模式随 DSH 开关正常启停，manageService=false 时独立常驻。

完整组合先构建 Core 和六个应用的插件 tarball，安装自身环境，再执行：

```sh
WORKSHOPS_UI_SCRIPT="$PWD/scripts/verify-workshops-accounts-ui.mjs" \
WORKSHOPS_HARNESS_SCRIPT="$PWD/scripts/verify-workshops-accounts-harness.mjs" \
WORKSHOPS_WORKSPACE="$PWD" \
dsh-core/.runtime/worker-venv/bin/python scripts/verify_workshops_accounts.py
```

需要 DSH CLI、FFmpeg 和 Chrome；使用 19310、19362–19368 隔离端口，证据在 `.local/workshops-accounts/`。脚本仅使用提供方公开 CLI、HTTP/WS 与文档化测试夹具。详见 [联动验收](tests/integration/README.md)。

## 统一存储

在 Core 看板顶部“存储”中设置统一数据根目录。默认建议 `~/Library/Application Support/DSH-FPL`；Core 与六工坊按自己的子目录保存数据，代码和运行环境仍由安装目录管理。已有数据通过预检、显式迁移和可恢复切换导入，原目录保留。旧 FPL 来源必须另外明确登记和选择，不会因新安装自动导入。参见 [Core 存储与迁移](dsh-core/docs/storage.md)。DSH 插件显示名称统一采用 `dsh-fpl-` 前缀，仓库、包 ID 与稳定应用 ID 保持兼容。

七服务真实启停验收：构建并打包当前插件后运行 `node scripts/verify_plugin_lifecycle.mjs`，证据在 `.local/plugin-lifecycle/`。

## 托管安装改造候选

当前未发布候选保留七个独立服务，将每个服务的生产源码、锁文件和编译界面放入自身插件包。Core 的 **FPL 安装与连接** 设置负责首次环境准备、服务启停和浏览器确认授权；六工坊同时提供原生 DSH 工具与操作 Skill。目标 Host 为 `0.2.2-rc.1` 和 `0.2.2-rc.5`，首轮支持 macOS；安装和恢复约定归 [Core 文档](dsh-core/docs/managed-setup.md)。

隔离验收工具包括 `scripts/stage_plugin_candidates.py`（按当前源码暂存构建候选）、`scripts/prepare_managed_harness.py`（安装桌面内置 rc.1 与 npm rc.5 的隔离 Host 及本地 tarball）、`scripts/verify_managed_plugins.py`（真实宿主控制和原生流程）。临时报告与截图写入 `.local/plugin-managed-setup/`，服务与测试 profile 位于 `.runtime/plugin-managed-setup/`。候选构建可复用开发依赖；真实托管安装则从包内载荷创建新 Python 环境，不引用源码环境。

[TestWithProof 验收目录](.testwithproof/catalog.yaml) 区分真实 Host、提供方回归和模拟供应商的七服务联动。准备候选包和 Host 后，运行 `twp --project "$PWD" --json doctor` 与 `twp --project "$PWD" --json run`；随后用 `verify` 与 `export` 检查证据并导出报告。截图审阅由实际审阅者完成，自动测试不代替人工认可。当前改造按用户授权在各仓库 `main` 本地提交，并由总仓库 gitlink 固定组合；尚未推送或发布。正式发布前需分配新版本、提高最小 Core 依赖并对最终包摘要重验。
