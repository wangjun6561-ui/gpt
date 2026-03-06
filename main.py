#!/usr/bin/env python3
"""实时监控 BWEnews 并进行 AI 分析推送。"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
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
DEFAULT_RECENT_NEWS_LIMIT = 5

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
class AppConfig:
    deepseek_api_key: str
    serverchan_sendkey: str
    store_file: str
    recent_news_limit: int


@dataclass
class NewsItem:
    title: str
    url: str
    timestamp: int
    source: str
    coins: list[str] = field(default_factory=list)

    @property
    def dt_str(self) -> str:
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


class PersistentRecentStore:
    """本地持久化最近新闻 key，仅保留最新 N 条。"""

    def __init__(self, file_path: str, max_items: int = DEFAULT_RECENT_NEWS_LIMIT) -> None:
        self.file_path = Path(file_path)
        self.max_items = max_items
        self._lock = threading.Lock()
        self._keys: Deque[str] = deque(maxlen=max_items)
        self._load()

    def _load(self) -> None:
        if not self.file_path.exists():
            return
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
            keys = data.get("keys", []) if isinstance(data, dict) else []
            if isinstance(keys, list):
                for key in keys[-self.max_items :]:
                    if isinstance(key, str) and key.strip():
                        self._keys.append(key)
            logging.info("已加载本地消息缓存: %s (%d 条)", self.file_path, len(self._keys))
        except Exception as exc:
            logging.warning("读取本地消息缓存失败，将使用空缓存: %s", exc)

    def _persist(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"keys": list(self._keys)}
        self.file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def contains(self, key: str) -> bool:
        with self._lock:
            return key in self._keys

    def add(self, key: str) -> None:
        with self._lock:
            if key in self._keys:
                return
            self._keys.append(key)
            self._persist()


class Deduplicator:
    """进程内去重缓存（用于高频重复消息）。"""

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


def load_config(config_path: str) -> AppConfig:
    path = Path(config_path)
    if not path.exists():
        raise RuntimeError(f"配置文件不存在: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"配置文件 JSON 格式错误: {path} ({exc})") from exc

    deepseek_api_key = str(data.get("deepseek_api_key", "")).strip()
    serverchan_sendkey = str(data.get("serverchan_sendkey", "")).strip()
    store_file = str(data.get("store_file", "seen_news.json")).strip() or "seen_news.json"

    recent_news_limit_raw = data.get("recent_news_limit", DEFAULT_RECENT_NEWS_LIMIT)
    try:
        recent_news_limit = int(recent_news_limit_raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("配置文件 recent_news_limit 必须为整数") from exc

    if not deepseek_api_key:
        raise RuntimeError("配置文件缺少 deepseek_api_key")
    if not serverchan_sendkey:
        raise RuntimeError("配置文件缺少 serverchan_sendkey")
    if recent_news_limit <= 0:
        raise RuntimeError("配置文件 recent_news_limit 必须大于 0")

    return AppConfig(
        deepseek_api_key=deepseek_api_key,
        serverchan_sendkey=serverchan_sendkey,
        store_file=store_file,
        recent_news_limit=recent_news_limit,
    )


def build_dedup_key(item: NewsItem) -> str:
    return f"{item.title.strip()}|{item.url.strip()}"


def send_serverchan(sendkey: str, title: str, body: str) -> None:
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
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logging.exception("DeepSeek 调用失败: %s", exc)
        return "AI 分析暂时不可用（DeepSeek API 调用失败）。"


def format_news_quick_message(item: NewsItem) -> str:
    coin_text = ", ".join(item.coins) if item.coins else "未提及"
    return (
        f"### {item.title}\n\n"
        f"- 来源：`{item.source}`\n"
        f"- 时间：`{item.dt_str}`\n"
        f"- 相关币：`{coin_text}`\n"
        f"- 链接：{item.url or '无'}"
    )


def format_news_analysis_message(item: NewsItem, analysis: str) -> str:
    return f"### {item.title}\n\n{analysis}"


def handle_news(item: NewsItem, sendkey: str, deepseek_api_key: str, do_analysis: bool = True) -> None:
    logging.info("接收到新闻: %s", item.title)

    send_serverchan(sendkey, "BWEnews 快讯", format_news_quick_message(item))

    if not do_analysis:
        logging.info("跳过 AI 分析（节省算力）: %s", item.title)
        return

    analysis = analyze_with_deepseek(deepseek_api_key, item.title)
    send_serverchan(sendkey, "AI新闻分析", format_news_analysis_message(item, analysis))


def parse_ws_message(raw: str) -> Optional[NewsItem]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logging.debug("忽略非 JSON 消息: %s", raw)
        return None

    title = str(data.get("news_title", "")).strip()
    url = str(data.get("url", "")).strip()
    timestamp = data.get("timestamp")
    coins_raw = data.get("coins_included", [])

    if not title:
        return None
    if not isinstance(timestamp, int):
        timestamp = int(time.time())

    coins: list[str] = []
    if isinstance(coins_raw, list):
        coins = [str(c).strip() for c in coins_raw if str(c).strip()]

    return NewsItem(
        title=title,
        url=url,
        timestamp=timestamp,
        source=str(data.get("source_name", "BWENEWS")),
        coins=coins,
    )


def websocket_listener(stop_event: threading.Event):
    while not stop_event.is_set():
        ws = None
        try:
            logging.info("尝试连接 WebSocket: %s", WS_URL)
            ws = websocket.create_connection(
                WS_URL,
                timeout=15,
                http_proxy_host=None,
                http_proxy_port=None,
            )
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


def process_news_item(
    item: NewsItem,
    dedup: Deduplicator,
    store: PersistentRecentStore,
    sendkey: str,
    deepseek_api_key: str,
    do_analysis: bool,
) -> bool:
    key = build_dedup_key(item)
    if dedup.seen(key):
        return False
    if store.contains(key):
        return False

    handle_news(item, sendkey, deepseek_api_key, do_analysis=do_analysis)
    store.add(key)
    return True


def build_news_item_from_rss_entry(entry, now_ts: int) -> Optional[NewsItem]:
    title = str(getattr(entry, "title", "")).strip()
    if not title:
        return None
    url = str(getattr(entry, "link", "")).strip()
    return NewsItem(title=title, url=url, timestamp=now_ts, source="RSS")


def bootstrap_latest_from_rss(
    dedup: Deduplicator,
    store: PersistentRecentStore,
    sendkey: str,
    deepseek_api_key: str,
    recent_limit: int,
) -> None:
    """启动时快速处理最新 N 条：仅分析最新1条，其余只发快讯。"""
    try:
        feed = feedparser.parse(RSS_URL)
        entries = feed.entries[:recent_limit]
        now_ts = int(time.time())

        analyzed_once = False
        for entry in entries:
            item = build_news_item_from_rss_entry(entry, now_ts)
            if item is None:
                continue

            key = build_dedup_key(item)
            if store.contains(key):
                logging.info("启动阶段命中本地存储，停止补发: %s", item.title)
                break

            pushed = process_news_item(
                item,
                dedup,
                store,
                sendkey,
                deepseek_api_key,
                do_analysis=not analyzed_once,
            )
            if pushed and not analyzed_once:
                analyzed_once = True

    except Exception as exc:
        logging.warning("启动阶段 RSS 预热失败，继续 WebSocket 实时监听: %s", exc)


def rss_fallback(
    dedup: Deduplicator,
    store: PersistentRecentStore,
    sendkey: str,
    deepseek_api_key: str,
    stop_event: threading.Event,
    max_cycles: int = 1,
    recent_limit: int = DEFAULT_RECENT_NEWS_LIMIT,
) -> None:
    logging.info("进入 RSS fallback 模式: %s", RSS_URL)
    cycles = 0

    while not stop_event.is_set() and cycles < max_cycles:
        try:
            feed = feedparser.parse(RSS_URL)
            entries = feed.entries[:recent_limit]
            now_ts = int(time.time())

            for entry in entries:
                item = build_news_item_from_rss_entry(entry, now_ts)
                if item is None:
                    continue

                key = build_dedup_key(item)
                if store.contains(key):
                    logging.info("RSS 命中本地存储，停止本轮推送: %s", item.title)
                    break

                process_news_item(
                    item,
                    dedup,
                    store,
                    sendkey,
                    deepseek_api_key,
                    do_analysis=False,
                )

        except Exception as exc:
            logging.exception("RSS fallback 轮询异常: %s", exc)

        cycles += 1
        if cycles < max_cycles and stop_event.wait(RSS_POLL_INTERVAL):
            break


def main_loop(config: AppConfig) -> None:
    dedup = Deduplicator()
    store = PersistentRecentStore(config.store_file, max_items=config.recent_news_limit)
    stop_event = threading.Event()

    def _signal_handler(signum, frame):
        del frame
        logging.info("收到退出信号(%s)，准备停止...", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # 启动时先快速补齐最近消息：仅分析最新1条，尽快把关键信息推给你。
    bootstrap_latest_from_rss(
        dedup,
        store,
        config.serverchan_sendkey,
        config.deepseek_api_key,
        recent_limit=config.recent_news_limit,
    )

    while not stop_event.is_set():
        ws_stream = websocket_listener(stop_event)
        try:
            while not stop_event.is_set():
                state, item = next(ws_stream)
                if state == "connected" and item is not None:
                    process_news_item(
                        item,
                        dedup,
                        store,
                        config.serverchan_sendkey,
                        config.deepseek_api_key,
                        do_analysis=True,
                    )
                elif state == "disconnected":
                    rss_fallback(
                        dedup,
                        store,
                        config.serverchan_sendkey,
                        config.deepseek_api_key,
                        stop_event,
                        max_cycles=1,
                        recent_limit=config.recent_news_limit,
                    )
                    break
        except StopIteration:
            break
        except Exception as exc:
            logging.exception("主循环异常: %s", exc)
            if stop_event.wait(2):
                break


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BWEnews 实时监控与 AI 分析推送")
    parser.add_argument("-c", "--config", default="config.json", help="配置文件路径（默认: config.json）")
    return parser.parse_args()


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


if __name__ == "__main__":
    setup_logging()
    args = parse_args()
    app_config = load_config(args.config)
    main_loop(app_config)
