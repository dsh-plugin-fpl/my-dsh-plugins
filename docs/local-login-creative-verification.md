# 本机默认身份与网站创意工坊验收

日期：2026-11-25。

## 版本与行为

- Core：`d508f02`；原 FPL：`43810684`，产品 API 参考独立提交为 `04d21d04`。均为 main 本地提交，未推送或发布。
- 默认免密进入本机所有者；右上角可选登录 FPL 网站，网站身份不改变本机数据归属。原 Core 多账号入口保留在账号页及 `/login?core=1`。
- 左侧顺序为首页、创意工坊、应用、文件、集成中心、AI 能力。
- 创意工坊完整适配原站的浏览、草稿、发布与撤回；安装明确写入本机集成中心，默认停用。stdio MCP 保留待配置状态。
- 原站新增公开固定版本 package 接口；Core 验证归档、版本和依赖，再以本地事务安装并保存回执。服务间仅使用公开 HTTP 协议。
- 本机 Core 已通过正式启动器加载变更；启动前确认本机所有者无在途任务。原站源码已适配，但未部署或重启现有原站；连接的原站必须加载更新后的接口才能下载安装到本机。

## 通过的检查

| 检查 | 结果 |
| --- | --- |
| Core Python 全量回归 | 249 passed（含 9 项新增场景） |
| Core 连接层回归 | 20 passed |
| Core 全量 Chrome 回归 | 6 passed |
| 扩展两服务真实 Chrome 旅程 | 2 passed，方案包包含工具 API、HTTP MCP、stdio MCP、完整 Skill 附件 |
| 原站创意工坊与 SDK 契约回归 | 26 passed |
| 原站 Identity / Creative 独立服务和路由契约 | 17 passed |
| Core 构建、OpenAPI 生成、公开消费端编译 | 通过 |
| 原站 OpenAPI/Web 客户端、SDK、独立服务契约 | 通过 |
| 原站工程 Note 与产品文档保护 | 通过，产品文档独立提交 |
| 布局 | 明暗主题，1440 / 800 / 390 像素，检查截图无横向溢出 |

真实 HTTP 旅程使用原站自有隔离夹具及合成账号，覆盖登录、发布、包下载、本机禁用副本与附件下载、退出网站后继续本地访问。测试不使用正式网站账号，不向真实站点发布内容，不调用付费供应商。

Python 回归另覆盖 Origin/CSRF、本地账号隔离、远程会话过期与离线、网站账号切换、摘要篡改、名称冲突、依赖撤回、批量失败与 Skill 文件补偿、幂等回执以及原工坊授权码边界。

## 既有检查问题

- 原站架构检查：125 passed，1 failed。失败在未修改的 `backend/studio/apps/asset_library/references/references.py:180` 对 `session.info["owned_models"]` 的使用；任务开始前提交已经包含该代码。
- 原站组合 `npm run contracts:check` 的 SDK 文档阶段仍报告 `sdk-reference-files.md` 与 `sdk-reference-visual.md` 过期。通过任务开始前的 Git 内容重建生成器输入，确认这两项均为既有差异。本次只更新创意工坊参考及 SDK 覆盖表，未改写无关产品文档。

## 证据与复现

临时日志及基线分析在总仓库 `.local/fpl-creative/`；截图、Trace 和浏览器结果在 Core `.local/creative-browser/` 与 `.local/browser-results/`。它们均被 Git 忽略，不承载正式服务依赖。

```sh
# Core 目录；原站需要同一功能版本及其隔离服务夹具
FPL_SOURCE_REPOSITORY=/path/to/Future-Props-Lab \
CORE_TEST_BROWSER_CHANNEL=chrome pnpm --dir web test:e2e
```

正式本机配置沿用 `.runtime/` / 已选统一存储根目录；没有迁移、合并、删除或上传既有本机业务数据。
