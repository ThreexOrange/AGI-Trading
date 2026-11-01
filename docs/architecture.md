# 架构与当前边界

v0.2 添加本地审查门槛：`verification.py` 收集提交/源码/运行依赖哈希并验证 reviewer-authored 报告。CEX 在签名前、传输层在联网前、原生 CLI 在启动前、安装器在执行前、非 paper 订单在认领前检查报告。缺失、不批准、过期、内容变化或未解决高危问题都会拦截。没有环境变量跳过开关；但本地有代码执行权的人仍能绕过或伪造报告，不能将其当作对抗性安全边界。

审查材料包含未跟踪的源码文件，跳过依赖/构建/缓存及已知命名的私密文件；运行依赖另行逐文件哈希。哈希本身不鉴定行为安全。源码 checkout 必须可识别 Git 提交；wheel 安装不替代源码审查。独立 Agent/审计人员自行检查后导入报告，而非由项目自动给自身打高分。

CLI 解析结构化参数 → 对应平台适配器 → 官方 CLI / 官方 HTTPS API。输出统一为 JSON，包含实际观察时间。Binance/OKX 为链上钱包；Bitget/Bybit 为中心化交易所账户，不能互换地址或权限。

`agi_trading/providers/binance/` 与 `okx/` 将经过验证的参数数组传给官方 CLI，`shell=False`，不执行 API 返回的 `next` 命令。`bitget/` 与 `bybit/` 各自实现官方 HMAC 签名和受限的 spot API；共享的传输层拒绝重定向及非白名单 host，不自动重试写请求。

`orders.py` 保存预览、摘要、client order ID 和执行状态；不保存凭据或原始账户响应。执行路径：prepared → claimed → submission_unknown → submitted。验证失败为 validation_failed；中途终止可能保留 claimed/submission_unknown，需要读取订单实际状态，不得自动重新提交。

SQLite 支持同一个状态目录内多进程竞争认领。它不提供多个丢失/分叉的云环境之间的全局去重。重新创建计划生成新的 client order ID，因此新计划仍可能表达一笔重复交易；需要上层人工或策略逻辑识别。

限价单精度在预览和提交前检查，提交前进行保守余额检查（买单预留 1%）；平台最终检查仍具权威性。Bitget 的可用余额按 API `available` 字段；Bybit 从钱包余额扣除冻结和借贷字段，可能过度保守并拒绝本来可执行的订单。专用无借贷账户最适合本版。

默认限额是**单笔名义金额**，不是日限额、总仓位限制或最大亏损限制。已有仓位、所有其他运行进程及手工交易不在这个控制范围内。本版没有策略调度、WebSocket 成交追踪、撤单、自动止损、杠杆、衍生品、跨链路由、资金划转或提现。

钱包报价不会升级为链上交易执行。后续开放需要针对官方审计/模拟/risk verdict/限额/权限变更以及链上最终状态增加专项流程和测试。

不提供公共 HTTP 或 MCP 服务。当前可由有终端权限的 AI 助手通过 CLI 使用，也可导入 Python 适配器。ChatGPT 行情插件不会因为 GitHub 有了这个仓库就自动获得执行能力。

Binance/Bitget 官方依赖恢复用 npm lockfile 和 `npm ci --ignore-scripts`。OKX 直接从官方 release 下载固定版本 v4.6.7 的 CLI，并核对 `release.json` 固定的 SHA-256；下载器只接受 GitHub 官方发行资产域名，不安装 skills、workflows 或 A2A。升级版本时需要同时核对 release 和校验值。
