import json
import os
import smtplib
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Flask, jsonify, render_template_string


@dataclass
class TraderConfig:
    name: str
    platform: str
    unique_name: str


class OKXMonitor:
    POSITION_URL = "https://www.okx.com/priapi/v5/ecotrade/public/community/user/position-current"
    TRADES_URL = "https://www.okx.com/priapi/v5/ecotrade/public/community/user/trade-records"

    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self.debug = bool(self.config.get("debug", False))
        self.state_lock = threading.Lock()
        self.running = False
        self.last_refresh_time = ""

        self.contract_values = self.config.get("okx", {}).get("contract_values", {
            "ETH-USDT-SWAP": 0.1,
            "BTC-USDT-SWAP": 0.01,
            "SOL-USDT-SWAP": 1,
        })

        self.traders = self._load_traders()
        data_dir = Path(self.config.get("data_dir", "data"))
        data_dir.mkdir(parents=True, exist_ok=True)

        self.trades_history_file = str(data_dir / "trades_history.json")
        self.previous_trades: Dict[str, List[str]] = {}
        self.latest_positions: Dict[str, Dict[str, Any]] = {}

        self._load_trades_history()

    @property
    def http_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
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
        except json.JSONDecodeError as e:
            print(f"⚠️  交易历史数据文件格式错误: {e}，将重新开始")
            self.previous_trades = {}
        except Exception as e:
            print(f"⚠️  加载交易历史数据失败: {e}，将重新开始")
            self.previous_trades = {}

    def _save_trades_history(self):
        try:
            history_data = {
                "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "trades": self.previous_trades,
                "version": "3.1",
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

    def fetch_okx_positions(self, unique_name: str) -> Optional[List[Dict[str, Any]]]:
        try:
            payload = self._http_get_json(self.POSITION_URL, params={"uniqueName": unique_name})
            if payload.get("code") != "0":
                return None
            data = payload.get("data", [])
            return data[0].get("posData", []) if data else []
        except Exception as e:
            print(f"❌ 获取持仓失败 {unique_name}: {e}")
            return None

    def fetch_okx_trades(self, unique_name: str, limit: int = 8) -> Optional[Dict[str, Any]]:
        try:
            url = f"{self.TRADES_URL}?uniqueName={unique_name}&limit={limit}"
            return self._http_get_json(url)
        except Exception as e:
            print(f"❌ 获取交易记录失败 {unique_name}: {e}")
            return None

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

    def _position_to_view(self, pos: Dict[str, Any]) -> Dict[str, Any]:
        inst_id = str(pos.get("instId", ""))
        contract_value = float(self.contract_values.get(inst_id, 1))
        pos_size = float(pos.get("pos", 0) or 0)
        coin_amount = pos_size * contract_value

        upl_ratio = float(pos.get("uplRatio", 0) or 0)
        mgn_ratio = float(pos.get("mgnRatio", 0) or 0)

        return {
            "symbol": inst_id.replace("-SWAP", "").replace("-", "/").lower(),
            "direction": "空" if pos.get("posSide") == "short" else "多",
            "lever": pos.get("lever", "0"),
            "avgPx": self.format_number(pos.get("avgPx", 0), 8),
            "uplRate": f"{upl_ratio * 100:.2f}%",
            "coinAmount": self.format_number(coin_amount, 6),
            "margin": self.format_number(pos.get("margin", 0), 4),
            "notionalUsd": self.format_number(pos.get("notionalUsd", 0), 4),
            "upl": self.format_number(pos.get("upl", 0), 4),
            "liqPx": self.format_number(pos.get("liqPx") or 0, 8) if pos.get("liqPx") else "--",
            "mgnRate": f"{mgn_ratio * 100:.2f}%",
            "danger": mgn_ratio < 1,
        }

    @staticmethod
    def _pick_primary_position(pos_data: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not pos_data:
            return None
        priority = ["ETH-USDT-SWAP", "BTC-USDT-SWAP", "SOL-USDT-SWAP"]
        index = {p.get("instId"): p for p in pos_data}
        for inst in priority:
            if inst in index:
                return index[inst]
        return pos_data[0]

    def refresh_positions(self):
        snapshot: Dict[str, Dict[str, Any]] = {}
        for trader in self.traders:
            pos_data = self.fetch_okx_positions(trader.unique_name)
            if pos_data is None:
                snapshot[trader.unique_name] = {
                    "name": trader.name,
                    "platform": trader.platform,
                    "uniqueName": trader.unique_name,
                    "hasPosition": False,
                    "position": None,
                    "rawCount": 0,
                    "error": "拉取失败",
                }
                continue

            primary = self._pick_primary_position(pos_data)
            snapshot[trader.unique_name] = {
                "name": trader.name,
                "platform": trader.platform,
                "uniqueName": trader.unique_name,
                "hasPosition": bool(primary),
                "position": self._position_to_view(primary) if primary else None,
                "rawCount": len(pos_data),
                "error": "",
            }

        sorted_items = sorted(snapshot.items(), key=lambda x: (0 if x[1]["hasPosition"] else 1, x[1]["name"]))
        with self.state_lock:
            self.latest_positions = dict(sorted_items)
            self.last_refresh_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

        summary = []
        for item in notifications:
            summary.append(
                f"{item.get('emoji', '📊')} **{item['action_text']}** `{self.format_number(item['size'], 4)} {item['coin_symbol']}` "
                f"@ `{self.format_number(item.get('avg_price', 0), 5)} USDT` - {item.get('time_short', '')}"
            )

        title = f"📊 {trader_name} 批量交易提醒 ({len(notifications)}笔)"
        content = (
            f"## 📊 {trader_name} - 批量交易提醒\n\n"
            f"### 检测到 {len(notifications)} 笔新交易\n\n"
            + "\n".join(summary)
            + f"\n\n> 🔗 博主ID: `{unique_name}`\n> ⏰ 通知时间: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}"
        )

        return {
            "platform": "okx",
            "title": title,
            "content": content,
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

        payload = {"title": title, "desp": content, "channel": conf.get("channel", "1")}
        try:
            self._http_post_json(f"https://sctapi.ftqq.com/{sendkey}.send", payload)
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
        server_host = email_conf.get("smtp_server", "")
        server_port = int(email_conf.get("smtp_port", 465))
        use_ssl = bool(email_conf.get("use_ssl", True))

        if not all([sender, password, receiver, server_host]):
            return False

        try:
            msg = MIMEMultipart()
            msg["From"] = Header(sender)
            msg["To"] = Header(receiver)
            msg["Subject"] = Header(subject, "utf-8")
            msg.attach(MIMEText(self._convert_markdown_to_html(content, platform), "html", "utf-8"))

            smtp = smtplib.SMTP_SSL(server_host, server_port) if use_ssl else smtplib.SMTP(server_host, server_port)
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

    @staticmethod
    def _convert_markdown_to_html(content: str, platform: str = "okx") -> str:
        import html

        lines = html.escape(content).split("\n")
        blocks = []
        for line in lines:
            if line.startswith("## "):
                blocks.append(f'<h2 style="margin:14px 0 8px;">{line[3:]}</h2>')
            elif line.startswith("### "):
                blocks.append(f'<h3 style="margin:10px 0 8px;">{line[4:]}</h3>')
            elif line.startswith("> "):
                blocks.append(f'<blockquote style="border-left:4px solid #3b82f6;padding-left:10px;color:#6b7280;">{line[2:]}</blockquote>')
            elif line.startswith("- "):
                blocks.append(f"• {line[2:]}<br>")
            elif line.strip() == "":
                blocks.append("<br>")
            else:
                blocks.append(line + "<br>")

        gradient = "linear-gradient(135deg,#667eea 0%,#764ba2 100%)" if platform == "okx" else "linear-gradient(135deg,#f0b90b 0%,#f8d33a 100%)"
        title = "OKX交易提醒" if platform == "okx" else "交易提醒"

        return (
            "<html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'></head>"
            "<body style='font-family:Arial,sans-serif;max-width:760px;margin:0 auto;padding:20px;background:#fff;color:#1f2937;'>"
            f"<div style='background:{gradient};padding:16px;border-radius:10px 10px 0 0;color:#fff;'><h1 style='margin:0;font-size:22px'>{title}</h1></div>"
            "<div style='background:#f9fafb;border:1px solid #e5e7eb;border-top:none;padding:18px;border-radius:0 0 10px 10px;'>"
            + "\n".join(blocks)
            + "</div><div style='text-align:center;color:#9ca3af;font-size:12px;margin-top:12px;'>此邮件由监控系统自动发送</div></body></html>"
        )

    def check_trades_once(self):
        all_notifications: List[Dict[str, Any]] = []
        limit = int(self.config.get("okx", {}).get("trades_limit", 8))
        for trader in self.traders:
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

            # 有新交易后立即刷新页面状态
            self.refresh_positions()
        else:
            self._log_debug("本轮无新交易")

        self._save_trades_history()

    def bootstrap_history(self):
        limit = int(self.config.get("okx", {}).get("trades_limit", 8))
        for trader in self.traders:
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
                self.refresh_positions()
                self.check_trades_once()
            except Exception as e:
                print(f"❌ 监控循环异常: {e}")
            time.sleep(interval)

    def stop(self):
        self.running = False


DASHBOARD_TEMPLATE = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>OKX 带单监控</title>
  <style>
    :root{--bg:#0b1020;--card:#151c32;--text:#e6ecff;--muted:#9aa9d1;--line:#2b3455;--green:#4ade80;--red:#f87171;--amber:#fbbf24;--primary:#60a5fa}
    *{box-sizing:border-box}
    body{margin:0;font-family:Inter,Segoe UI,Roboto,Arial,sans-serif;background:radial-gradient(1200px 500px at 30% -10%, #1e2d58 0%, var(--bg) 50%);color:var(--text)}
    .wrap{max-width:1100px;margin:0 auto;padding:24px 16px 32px}
    .header{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:16px}
    .title{font-size:24px;font-weight:700;letter-spacing:.2px}
    .meta{font-size:13px;color:var(--muted)}
    .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
    .card{background:linear-gradient(180deg,#1a2340 0%, var(--card) 100%);border:1px solid var(--line);border-radius:16px;padding:14px 14px 10px;box-shadow:0 10px 22px rgba(0,0,0,.2)}
    .card h3{margin:0 0 10px;font-size:17px;display:flex;align-items:center;gap:8px}
    .badge{font-size:11px;padding:3px 8px;border-radius:999px;border:1px solid #3f4a73;background:#212a47;color:#bbcaf3}
    .kv{display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px dashed rgba(154,169,209,.18);font-size:13px}
    .kv:last-child{border-bottom:none}
    .muted{color:var(--muted)}
    .good{color:var(--green);font-weight:600}
    .bad{color:var(--red);font-weight:600}
    .warn{color:var(--amber);font-weight:600}
    .err{margin-top:8px;color:#ffb4b4;font-size:12px}
    .empty{padding:20px 10px;color:var(--muted);text-align:center;border:1px dashed #3a4571;border-radius:12px}
    @media(max-width:640px){.wrap{padding:14px 10px 24px}.title{font-size:20px}.card{padding:12px}.kv{font-size:12px}}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="header">
      <div class="title">OKX 带单员实时监控</div>
      <div class="meta" id="meta">加载中...</div>
    </div>
    <div class="grid" id="cards"></div>
  </div>

<script>
function valClass(v){
  if(typeof v !== 'string') return '';
  if(v.startsWith('-')) return 'bad';
  return 'good';
}
async function render(){
  const res = await fetch('/api/status');
  const data = await res.json();
  const cards = document.getElementById('cards');
  cards.innerHTML = '';
  document.getElementById('meta').textContent = `更新时间: ${data.last_refresh_time || '--'} ｜ 账户: ${data.count}`;

  if(!data.items.length){
    cards.innerHTML = "<div class='empty'>暂无数据</div>";
    return;
  }

  data.items.forEach(it=>{
    const c = document.createElement('div');
    c.className='card';
    if(!it.hasPosition){
      c.innerHTML = `<h3>${it.name}<span class='badge'>空仓</span></h3><div class='muted'>当前无持仓</div>${it.error?`<div class='err'>${it.error}</div>`:''}`;
    }else{
      const p = it.position;
      c.innerHTML = `
        <h3>${it.name}<span class='badge'>${p.symbol}</span></h3>
        <div class='kv'><span class='muted'>方向</span><span>${p.direction}</span></div>
        <div class='kv'><span class='muted'>杠杆</span><span>${p.lever}x</span></div>
        <div class='kv'><span class='muted'>开仓均价</span><span>${p.avgPx}</span></div>
        <div class='kv'><span class='muted'>收益率</span><span class='${valClass(p.uplRate)}'>${p.uplRate}</span></div>
        <div class='kv'><span class='muted'>持仓量</span><span>${p.coinAmount}</span></div>
        <div class='kv'><span class='muted'>保证金</span><span>${p.margin}</span></div>
        <div class='kv'><span class='muted'>持仓价值</span><span>${p.notionalUsd}</span></div>
        <div class='kv'><span class='muted'>收益</span><span class='${valClass(p.upl)}'>${p.upl}</span></div>
        <div class='kv'><span class='muted'>保证金率</span><span class='${p.danger ? "warn" : "good"}'>${p.mgnRate}</span></div>
        <div class='kv'><span class='muted'>预估爆仓价</span><span>${p.liqPx}</span></div>
        ${it.error?`<div class='err'>${it.error}</div>`:''}`;
    }
    cards.appendChild(c);
  });
}
render();
setInterval(render, 5000);
</script>
</body>
</html>
"""


def create_flask_app(monitor: OKXMonitor) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template_string(DASHBOARD_TEMPLATE)

    @app.get("/api/status")
    def api_status():
        with monitor.state_lock:
            items = list(monitor.latest_positions.values())
            payload = {
                "last_refresh_time": monitor.last_refresh_time,
                "count": len(items),
                "items": items,
            }
        return jsonify(payload)

    return app


def main():
    monitor = OKXMonitor("config.json")
    monitor.refresh_positions()
    if not monitor.previous_trades:
        monitor.bootstrap_history()

    monitor_thread = threading.Thread(target=monitor.monitor_loop, daemon=True)
    monitor_thread.start()

    web_conf = monitor.config.get("web", {})
    host = web_conf.get("host", "0.0.0.0")
    port = int(web_conf.get("port", 8080))

    app = create_flask_app(monitor)
    print(f"🚀 Flask Web 已启动: http://{host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
