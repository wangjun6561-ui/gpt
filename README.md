# OKX 带单员实时监控（Flask版，Python 3.9）

一个轻量的 OKX 带单监控程序：
- 启动时拉取多个博主当前持仓；
- Flask 提供网页与 API；
- 监控交易记录，发现新交易后发送 Server酱/邮件通知；
- 同一博主当轮 >=3 条交易自动合并提醒；
- 支持 Windows / Linux。

## 1. 环境要求
- Python 3.9
- 基础 Python / Node 环境即可（不依赖重型前端构建链）

## 2. 安装与启动
```bash
pip install -r requirements.txt
cp config.example.json config.json
python app.py
```
访问：`http://127.0.0.1:8080`

## 3. 配置说明（config.json）
- `debug`: `true` 时打印关键调试日志。
- `traders`: 多博主配置，字段：`name`、`platform`、`uniqueName`。
- `okx.contract_values`: 合约面值映射，用于 `持仓币数 = pos * 合约面值`。
- `notification.serverchan` / `notification.email`: 通知开关与账号配置。
- `web.host` / `web.port`: Flask 服务监听地址与端口。

## 4. 页面展示逻辑
每个博主默认只展示一个币种，优先级：`ETH > BTC > SOL > 其他`。
展示字段：
- 币种、方向、杠杆、开仓均价
- 收益率（`uplRatio * 100`）
- 持仓量（按合约面值换算）
- 保证金、持仓价值、收益
- 保证金率（`mgnRatio * 100`）
- 预估爆仓价

未持仓博主会自动排到最后。

## 5. 历史与增量监控
- 首次运行会初始化 `data/trades_history.json`。
- 每轮拉取交易记录并与历史记录对比，识别新增交易。
- 同博主当轮新增 >=3 条会合并成 1 条通知。

## 6. 跨平台运行
- Windows：`python app.py` 或任务计划程序。
- Linux：`systemd` / `supervisor` 守护。

## 7. 调试模式
`config.json` 设置：
```json
{ "debug": true }
```
会输出拉取结果、增量检测、通知发送、历史保存等关键日志。
