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

## 配置环境变量

```bash
export DEEPSEEK_API_KEY="你的 DeepSeek Key"
export SERVERCHAN_SENDKEY="你的 server酱 SendKey"
```

## 运行

```bash
python main.py
```

## 程序结构

- `websocket_listener()`：WebSocket 实时监听 + 自动重连
- `rss_fallback()`：RSS 轮询后备
- `analyze_with_deepseek()`：调用 DeepSeek Chat API
- `send_serverchan()`：推送 server酱
- `main_loop()`：主调度循环

## 说明

- 若 WebSocket 与 RSS 都可用，程序会优先处理 WebSocket（低延迟）。
- 去重使用内存缓存（固定上限），适合长期运行。
- 程序已包含日志输出和基础错误处理。
