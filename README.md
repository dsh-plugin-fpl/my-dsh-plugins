# my-dsh-plugins

FPL 的 DeepSeek Harness 插件联合开发工作区：集中维护架构、Agent 开发规则、插件版本组合和联动验收，各插件保留独立仓库与发布能力。

当前只有 `dsh-core` 的文档脚手架，尚未实现公共能力或业务联动。此仓库不包含完整 FPL，也不要求本机存在 FPL 源码。

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
| dsh-core | [dsh-plugin-fpl/dsh-core](https://github.com/dsh-plugin-fpl/dsh-core) | 文档初始化；规划中的公共配置、能力适配与应用接入底座 |

未来插件按需增加，不能将此表中的规划视为已可调用的接口。

## 整套开发入口

在本目录启动 Agent，先读取 [AGENTS.md](AGENTS.md)，修改插件前再读取插件自身规则。

- [架构与契约](docs/architecture.md)：职责、依赖方向、共享接口与联动原则。
- [开发流程](docs/development.md)：分支、跨仓库提交、版本更新与恢复。
- [新增插件](docs/adding-plugins.md)：新仓库接入与最低验收要求。
- [决策记录](docs/decisions.md)：工作区边界及工具行为的原因。
- [联动验收目录](tests/integration/README.md)：后续业务验收的落点，目前没有业务联动实现。

临时验收输出放已忽略的 `.local/`，持久本地运行状态放 `.runtime/`，凭据与真实数据不入库。仓库公开不等于已授予开源许可；许可证待所有者明确选择。
