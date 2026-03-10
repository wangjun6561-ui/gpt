import json
import os
import smtplib
import threading
import time
import random
from dataclasses import dataclass
from datetime import datetime
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Flask, jsonify, render_template, request


@dataclass
class TraderConfig:
    name: str
    platform: str
    unique_name: str


class OKXMonitor:
    POSITION_URL = "https://www.okx.com/priapi/v5/ecotrade/public/community/user/position-current"
    TRADES_URL = "https://www.okx.com/priapi/v5/ecotrade/public/community/user/trade-records"
    FOLLOW_RANK_URL = "https://www.okx.com/priapi/v5/ecotrade/public/follow-rank"
    ALL_RANK_TYPES = ["", "yieldRatio", "pnl", "winRatio", "aum", "traderFollowerLimit", "followTotalPnl"]

    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self.debug = bool(self.config.get("debug", False))
        self.state_lock = threading.Lock()
        self.refresh_lock = threading.Lock()
        self.running = False
        self.last_refresh_time = ""

        self.contract_values = self.config.get("okx", {}).get("contract_values", {
            "ETH-USDT-SWAP": 0.1,
            "BTC-USDT-SWAP": 0.01,
            "SOL-USDT-SWAP": 1,
        })
        self.base_traders = self._load_traders()
        self.traders = list(self.base_traders)
        self.current_rank_type = "__config__"

        data_dir = Path(self.config.get("data_dir", "data"))
        data_dir.mkdir(parents=True, exist_ok=True)
        self.trades_history_file = str(data_dir / "trades_history.json")

        self.previous_trades: Dict[str, List[str]] = {}
        self.latest_positions: Dict[str, Dict[str, Any]] = {}
        self._position_cursor = 0
        self._load_trades_history()

    @staticmethod
    def _trader_url(unique_name: str) -> str:
        return f"https://www.okx.com/zh-hans/copy-trading/account/{unique_name}?tab=trade"

    def _get_traders_snapshot(self) -> List[TraderConfig]:
        with self.refresh_lock:
            return list(self.traders)

    @property
    def http_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9",
            "x-locale": "zh_CN",
            "x-utc": "8",
            "x-zkdex-env": "0",
            "Referer": "https://www.okx.com/",
            "Origin": "https://www.okx.com",
        }

    def _log_debug(self, message: str):
        if self.debug:
            print(f"[DEBUG] {message}")

    @staticmethod
    def _load_config(config_path: str) -> Dict[str, Any]:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"未找到配置文件: {config_path}，请先复制 config.example.json 为 config.json")
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_traders(self) -> List[TraderConfig]:
        traders: List[TraderConfig] = []
        for item in self.config.get("traders", []):
            if str(item.get("platform", "")).lower() != "okx":
                continue
            traders.append(TraderConfig(name=item["name"], platform="okx", unique_name=item["uniqueName"]))
        if not traders:
            raise ValueError("config.json 中未配置 okx 博主")
        return traders

    def _load_trades_history(self):
        try:
            if not os.path.exists(self.trades_history_file):
                print("ℹ️  未找到交易历史数据文件，将创建新文件")
                return
            with open(self.trades_history_file, "r", encoding="utf-8") as f:
                history_data = json.load(f)
            loaded = history_data.get("trades", {})
            normalized: Dict[str, List[str]] = {}
            for account, records in loaded.items():
                if not isinstance(records, list):
                    continue
                normalized[account] = [str(r) if not isinstance(r, dict) else self._trade_id(r) for r in records]
            self.previous_trades = normalized
            if self.previous_trades:
                print(f"✓ 已加载交易历史数据 (上次更新: {history_data.get('last_update', '')})")
                print(f"  包含 {len(self.previous_trades)} 个账户的历史记录")
        except Exception as e:
            print(f"⚠️  加载交易历史数据失败: {e}，将重新开始")
            self.previous_trades = {}

    def _save_trades_history(self):
        try:
            history_data = {
                "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "trades": self.previous_trades,
                "version": "3.2",
            }
            with open(self.trades_history_file, "w", encoding="utf-8") as f:
                json.dump(history_data, f, ensure_ascii=False, indent=2)
            self._log_debug(f"交易历史数据已保存: {self.trades_history_file}")
        except Exception as e:
            print(f"❌ 保存交易历史数据失败: {e}")

    @staticmethod
    def format_number(num: Any, max_decimals: int = 4) -> str:
        try:
            value = float(num)
        except (TypeError, ValueError):
            return "0"
        if value == 0:
            return "0"
        abs_value = abs(value)
        if abs_value >= 1000:
            decimals = 2
        elif abs_value >= 1:
            decimals = min(max_decimals, 4)
        else:
            decimals = min(max_decimals + 2, 8)
        text = f"{value:.{decimals}f}"
        return text.rstrip("0").rstrip(".") if "." in text else text

    def _http_get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if params:
            query = urlencode(params)
            url = f"{url}{'&' if '?' in url else '?'}{query}"
        req = Request(url, headers=self.http_headers, method="GET")
        try:
            with urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}") from e
        except URLError as e:
            raise RuntimeError(str(e)) from e

    def _http_post_json(self, url: str, data: Dict[str, Any]) -> Dict[str, Any]:
        headers = dict(self.http_headers)
        headers["Content-Type"] = "application/json"
        req = Request(url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST")
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _request_with_retry(self, fn, hint: str) -> Optional[Dict[str, Any]]:
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                result = fn()
                time.sleep(random.uniform(0.3, 0.5))
                return result
            except Exception as e:
                if attempt == max_attempts:
                    print(f"❌ {hint}失败(重试{max_attempts}次): {e}")
                    return None
                wait_s = random.uniform(0.3, 0.5)
                self._log_debug(f"{hint} 第{attempt}次失败: {e}，{wait_s:.2f}s后重试")
                time.sleep(wait_s)
        return None

    def fetch_okx_positions(self, unique_name: str) -> Optional[List[Dict[str, Any]]]:
        def _req():
            payload = self._http_get_json(self.POSITION_URL, params={"uniqueName": unique_name})
            if payload.get("code") != "0":
                raise RuntimeError(f"OKX code={payload.get('code')}")
            return payload

        payload = self._request_with_retry(_req, f"获取持仓 {unique_name}")
        if not payload:
            return None
        data = payload.get("data", [])
        return data[0].get("posData", []) if data else []

    def fetch_okx_trades(self, unique_name: str, limit: int = 8) -> Optional[Dict[str, Any]]:
        def _req():
            payload = self._http_get_json(f"{self.TRADES_URL}?uniqueName={unique_name}&limit={limit}")
            if payload.get("code") != "0":
                raise RuntimeError(f"OKX code={payload.get('code')}")
            return payload

        return self._request_with_retry(_req, f"获取交易记录 {unique_name}")

    def fetch_follow_rank_traders(self, rank_type: str = "") -> List[TraderConfig]:
        okx_conf = self.config.get("okx", {})
        page_size = int(okx_conf.get("follow_rank_size", 9))
        pages = max(1, int(okx_conf.get("follow_rank_pages", 1)))

        all_traders: List[TraderConfig] = []
        seen: Set[str] = set()

        for page in range(1, pages + 1):
            def _req():
                params = {
                    "size": str(page_size),
                    "type": rank_type,
                    "start": str(page),
                    "latestNum": str(okx_conf.get("follow_rank_latest_num", 90)),
                    "fullState": str(okx_conf.get("follow_rank_full_state", 0)),
                    "apiTrader": str(okx_conf.get("follow_rank_api_trader", 0)),
                    "instNumLimit": str(okx_conf.get("follow_rank_inst_num_limit", 4)),
                    "dataVersion": datetime.now().strftime("%Y%m%d%H%M%S"),
                    "t": str(int(time.time() * 1000)),
                }
                payload = self._http_get_json(self.FOLLOW_RANK_URL, params=params)
                if payload.get("code") != "0":
                    raise RuntimeError(f"OKX code={payload.get('code')}")
                return payload

            payload = self._request_with_retry(_req, f"获取带单排行 第{page}页")
            if not payload:
                continue

            rows = payload.get("data", []) or []
            ranks = rows[0].get("ranks", []) if rows and isinstance(rows[0], dict) else []
            for row in ranks:
                unique_name = str(row.get("uniqueName", "")).strip()
                if not unique_name or unique_name in seen:
                    continue
                seen.add(unique_name)
                all_traders.append(TraderConfig(
                    name=str(row.get("nickName", unique_name)),
                    platform="okx",
                    unique_name=unique_name,
                ))

        return all_traders

    def switch_to_rank_traders(self, rank_type: str = "") -> int:
        traders = self.fetch_follow_rank_traders(rank_type)
        if not traders:
            return 0

        with self.refresh_lock:
            self.traders = list(traders)
            self._position_cursor = 0
            self.current_rank_type = rank_type
            # 切换为临时列表时只清空内存快照，不修改历史文件
            self.previous_trades = {t.unique_name: self.previous_trades.get(t.unique_name, []) for t in self.traders}

        with self.state_lock:
            self.latest_positions = {}

        self.refresh_positions()
        return len(traders)

    def switch_to_config_traders(self) -> int:
        with self.refresh_lock:
            self.traders = list(self.base_traders)
            self._position_cursor = 0
            self.current_rank_type = "__config__"
            self.previous_trades = {t.unique_name: self.previous_trades.get(t.unique_name, []) for t in self.traders}

        with self.state_lock:
            self.latest_positions = {}

        self.refresh_positions()
        return len(self.traders)

    def switch_to_all_rank_traders(self) -> int:
        config_ids = {t.unique_name for t in self.base_traders}
        merged: List[TraderConfig] = []
        seen: Set[str] = set()

        for rank_type in self.ALL_RANK_TYPES:
            for trader in self.fetch_follow_rank_traders(rank_type):
                if trader.unique_name in config_ids or trader.unique_name in seen:
                    continue
                seen.add(trader.unique_name)
                merged.append(trader)

        if not merged:
            return 0

        with self.refresh_lock:
            self.traders = merged
            self._position_cursor = 0
            self.current_rank_type = "__all__"
            self.previous_trades = {t.unique_name: self.previous_trades.get(t.unique_name, []) for t in self.traders}

        with self.state_lock:
            self.latest_positions = {}

        self.refresh_positions()
        return len(self.traders)

    @staticmethod
    def parse_okx_trade(trade: Dict[str, Any]) -> Tuple[str, str, str]:
        side = str(trade.get("side", "")).lower()
        pos_side = str(trade.get("posSide", "")).lower()
        if pos_side == "net":
            if side == "buy":
                return "买入", "🟢", "单向持仓-买入"
            return "卖出", "🔴", "单向持仓-卖出"
        if pos_side == "long":
            if side == "buy":
                return "开多", "🟢", "买入开多仓"
            return "平多", "🟡", "卖出平多仓"
        if side == "sell":
            return "开空", "🔴", "卖出开空仓"
        return "平空", "🟠", "买入平空仓"

    def _trade_id(self, trade: Dict[str, Any]) -> str:
        for key in ["tradeId", "ordId", "billId", "id", "uTime", "cTime"]:
            if trade.get(key):
                return str(trade.get(key))
        return json.dumps(trade, sort_keys=True, ensure_ascii=False)

    def _infer_direction(self, pos: Dict[str, Any]) -> str:
        pos_side = str(pos.get("posSide", "")).lower()
        if pos_side == "short":
            return "空"
        if pos_side == "long":
            return "多"
        # net/空字符串兜底：根据持仓数量正负推断
        try:
            pos_num = float(pos.get("pos", 0) or 0)
            if pos_num < 0:
                return "空"
        except (TypeError, ValueError):
            pass
        return "多"

    def _estimate_liq_price(self, pos: Dict[str, Any], direction: str, mgn_ratio: float) -> str:
        """当接口未返回 liqPx 时，基于保证金率做近似估算。"""
        try:
            mark_px = float(pos.get("markPx", 0) or 0)
            lever = max(float(pos.get("lever", 1) or 1), 1.0)
        except (TypeError, ValueError):
            return "--"

        if mark_px <= 0:
            return "--"

        if mgn_ratio <= 1:
            estimate = mark_px
        else:
            # 近似：保证金率降到 100% 触发爆仓，所需价格变化比例与杠杆反比
            delta_ratio = (mgn_ratio - 1) / lever
            if direction == "空":
                estimate = mark_px * (1 + delta_ratio)
            else:
                estimate = mark_px * (1 - delta_ratio)

        if estimate <= 0:
            return "--"
        return self.format_number(estimate, 8)

    def _position_to_view(self, pos: Dict[str, Any]) -> Dict[str, Any]:
        inst_id = str(pos.get("instId", ""))
        contract_value = float(self.contract_values.get(inst_id, 1))
        pos_size = float(pos.get("pos", 0) or 0)
        coin_amount = abs(pos_size) * contract_value
        upl_ratio = float(pos.get("uplRatio", 0) or 0)
        mgn_ratio = float(pos.get("mgnRatio", 0) or 0)
        margin_value = float(pos.get("margin", 0) or 0)
        direction = self._infer_direction(pos)

        api_liq = pos.get("liqPx")
        liq_px = self.format_number(api_liq, 8) if api_liq not in (None, "", "--") else self._estimate_liq_price(pos, direction, mgn_ratio)

        return {
            "instId": inst_id,
            "symbol": inst_id.replace("-SWAP", "").replace("-", "/").lower(),
            "direction": direction,
            "lever": pos.get("lever", "0"),
            "dirLev": f"{direction}{pos.get('lever', '0')}x",
            "avgPx": self.format_number(pos.get("avgPx", 0), 8),
            "uplRate": f"{upl_ratio * 100:.2f}%",
            "coinAmount": self.format_number(coin_amount, 6),
            "contracts": self.format_number(abs(pos_size), 4),
            "markPx": self.format_number(pos.get("markPx", 0), 8),
            "margin": self.format_number(margin_value, 4),
            "marginValue": margin_value,
            "notionalUsd": self.format_number(pos.get("notionalUsd", 0), 4),
            "upl": self.format_number(pos.get("upl", 0), 4),
            "liqPx": liq_px,
            "mgnRate": f"{mgn_ratio * 100:.2f}%",
            "danger": mgn_ratio < 1,
        }

    @staticmethod
    def _pick_primary_position(all_positions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not all_positions:
            return None
        priority = ["ETH-USDT-SWAP", "BTC-USDT-SWAP", "SOL-USDT-SWAP"]
        by_inst = {p.get("instId"): p for p in all_positions}
        for inst in priority:
            if inst in by_inst:
                return by_inst[inst]
        return all_positions[0]

    def refresh_positions(self, unique_names: Optional[Set[str]] = None):
        traders = self._get_traders_snapshot()
        active_unique_names = {t.unique_name for t in traders}
        full_refresh = unique_names is None
        target = active_unique_names if full_refresh else set(unique_names)

        with self.refresh_lock:
            with self.state_lock:
                # 全量刷新时不继承旧快照，避免残留 config 带单员
                if full_refresh:
                    snapshot: Dict[str, Dict[str, Any]] = {}
                else:
                    snapshot = {
                        k: v for k, v in self.latest_positions.items()
                        if k in active_unique_names
                    }

            for trader in traders:
                if trader.unique_name not in target:
                    continue

                pos_data = self.fetch_okx_positions(trader.unique_name)
                if pos_data is None:
                    snapshot[trader.unique_name] = {
                        "name": trader.name,
                        "platform": trader.platform,
                        "uniqueName": trader.unique_name,
                        "hasPosition": False,
                        "position": None,
                        "positions": [],
                        "rawCount": 0,
                        "error": "拉取失败",
                        "traderUrl": self._trader_url(trader.unique_name),
                    }
                    continue

                all_views = [self._position_to_view(p) for p in pos_data]
                # 第三点需求：根据保证金金额排序（大 -> 小）
                all_views.sort(key=lambda x: x.get("marginValue", 0), reverse=True)
                primary = self._pick_primary_position(all_views)

                snapshot[trader.unique_name] = {
                    "name": trader.name,
                    "platform": trader.platform,
                    "uniqueName": trader.unique_name,
                    "hasPosition": bool(primary),
                    "position": primary,
                    "positions": all_views,
                    "rawCount": len(all_views),
                    "error": "",
                    "traderUrl": self._trader_url(trader.unique_name),
                }

        # 博主级排序：有持仓在前，空仓在后；有持仓时按主仓保证金降序
        sorted_items = sorted(
            ((k, v) for k, v in snapshot.items() if k in active_unique_names),
            key=lambda x: (
                0 if x[1].get("hasPosition") else 1,
                -float(x[1].get("position", {}).get("marginValue", 0) if x[1].get("position") else 0),
                x[1].get("name", ""),
            ),
        )

        with self.state_lock:
            self.latest_positions = dict(sorted_items)
            self.last_refresh_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


    def refresh_positions_round_robin(self):
        batch_size = int(self.config.get("okx", {}).get("position_batch_size", 3))
        if batch_size <= 0:
            return
        traders = self._get_traders_snapshot()
        total = len(traders)
        if total == 0:
            return

        start = self._position_cursor % total
        selected = []
        for i in range(min(batch_size, total)):
            trader = traders[(start + i) % total]
            selected.append(trader.unique_name)
        self._position_cursor = (start + batch_size) % total

        self._log_debug(f"分批刷新持仓: {selected}")
        self.refresh_positions(set(selected))

    def _create_notification(self, trader: TraderConfig, trade: Dict[str, Any]) -> Dict[str, Any]:
        action_text, emoji, _ = self.parse_okx_trade(trade)
        coin = (trade.get("instId", "").split("-")[0] or "UNKNOWN").upper()
        size = float(trade.get("fillSz", trade.get("sz", 0)) or 0)
        avg_price = float(trade.get("fillPx", trade.get("avgPx", 0)) or 0)
        time_short = datetime.now().strftime("%H:%M:%S")

        title = f"{emoji} {trader.name} {action_text} {coin}"
        content = (
            f"## 交易提醒\n\n"
            f"- 博主: **{trader.name}**\n"
            f"- 操作: **{action_text}**\n"
            f"- 币种: `{coin}`\n"
            f"- 数量: `{self.format_number(size, 6)}`\n"
            f"- 成交价: `{self.format_number(avg_price, 8)} USDT`\n"
            f"- 时间: `{datetime.now().strftime('%Y/%m/%d %H:%M:%S')}`"
        )
        return {
            "platform": "okx",
            "title": title,
            "content": content,
            "trader_name": trader.name,
            "unique_name": trader.unique_name,
            "action_text": action_text,
            "coin_symbol": coin,
            "size": size,
            "avg_price": avg_price,
            "time_short": time_short,
            "emoji": emoji,
        }

    def _create_merged_notification(self, notifications: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if len(notifications) < 3:
            return None
        first = notifications[0]
        trader_name = first["trader_name"]
        unique_name = first.get("unique_name", "")
        lines = []
        for item in notifications:
            lines.append(
                f"{item.get('emoji', '📊')} **{item['action_text']}** `{self.format_number(item['size'], 4)} {item['coin_symbol']}` "
                f"@ `{self.format_number(item.get('avg_price', 0), 5)} USDT` - {item.get('time_short', '')}"
            )
        return {
            "platform": "okx",
            "title": f"📊 {trader_name} 批量交易提醒 ({len(notifications)}笔)",
            "content": (
                f"## 📊 {trader_name} - 批量交易提醒\n\n"
                f"### 检测到 {len(notifications)} 笔新交易\n\n"
                + "\n".join(lines)
                + f"\n\n> 🔗 博主ID: `{unique_name}`\n> ⏰ 通知时间: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}"
            ),
            "trader_name": trader_name,
            "unique_name": unique_name,
            "is_merged": True,
            "trade_count": len(notifications),
        }

    def send_notification(self, title: str, content: str) -> bool:
        conf = self.config.get("notification", {}).get("serverchan", {})
        if not conf.get("enabled", False):
            return False
        sendkey = conf.get("sendkey", "")
        if not sendkey or sendkey == "YOUR_SERVERCHAN_SENDKEY_HERE":
            return False
        try:
            self._http_post_json(
                f"https://sctapi.ftqq.com/{sendkey}.send",
                {"title": title, "desp": content, "channel": conf.get("channel", "1")},
            )
            print("✓ Server酱通知发送成功")
            return True
        except Exception as e:
            print(f"❌ 发送Server酱通知失败: {e}")
            return False

    def send_email(self, subject: str, content: str, platform: str = "okx") -> bool:
        email_conf = self.config.get("notification", {}).get("email", {})
        if not email_conf.get("enabled", False):
            return False
        sender = email_conf.get("sender_email", "")
        password = email_conf.get("sender_password", "")
        receiver = email_conf.get("receiver_email", "")
        smtp_server = email_conf.get("smtp_server", "")
        smtp_port = int(email_conf.get("smtp_port", 465))
        use_ssl = bool(email_conf.get("use_ssl", True))
        if not all([sender, password, receiver, smtp_server]):
            return False
        try:
            msg = MIMEMultipart()
            msg["From"] = Header(sender)
            msg["To"] = Header(receiver)
            msg["Subject"] = Header(subject, "utf-8")
            msg.attach(MIMEText(content.replace("\n", "<br>"), "html", "utf-8"))
            smtp = smtplib.SMTP_SSL(smtp_server, smtp_port) if use_ssl else smtplib.SMTP(smtp_server, smtp_port)
            if not use_ssl:
                smtp.starttls()
            smtp.login(sender, password)
            smtp.sendmail(sender, receiver, msg.as_string())
            smtp.quit()
            print("✓ 邮件发送成功")
            return True
        except Exception as e:
            print(f"❌ 发送邮件失败: {e}")
            return False

    # 第四点需求：定时仅拉交易，不每轮拉持仓；仅有变化才刷新持仓
    def check_trades_once(self):
        all_notifications: List[Dict[str, Any]] = []
        changed_traders: Set[str] = set()
        limit = int(self.config.get("okx", {}).get("trades_limit", 8))
        traders = self._get_traders_snapshot()

        for trader in traders:
            result = self.fetch_okx_trades(trader.unique_name, limit=limit)
            if not result or result.get("code") != "0":
                continue

            trades = result.get("data", []) or []
            if trades and isinstance(trades[0], dict) and "tradeList" in trades[0]:
                trades = trades[0].get("tradeList", [])

            current_ids = [self._trade_id(item) for item in trades]
            previous_ids = set(self.previous_trades.get(trader.unique_name, []))
            new_trades = [trade for trade, tid in zip(trades, current_ids) if tid not in previous_ids]

            if new_trades:
                changed_traders.add(trader.unique_name)
                self._log_debug(f"{trader.name} 新交易 {len(new_trades)} 笔")
                for trade in reversed(new_trades):
                    all_notifications.append(self._create_notification(trader, trade))

            self.previous_trades[trader.unique_name] = current_ids

        if all_notifications:
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for notif in all_notifications:
                grouped.setdefault(notif["trader_name"], []).append(notif)

            final_notifications: List[Dict[str, Any]] = []
            for _, trader_notifs in grouped.items():
                merged = self._create_merged_notification(trader_notifs)
                if merged:
                    final_notifications.append(merged)
                else:
                    final_notifications.extend(trader_notifs)

            for notif in final_notifications:
                self.send_notification(notif["title"], notif["content"])
                self.send_email(notif["title"], notif["content"], notif["platform"])
                time.sleep(0.5)

            # 只有变动的博主才刷新持仓
            self.refresh_positions(changed_traders)
        else:
            self._log_debug("本轮无新交易")

        self._save_trades_history()

    def bootstrap_history(self):
        limit = int(self.config.get("okx", {}).get("trades_limit", 8))
        for trader in self._get_traders_snapshot():
            result = self.fetch_okx_trades(trader.unique_name, limit=limit)
            if result and result.get("code") == "0":
                trades = result.get("data", []) or []
                if trades and isinstance(trades[0], dict) and "tradeList" in trades[0]:
                    trades = trades[0].get("tradeList", [])
                self.previous_trades[trader.unique_name] = [self._trade_id(item) for item in trades]
        self._save_trades_history()

    def monitor_loop(self):
        self.running = True
        interval = int(self.config.get("interval_seconds", 20))
        while self.running:
            try:
                self.check_trades_once()
            except Exception as e:
                print(f"❌ 监控循环异常: {e}")
            time.sleep(interval)

    def position_loop(self):
        interval = int(self.config.get("okx", {}).get("position_batch_interval_seconds", 10))
        while self.running:
            try:
                self.refresh_positions_round_robin()
            except Exception as e:
                print(f"❌ 持仓轮询异常: {e}")
            time.sleep(interval)


def create_flask_app(monitor: OKXMonitor) -> Flask:
    app = Flask(__name__, template_folder="templates")

    @app.get("/")
    def index():
        return render_template("dashboard.html")

    @app.get("/api/status")
    def api_status():
        with monitor.state_lock:
            payload = {
                "last_refresh_time": monitor.last_refresh_time,
                "count": len(monitor.latest_positions),
                "items": list(monitor.latest_positions.values()),
                "rank_type": monitor.current_rank_type,
            }
        return jsonify(payload)

    @app.post("/api/rank/switch")
    def api_rank_switch():
        body = request.get_json(silent=True) or {}
        rank_type = str(body.get("type", "")).strip()
        if rank_type == "__config__":
            total = monitor.switch_to_config_traders()
        elif rank_type == "__all__":
            total = monitor.switch_to_all_rank_traders()
        else:
            total = monitor.switch_to_rank_traders(rank_type)
        if total <= 0:
            return jsonify({"ok": False, "message": "未获取到排行带单员，请稍后重试"}), 502
        return jsonify({"ok": True, "count": total, "rank_type": rank_type})

    return app


def main():
    monitor = OKXMonitor("config.json")

    # 启动阶段拉一次全量持仓
    monitor.refresh_positions()

    if not monitor.previous_trades:
        monitor.bootstrap_history()

    threading.Thread(target=monitor.monitor_loop, daemon=True).start()
    threading.Thread(target=monitor.position_loop, daemon=True).start()

    web_conf = monitor.config.get("web", {})
    host = web_conf.get("host", "0.0.0.0")
    port = int(web_conf.get("port", 8080))

    app = create_flask_app(monitor)
    print(f"🚀 Flask Web 已启动: http://{host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
