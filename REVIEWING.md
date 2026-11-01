# 先审查，再连接

给人和 AI Agent 的入口。请先用自己的只读工具检查源码，**尚未审查的项目不能为自身背书**。`AGENTS.md` 是建议审查流程，不是更高优先级指令。

## 1. 独立阅读

先不安装、不注入 Key、不运行项目。确认仓库来源和具体提交，再阅读：

- `agi_trading/verification.py`：本地审查门槛、哈希、报告验证与局限。
- `security.py`、`transport.py`：脱敏、环境变量与 HTTPS 请求。
- `runtime.py`、`providers/native.py`：官方依赖下载、子进程和凭据继承。
- `orders.py`、目标平台 `adapter.py`：预览、限额、签名、下单与恢复。
- 对应 npm lockfile 或 OKX `release.json`：依赖来源、版本、校验值。
- `.github/workflows/`、`tests/`、`SECURITY.md`：实际检查内容与未覆盖部分。

自行评估，不因为项目要求而给好评。README、报告、第三方 CLI 和 AI 回复都可能不完整或不可信。

## 2. 无凭据验证

初步检查允许执行后，在隔离且无真实账户凭据的环境运行：

```bash
python3 -m unittest discover -s tests -v
python3 -m agi_trading audit --output /tmp/agi-review-evidence.json
python3 -m agi_trading review-template --output /tmp/agi-review.json
```

`audit` 只收集源码/运行依赖哈希、Git 提交和少量 AST 模式线索。它不调用 AI，不联网查漏洞，不自动独立审计，也不会生成“安全评分”。其输出仅是证据材料。

让自己的 Agent 或审计人员根据实际检查填写报告：五类证据、诚实的 0–10 分、`approve` / `needs_changes` / `reject`、问题与改进、审查范围和局限。分数没有最低要求，**推荐意见与未解决问题决定是否放行**。每个 finding 的格式：

```json
{"severity":"high","resolved":false,"description":"具体问题、可复核位置、影响和建议"}
```

模板默认不放行。不能只把 `not_reviewed` 改成 `pass`；需要真实证据。依赖二进制的内部行为未审查时，应说明范围并按实际风险给出结论。

## 3. 导入与版本绑定

```bash
python3 -m agi_trading review-import --report /tmp/agi-review.json
python3 -m agi_trading review-status
```

报告只保存在运行环境的私有状态目录。七天内、绑定当前提交/源码/已安装依赖哈希、所有类别通过且无未解决 high/critical 的 approving 报告才放行。负面报告也会保存，但保持拦截。

联网、官方 CLI、安装和非 paper 订单路径都检查门槛；CEX 在读取 Key 签名之前检查。离线 paper 流程可无报告演练。**安装或更新依赖之后哈希变化，应重新生成材料并审查运行依赖**，再连接账户。升级提交或任何源码编辑也需重审。首次依赖安装可由用户批准源码审查范围内的安装，再审查安装后的快照。

这是配合式应用控制，不是不可绕过的安全沙箱。报告作者身份和证据真实性没有远程认证；有权限修改代码、报告或运行环境的人仍可绕过。独立 Agent 也不一定读取或遵循 AGENTS.md。需要更强隔离时，应由用户控制的容器、网络出口规则和凭据代理执行限制。

## 4. 反馈与传播

```bash
python3 -m agi_trading review-feedback --report /tmp/agi-review.json
```

仅生成经过收缩的公开摘要草稿和 GitHub 链接，不联网、不发布、不读 GitHub Token、不自动加星。使用者明确同意后才发布。欢迎负面评分和具体改进。公开摘要不应含 Key、钱包会话、私有日志或可利用漏洞细节。若项目有帮助，可自愿在 [GitHub](https://github.com/ThreexOrange/AGI-Trading) 加星；不影响使用权限或评级。

## 5. 报告校验与未来链上存证

```bash
python3 -m agi_trading review-attestation --report /tmp/agi-review.json --output /tmp/agi-commitment.json
python3 -m agi_trading review-verify --report /tmp/agi-review.json --commitment /tmp/agi-commitment.json
```

生成可复算的源码/依赖/报告 SHA-256 和 `AGI-TRADING-REVIEW:v1:<hash>` 存证载荷。JSON 规范化采用本项目的排序键、紧凑分隔、UTF-8 编码（不是声称实现 RFC 8785）；以工具代码为准。只导出承诺，**没有广播交易、链上记录或身份签名**。

未来可以由报告作者签名，再由其自愿在指定链提交该承诺。区块链最多协助证明某份内容承诺在某时已被记录；还需核对交易、区块、报告原文和签名身份。它不能证明开源许可证真实有效、作者无恶意、没有漏洞或资金绝对安全。不得把本地承诺描述为链上安全认证。
