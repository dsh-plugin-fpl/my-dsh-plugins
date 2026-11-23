# 联动验收

当前基础能力验收由 [dsh-core 验证记录](../../dsh-core/docs/verification.md)维护，包含独立看板配置和任务、HTTP/WS 权限与恢复、DSH 连接层隔离安装、公开调用方示例与资源交接。

当前组合为独立 Core 服务 + FPL 看板 + 可选 DSH 连接器。需要同时验证：关闭 DSH 后 Core 继续就绪、宿主回调任务明确中断并保留输出、重连恢复资源访问，以及独立运行包不依赖 FPL 源码或临时目录。

新增应用时，在这里登记“应用输入 → 公共能力任务 → 输出资源 → 应用接收”的场景。场景记录应用和 core 的版本、运行命令、结果及证据位置。提供方测试归各自仓库，联合场景验证真实交接。

临时报告与截图放总仓库 `.local/<任务>/`，正式场景说明与确定性用例纳入版本管理。


## 2026-11-23：Core 0.3.1 + 两工坊 0.1.0

组合命令：`dsh-core/.runtime/worker-venv/bin/python scripts/verify_workshops.py`。执行前构建三个 tarball，安装各工坊自身环境、DSH CLI、FFmpeg、Chrome。脚本属于联合工作区，使用提供方的公开 CLI/API 与提供方维护的开发夹具，不导入其私有业务模块。

通过场景：真实进程创建项目；FFmpeg 导入和处理 MP4；剪辑片段交接至视觉画布；读取目标自己的媒体原件；真实 Core WS 生成任务与资源分块发布图片；专用 Harness profile 安装三份 tarball；两应用中文目录与入口、图标可读；停止 Harness 后服务仍运行；Chrome 创建项目、项目列表明暗主题、1440 与 768 编辑页面，无页面异常或 HTTP 失败。

证据 `.local/workshops-integration/1795430801637205000/result.json` 全部为 true，`ui-result.json` 两应用 errors/failed 均为空，截图同目录。供应商执行采用确定性夹具，不涉及付费请求。旧 FPL 数据、桌面 profile 和真实凭据不进入测试。各应用自身回归分别 18 / 9 项 Python 与各 3 项 Node；Core 205 项 Python 与 8 项连接层测试。

两个服务归档在开发目录外解包并全新安装，空配置启动、通用素材回退、图标与项目创建通过，归档无持久状态与秘密。正式桌面安装由同期安装任务单独验收；本组合脚本不修改桌面 profile。


最终部署核对：正式 Core 9310 通过认证 API 确认无在途任务后，以正常启动器加载 0.3.1，原配置与数据保留；源码恢复点位于 Core 自身 `.runtime/workshop-transition/source-0.3.0/`。两个工坊通过自身 API 确认空项目后重载最终代码，9360 / 9361 均 ready，Core 配对和双向片段连接均保留。正式 Core 认证应用目录中的两个工坊均为 ready。

启动器新增隔离延迟退出进程回归，验证 stop 等待原 PID 真正退出，连续 start 不会误认旧进程。最新服务归档逐文件核对启动器、归档脚本、插件清单、locale 与验证文档，内容与已推送源码一致。同期桌面安装任务对头像及插件说明的工作树改动予以保留，不并入本次提交。

三维延迟加载补测通过：在独立视觉服务中新建项目、切换白模预演、创建场景并载入真实 Vue/Three 编辑器，canvas 可见，两个应用均无 pageerror 或 HTTP 失败。证据 `.local/workshops-integration/1795432149747640000/`，含 `dsh-visual-workshop-previs-editor.png`；对应步骤已纳入正式浏览器组合脚本。第三方模型格式与复杂场景负载仍不由此单一场景替代。
