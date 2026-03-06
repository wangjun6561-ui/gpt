# BWEnews 实时监控与 AI 分析

一个可长期运行的 Python 脚本，用于：

1. **优先通过 WebSocket** 实时监听 BWEnews。
2. WebSocket 不可用时自动切到 **RSS fallback**。
3. 对新闻做去重，避免重复推送。
4. 每条新闻先推送 `BWEnews 快讯`（更清晰的 Markdown 排版）。
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

```bash
python main.py
```

或指定配置路径：

```bash
python main.py --config /path/to/config.json
```

## 行为说明（本次优化）

- 启动阶段会快速检查最新 `recent_news_limit` 条消息。
- 如果启动时有多条新消息：**只对最新 1 条做 AI 分析**，其余仅发快讯（节省算力并保证推送速度）。
- 若启动阶段命中本地已处理消息，会立即停止继续补发更旧消息。
- `BWEnews 快讯` 已改为更直观格式：标题 + 来源 + 时间 + 相关币 + 链接。
- 正常运行后，实时 WebSocket 新消息仍会进行完整 AI 分析。
