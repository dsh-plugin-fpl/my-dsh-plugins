# my-dsh-plugins

FPL 的 DeepSeek Harness 插件联合开发工作区：集中维护架构、Agent 开发规则、插件版本组合和联动验收，各插件保留独立仓库与发布能力。

`dsh-core` 独立提供公共模型、Agent、本地模型、任务与资源服务及 FPL 看板。DSH 通过可选连接层接入，业务状态由独立服务持有。后续 `dsh-plugin-*` 应用在这里联合维护，通过公开服务组合这些能力。

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

新增应用按 [插件接入流程](docs/adding-plugins.md) 登记，整套版本由总仓库固定。

## 整套开发入口

在本目录启动 Agent，先读取 [AGENTS.md](AGENTS.md)，修改插件前再读取插件自身规则。

- [架构与契约](docs/architecture.md)：职责、依赖方向、共享接口与联动原则。
- [开发流程](docs/development.md)：分支、跨仓库提交、版本更新与恢复。
- [新增插件](docs/adding-plugins.md)：新仓库接入与最低验收要求。
- [决策记录](docs/decisions.md)：工作区边界及工具行为的原因。
- [联动验收目录](tests/integration/README.md)：整套能力与后续应用交接的验收入口。

临时验收输出放 `.local/`，持久本地运行状态放 `.runtime/`。从 [dsh-core 使用说明](dsh-core/README.md) 开始配置和接入。
