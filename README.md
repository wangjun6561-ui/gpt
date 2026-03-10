# OKX 带单员实时监控（Python 3.9）

一个**纯 Python（无 Web 框架）**的 OKX 带单监控程序：
- 启动时拉取多个博主当前持仓；
- 网页端实时展示（适配桌面/手机）；
- 轮询监控交易记录，发现新操作后发送 Server酱 / 邮件通知；
- 多条同博主交易自动合并通知（>=3 条）；
- 支持 Windows / Linux。

## 1. 环境要求
- Python 3.9
- 可联网访问 OKX 与通知接口

## 2. 安装与启动
```bash
pip install -r requirements.txt
cp config.example.json config.json
# 编辑 config.json 填入博主 uniqueName 与通知配置
python app.py
```
启动后访问：`http://127.0.0.1:8080`

## 3. 配置说明（config.json）
- `debug`: true 时输出关键步骤调试信息。
- `traders`: 可配置多个博主，字段包含：`name`、`platform`（当前仅 okx）、`uniqueName`。
- `okx.contract_values`: 合约面值映射，用于计算“持仓币数 = pos × 合约面值”。
- `notification.serverchan` / `notification.email`: 通知开关与账号。

## 4. 页面展示字段
默认每个博主只展示一个币种，按优先级选择：`ETH > BTC > SOL > 其他`。
展示内容：
- 币种（如 eth/usdt）
- 开单方向（多/空）
- 杠杆
- 开仓均价（低价币自动保留更多小数）
- 收益率（`uplRatio * 100`）
- 持仓量（按合约面值换算）
- 保证金、持仓价值、收益
- 保证金率（`mgnRatio * 100`）与风险提示（<100%）
- 预估爆仓价（接口无值时显示 `--`）

未持仓账户会自动排序到列表最后。

## 5. 交易监控逻辑
1. 首次运行先加载（或初始化）`data/trades_history.json`；
2. 每轮拉取交易记录，与历史记录做差集，识别新增交易；
3. 同一博主当轮新增 >=3 条时合并成 1 条批量通知；
4. 发送 Server酱、邮件（按配置启用）；
5. 保存最新历史记录，避免重复提醒。

## 6. 跨平台运行建议
- Windows：可用 `python app.py` 或任务计划程序。
- Linux：可配 systemd / supervisor 守护。
- 配置文件与数据文件均使用 UTF-8，路径采用相对路径，兼容两端。

## 7. 调试模式
`config.json` 中设置：
```json
{ "debug": true }
```
程序会输出：拉取结果、差异数量、通知发送、历史保存等关键日志。
