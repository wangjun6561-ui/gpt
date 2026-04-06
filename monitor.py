"""Douyin comment count monitor.

使用方法：
1. 复制 ``monitor_config.example.json`` 为 ``monitor_config.json``，按照注释填写 Authorization token、Server 酱 sendkey 以及要监控的 aweme_id 列表。
2. ``authorization_token`` 字段只需要填写原 ``Bearer <token>`` 中的 ``<token>``，脚本会自动补全 ``Bearer `` 前缀。
3. 根据需要增加或减少 ``aweme_ids`` 列表中的条目，脚本会在每次轮询时自动读取最新的配置。
4. 运行 ``python monitor.py``，脚本会常驻进程，每 10 分钟请求一次接口，并在评论数增加时发送通知。
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Dict, Iterable

import requests

POLL_INTERVAL_SECONDS = 10 * 60
CONFIG_FILENAME = "monitor_config.json"
CACHE_FILENAME = "monitor_state.json"


log = logging.getLogger("douyin-monitor")


class ConfigError(RuntimeError):
    """Raised when configuration is invalid."""


def sc_send(sendkey: str, title: str, desp: str = "", options: dict | None = None) -> dict:
    """发送 Server 酱通知。

    Args:
        sendkey: Server 酱密钥。请将你的密钥填入 ``monitor_config.json`` 的 ``sendkey`` 字段。
        title: 通知标题。
        desp: 通知正文。
        options: 额外参数，可选。
    """

    if options is None:
        options = {}

    if sendkey.startswith("sctp"):
        match = re.match(r"sctp(\d+)t", sendkey)
        if not match:
            raise ValueError("Invalid sendkey format for sctp")
        num = match.group(1)
        url = f"https://{num}.push.ft07.com/send/{sendkey}.send"
    else:
        url = f"https://sctapi.ftqq.com/{sendkey}.send"

    payload = {"title": title, "desp": desp, **options}
    response = requests.post(url, json=payload, headers={"Content-Type": "application/json;charset=utf-8"}, timeout=30)
    response.raise_for_status()
    return response.json()


def load_config(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(
            f"配置文件 {path} 不存在，请先复制 monitor_config.example.json 并填写 token/sendkey/aweme_ids。"
        )

    with path.open("r", encoding="utf-8") as fp:
        try:
            config = json.load(fp)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"配置文件 {path} 不是有效的 JSON：{exc}") from exc

    for field in ("authorization_token", "sendkey", "aweme_ids"):
        if field not in config:
            raise ConfigError(f"配置文件缺少 {field} 字段")

    if not isinstance(config["aweme_ids"], Iterable) or isinstance(config["aweme_ids"], (str, bytes)):
        raise ConfigError("aweme_ids 必须是 aweme_id 字符串列表")

    aweme_ids = []
    for aweme_id in config["aweme_ids"]:
        if not isinstance(aweme_id, str) or not aweme_id.strip():
            raise ConfigError("aweme_ids 中包含空值，请检查")
        aweme_ids.append(aweme_id.strip())
    config["aweme_ids"] = aweme_ids

    token = config["authorization_token"].strip()
    if not token:
        raise ConfigError("authorization_token 不能为空，请填入 API 的 <token> 部分")
    if token.lower().startswith("bearer "):
        # 允许用户直接粘贴带 Bearer 的内容
        token = token[7:]
    config["authorization_token"] = token

    return config


def fetch_comment_count(aweme_id: str, token: str) -> int:
    url = "https://api.tikhub.io/api/v1/douyin/app/v3/fetch_one_video"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"aweme_id": aweme_id}

    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()

    try:
        return int(payload["data"]["aweme_detail"]["statistics"]["comment_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"响应中缺少 comment_count 字段: {payload}") from exc


def load_state(path: Path) -> Dict[str, int]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fp:
            raw = json.load(fp)
        return {k: int(v) for k, v in raw.items()}
    except (json.JSONDecodeError, ValueError, OSError):
        log.warning("无法读取历史状态文件 %s，将从空状态开始", path)
        return {}


def save_state(path: Path, state: Dict[str, int]) -> None:
    tmp_path = path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as fp:
        json.dump(state, fp, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def monitor_loop(config_path: Path, state_path: Path) -> None:
    last_counts = load_state(state_path)
    log.info("初始化历史评论数：%s", last_counts)

    while True:
        try:
            config = load_config(config_path)
        except ConfigError as exc:
            log.error("配置错误：%s", exc)
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        token = config["authorization_token"]
        sendkey = config["sendkey"]
        aweme_ids = config["aweme_ids"]

        current_counts: Dict[str, int] = {}
        for aweme_id in aweme_ids:
            try:
                count = fetch_comment_count(aweme_id, token)
            except Exception as exc:  # noqa: BLE001 - 记录并跳过
                log.exception("获取 aweme_id=%s 评论数失败: %s", aweme_id, exc)
                continue

            current_counts[aweme_id] = count
            previous = last_counts.get(aweme_id)
            log.info("aweme_id=%s 当前评论数 %s (上一次 %s)", aweme_id, count, previous)

            if previous is not None and count > previous:
                delta = count - previous
                title = f"aweme {aweme_id} 评论数增加 {delta}"
                desp = f"之前评论数：{previous}\n当前评论数：{count}"
                try:
                    result = sc_send(sendkey, title, desp)
                    log.info("通知已发送：%s", result)
                except Exception as exc:  # noqa: BLE001
                    log.exception("发送通知失败：%s", exc)

        last_counts = {k: v for k, v in {**last_counts, **current_counts}.items() if k in aweme_ids}
        save_state(state_path, last_counts)
        log.debug("保存最新状态：%s", last_counts)

        time.sleep(POLL_INTERVAL_SECONDS)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    setup_logging()
    base_dir = Path(__file__).resolve().parent
    config_path = base_dir / CONFIG_FILENAME
    state_path = base_dir / CACHE_FILENAME

    log.info("启动抖音评论监控，配置文件：%s", config_path)
    try:
        monitor_loop(config_path, state_path)
    except KeyboardInterrupt:
        log.info("收到中断信号，程序退出。")
        sys.exit(0)


if __name__ == "__main__":
    main()
