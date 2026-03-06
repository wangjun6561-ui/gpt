#!/usr/bin/env python3
"""实时监控 BWEnews 并进行 AI 分析推送。"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Deque, Optional

import feedparser
import requests
import websocket

WS_URL = "wss://bwenews-api.bwe-ws.com/ws"
RSS_URL = "https://rss-public.bwe-ws.com/"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

SERVERCHAN_ENDPOINT = "https://sctapi.ftqq.com/{sendkey}.send"

WS_RECONNECT_DELAY = 5
RSS_POLL_INTERVAL = 20
DEEPSEEK_TIMEOUT = 30
SERVERCHAN_TIMEOUT = 10

DEDUP_MAX_SIZE = 5000

PROMPT_TEMPLATE = """你是一名专业的 Web3 / 加密货币市场分析师，擅长根据突发新闻快速判断市场影响。
任务：当我提供一条新闻时，请快速判断该新闻对 Web3 市场及相关加密货币的影响。
要求：先给结论，再给极简理由，不要长篇分析。

请按照以下格式输出：

【市场结论】
整体影响：强利多 / 利多 / 中性 / 利空 / 强利空
影响概率：X%

【可能受影响的币】
列出3–5个最可能受影响的币种

币种 | 方向 | 概率
BTC | 利多/利空 | X%
ETH | 利多/利空 | X%
XXX | 利多/利空 | X%

【一句话原因】
用1–2句话说明逻辑即可

【交易参考】
预估影响时间（最低可以用分钟为单位） xxxx
最可能受益或受损的币：XXX

新闻：
{news}
"""


@dataclass
class NewsItem:
    """统一的新闻结构。"""

    title: str
    url: str
    timestamp: int
    source: str

    @property
    def dt_str(self) -> str:
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


class Deduplicator:
    """使用内存缓存去重，支持固定上限，避免无限增长。"""

    def __init__(self, max_size: int = DEDUP_MAX_SIZE) -> None:
        self.max_size = max_size
        self._keys: set[str] = set()
        self._queue: Deque[str] = deque()
        self._lock = threading.Lock()

    def seen(self, key: str) -> bool:
        with self._lock:
            if key in self._keys:
                return True
            self._keys.add(key)
            self._queue.append(key)
            if len(self._queue) > self.max_size:
                removed = self._queue.popleft()
                self._keys.discard(removed)
            return False


def build_dedup_key(item: NewsItem) -> str:
    return f"{item.title.strip()}|{item.url.strip()}"


def send_serverchan(sendkey: str, title: str, body: str) -> None:
    """推送消息到 server酱。"""
    endpoint = SERVERCHAN_ENDPOINT.format(sendkey=sendkey)
    payload = {"title": title, "desp": body}
    try:
        resp = requests.post(endpoint, data=payload, timeout=SERVERCHAN_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            logging.warning("Server酱返回异常: %s", data)
        else:
            logging.info("Server酱推送成功: %s", title)
    except Exception as exc:
        logging.exception("Server酱推送失败: %s", exc)


def analyze_with_deepseek(api_key: str, news_title: str) -> str:
    """调用 DeepSeek Chat API 分析新闻。"""
    prompt = PROMPT_TEMPLATE.format(news=news_title)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是专业Web3市场分析师。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }

    try:
        resp = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=DEEPSEEK_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        return content
    except Exception as exc:
        logging.exception("DeepSeek 调用失败: %s", exc)
        return "AI 分析暂时不可用（DeepSeek API 调用失败）。"


def handle_news(item: NewsItem, sendkey: str, deepseek_api_key: str) -> None:
    """处理单条新闻：推送快讯 -> AI分析 -> 推送分析。"""
    logging.info("接收到新闻: %s", item.title)

    quick_body = f"{item.title}\n{item.url}\n{item.dt_str}"
    send_serverchan(sendkey, "BWEnews 快讯", quick_body)

    analysis = analyze_with_deepseek(deepseek_api_key, item.title)
    analysis_body = f"{item.title}\n\n{analysis}"
    send_serverchan(sendkey, "AI新闻分析", analysis_body)


def parse_ws_message(raw: str) -> Optional[NewsItem]:
    """解析 WebSocket 消息。"""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logging.debug("忽略非 JSON 消息: %s", raw)
        return None

    title = str(data.get("news_title", "")).strip()
    url = str(data.get("url", "")).strip()
    timestamp = data.get("timestamp")

    if not title:
        return None

    if not isinstance(timestamp, int):
        timestamp = int(time.time())

    return NewsItem(
        title=title,
        url=url,
        timestamp=timestamp,
        source=str(data.get("source_name", "BWENEWS")),
    )


def websocket_listener(stop_event: threading.Event):
    """持续监听 WebSocket；断开时重连。"""
    while not stop_event.is_set():
        ws = None
        try:
            logging.info("尝试连接 WebSocket: %s", WS_URL)
            ws = websocket.create_connection(WS_URL, timeout=15)
            logging.info("WebSocket 已连接")

            while not stop_event.is_set():
                raw = ws.recv()
                if raw is None:
                    raise ConnectionError("WebSocket recv 返回空")
                yield "connected", parse_ws_message(raw)

        except Exception as exc:
            logging.warning("WebSocket 连接/监听异常，将重连: %s", exc)
            yield "disconnected", None
            if stop_event.wait(WS_RECONNECT_DELAY):
                break
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass


def rss_fallback(dedup: Deduplicator, sendkey: str, deepseek_api_key: str, stop_event: threading.Event) -> None:
    """RSS 轮询后备逻辑。"""
    logging.info("进入 RSS fallback 模式: %s", RSS_URL)
    while not stop_event.is_set():
        try:
            feed = feedparser.parse(RSS_URL)
            entries = feed.entries[:20]
            now_ts = int(time.time())

            for entry in reversed(entries):
                title = str(getattr(entry, "title", "")).strip()
                url = str(getattr(entry, "link", "")).strip()
                if not title:
                    continue

                item = NewsItem(title=title, url=url, timestamp=now_ts, source="RSS")
                key = build_dedup_key(item)
                if dedup.seen(key):
                    continue
                handle_news(item, sendkey, deepseek_api_key)

        except Exception as exc:
            logging.exception("RSS fallback 轮询异常: %s", exc)

        if stop_event.wait(RSS_POLL_INTERVAL):
            break


def main_loop() -> None:
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    sendkey = os.getenv("SERVERCHAN_SENDKEY", "").strip()

    if not deepseek_api_key:
        raise RuntimeError("缺少环境变量 DEEPSEEK_API_KEY")
    if not sendkey:
        raise RuntimeError("缺少环境变量 SERVERCHAN_SENDKEY")

    dedup = Deduplicator()
    stop_event = threading.Event()

    def _signal_handler(signum, frame):
        logging.info("收到退出信号(%s)，准备停止...", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    ws_stream = websocket_listener(stop_event)
    while not stop_event.is_set():
        try:
            state, item = next(ws_stream)
            if state == "connected" and item is not None:
                key = build_dedup_key(item)
                if dedup.seen(key):
                    logging.debug("跳过重复新闻: %s", item.title)
                    continue
                handle_news(item, sendkey, deepseek_api_key)
            elif state == "disconnected":
                rss_fallback(dedup, sendkey, deepseek_api_key, stop_event)
        except StopIteration:
            break
        except Exception as exc:
            logging.exception("主循环异常: %s", exc)
            if stop_event.wait(2):
                break


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


if __name__ == "__main__":
    setup_logging()
    main_loop()
