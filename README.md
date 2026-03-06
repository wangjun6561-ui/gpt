# BWEnews 实时监控与 AI 分析

一个可长期运行的 Python 脚本，用于：

1. **优先通过 WebSocket** 实时监听 BWEnews。
2. WebSocket 不可用时自动切到 **RSS fallback**。
3. 对新闻做去重，避免重复推送。
4. 每条新闻先推送 `BWEnews 快讯` 到 server酱。
5. 再调用 DeepSeek (`deepseek-chat`) 做市场影响分析。
6. 将分析结果再次推送到 server酱 (`AI新闻分析`)。

## 环境要求

- Python 3.10+

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置文件（不使用环境变量）

1. 复制示例配置：

```bash
cp config.example.json config.json
```

2. 编辑 `config.json`：

```json
{
  "deepseek_api_key": "你的 DeepSeek Key",
  "serverchan_sendkey": "你的 server酱 SendKey",
  "store_file": "seen_news.json",
  "recent_news_limit": 5
}
```

- `store_file`：本地存储文件，用于记录最近已推送消息（重启后继续去重）。
- `recent_news_limit`：只处理最新 N 条消息（默认 5）。

## 运行

默认读取当前目录下 `config.json`：

```bash
python main.py
```

也可以指定配置路径：

```bash
python main.py --config /path/to/config.json
```

## 行为说明（本次更新重点）

- 仅处理最新 `recent_news_limit` 条消息（默认 5 条）。
- 增加本地持久化去重：消息推送成功后会写入 `store_file`。
- 重新启动监控时，若在最新消息中命中本地已存在消息，会停止本轮继续推送（避免重复轰炸）。
- WebSocket 与 RSS 都可用时，仍优先 WebSocket（低延迟）。

## 程序结构

- `load_config()`：从 JSON 配置文件读取密钥和参数
- `PersistentRecentStore`：本地持久化最新消息 key
- `websocket_listener()`：WebSocket 实时监听 + 自动重连
- `rss_fallback()`：RSS 后备（仅拉取最新 N 条 + 命中即停止本轮）
- `analyze_with_deepseek()`：调用 DeepSeek Chat API
- `send_serverchan()`：推送 server酱
- `main_loop()`：主调度循环
