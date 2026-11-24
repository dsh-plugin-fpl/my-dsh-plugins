# 联合开发与验证

## 开始工作

```sh
python3 scripts/workspace.py status
python3 scripts/workspace.py bootstrap
python3 scripts/workspace.py check
```

从总仓库启动 Agent，修改前显式读取目标插件的 AGENTS.md。直接打开插件时只依赖插件自身指南；涉及其他插件或整套规则时回到总工作区。不要用全局 Codex 配置改变 Git 根目录识别来掩盖规则缺失。

默认沿用总仓库和各插件当前已检出的分支，直接在这些分支上修改；不要因为开始新任务而新建或切换分支，也不要额外创建 worktree。各仓库分支独立。只有目标仓库处于 detached HEAD 时，才在该仓库创建开发分支；如果用户已指定目标分支，则切换到该分支。提交仍按用户授权执行。

## 管理命令语义

脚本只管理 `.gitmodules` 登记的直接子模块；插件内部若自行嵌套子模块，由该插件自己的文档与工具负责。配置读取使用 Git，自带结构检查不依赖插件包管理器。

`bootstrap` 先检查所有直接子模块，再初始化缺失项。已初始化插件的 HEAD 必须等于索引 gitlink，且无已暂存、未暂存或未跟踪修改；否则在任何初始化前停止。非空但未初始化的目标目录也会阻止操作。使用固定提交和 checkout 模式，不传 force、不使用 remote 更新、不自动切换已有分支。网络失败可能留下已完成的初始化；修复网络后重跑，不删除已完成结果。

`status` 只读列出根仓库和插件状态。upstream 的领先／落后只基于本机已有远端引用，无 upstream 会明确显示；未初始化和版本偏移作为状态显示。

`check` 校验工作树 `.gitmodules` 与索引 gitlink 配对、路径安全、初始化状态、版本匹配、必需文档和文档中的本地文件链接。登记与 gitlink 不一致、合并冲突或缺文档返回非零；普通文件的未提交改动仅警告，不阻止开发中检查。此命令不执行 fetch，不验证远端提交可达性，也不证明插件业务正确。

## 跨仓库变更

1. 明确接口提供方、调用方及兼容窗口，读取各仓库规则，先实现提供方的兼容接口。
2. 在各插件完成测试，明确暂存本次文件；按用户授权在当前分支提交。只有用户要求推送或发布时，才推送并核对远端提交。不要直接在 detached HEAD 上交付修改。
3. 验证真实联动场景，检查重试、取消、授权失败、部分失败与恢复。尚无实现时如实记录未覆盖项。
4. 在总仓库显式 `git add <插件目录>` 更新 gitlink，同时更新相关文档与验收记录；确认引用的插件提交已在远端 main 或正式发布标签可达。
5. 运行总仓库检查与适用测试，提交总仓库并推送。禁止自动批量提交和推送。

所有仓库无法原子发布，接口移除应在调用方迁移完成后单独进行。

## 更新与恢复固定版本

普通 `git pull` 不会保证子模块工作树同步。先 `status` 检查并提交或另行保存自己的修改，再更新总仓库，然后检查差异。

若已有插件 HEAD 与 gitlink 不同，bootstrap 会停止。确认插件没有修改、分支成果已保存后，人工运行 `git submodule update --init --checkout -- <插件目录>` 恢复固定提交；这可能进入 detached HEAD。不要使用 `reset --hard` 或 `clean` 解决版本偏移。

主动升级插件时，在插件中显式 fetch、选择目标提交并运行对应验收，然后更新总仓库 gitlink；没有自动跟踪“最新”的行为。回退组合时，同样先保护所有工作，再回退总仓库提交和相应固定版本。

## 验证矩阵

- 文档或清单：`python3 scripts/workspace.py check`，检查状态及链接。
- 管理脚本：`python3 -B -m unittest discover -s tests -p 'test_*.py' -v`；隔离夹具放 `.local/`，不访问真实远端。
- 插件行为：执行对应插件指南中的测试与构建，并更新使用文档。
- 跨插件接口：提供方契约测试、调用方兼容测试及真实联动验收；场景目录见 [联动验收](../tests/integration/README.md)。
- 版本组合交付：先 `git check-ignore .local/<任务>/fresh`，再向该位置从 GitHub 递归克隆，运行结构检查，证明无需原工作目录也可还原。

Python 可用 `uv run --no-project python` 替代；脚本无需第三方包。临时产物按根级规则落盘，测试夹具禁用真实用户 Git hooks 和签名，不修改全局配置。


## 三服务组合验收

分别运行 Core 与两个工坊自身的构建、测试和 `pnpm pack --pack-destination .runtime/packages`。随后从总工作区执行：

```sh
dsh-core/.runtime/worker-venv/bin/python scripts/verify_workshops.py
```

脚本使用 Core 自己维护的公开开发夹具，只替换供应商执行，不替换 Core WS、任务或资源实现。通过各工坊正常 CLI 建立隔离状态、会话、Core 配对及片段连接；使用真实 FFmpeg 与 Chrome，实际安装三份 tarball。所有输入、账号和素材均为隔离生成，秘密票据不输出。端口被其他实例占用时应先结束对应测试；不要清理真实服务或复用正式状态。

报告不代替带真实供应商凭据的付费验收。各服务的正式生命周期与数据迁移仍按其自身文档执行。桌面安装通过正常 DSH 插件管理，不手改 profile 的持久配置。


## 插件开关启停验收

构建并打包七个当前版本、安装各自独立服务环境后，执行 `node scripts/verify_plugin_lifecycle.mjs`。脚本从当前 tarball 装入真实 Cordis，在隔离存储、账号和动态端口验证七服务的启动、关闭、重新启用、Core 依赖停机与恢复；不修改桌面 profile。证据放 `.local/plugin-lifecycle/`，隔离插件环境放 `.runtime/plugin-lifecycle/`。旧业务联动脚本显式设置 manageService=false，由其外层夹具启动和停止进程。
