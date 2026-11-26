# 新插件接入

## 独立仓库最低要求

在 future-props-lab 组织创建与职责对应的独立仓库；按实际发布策略选择可见性和许可证。先提交 README、AGENTS.md、忽略规则，再添加真实实现。README 说明功能成熟度、公开入口、依赖、配置与测试；未实现的部分明确写为规划，不添加虚假通过的占位测试。

插件必须支持独立克隆。基础开发规则直接保存在本仓库，涉及整套任务时引导回到 fpl-workspace；可参考 [Agent 指南模板](templates/plugin-agents.md)，将其中的包管理与测试命令替换为已实现入口。

## 注册到工作区

新插件日常开发与提交使用该仓库的 `main`。先确认插件首个提交已推送到 `main`，再从总仓库根目录运行（将示例名称替换为实际仓库名）：

```sh
git submodule add https://github.com/future-props-lab/dsh-example.git dsh-example
python3 scripts/workspace.py status
python3 scripts/workspace.py check
```

使用根目录直接子模块和完整 HTTPS URL；不要在外层用 `git add .` 将嵌套仓库误当普通目录加入。`.gitmodules` 是清单，索引 gitlink 是固定版本，不需要另建插件 JSON 清单或修改管理脚本。

如果插件目录已经存在，先检查它的仓库根目录、origin、修改、HEAD 和分支；不得覆盖、删除 .git 或重新初始化。只有确认属于目标仓库且提交已发布后才复用。

## 文档与验收

更新总仓库 README 的插件表和架构边界；正式接口仍放提供方仓库，避免在总仓库复制 schema。按需新增组合验收，公开工作区中不得放私有仓库凭据。

确认插件可独立克隆并运行其真实测试、缺少可选插件时反馈清楚、公开依赖声明完整。再从 GitHub 递归克隆整个工作区，确认新插件被还原、status 自动发现、check 通过；需要权限的仓库须明确说明访问要求。

最后显式暂存 `.gitmodules`、新插件 gitlink 和相关文档，在总仓库 `main` 按 [开发流程](development.md) 提交。推送总仓库前，确保被引用的插件提交已推送到插件 `main`；是否推送总仓库仍按用户授权执行。独立包发布及生产部署需要另行确定流程，不属于子模块登记动作。
