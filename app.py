import json
import os
import threading
import time
import smtplib
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError



@dataclass
class TraderConfig:
    name: str
    platform: str
    unique_name: str


class OKXMonitor:
    POSITION_URL = "https://www.okx.com/priapi/v5/ecotrade/public/community/user/position-current"
    TRADES_URL = "https://www.okx.com/priapi/v5/ecotrade/public/community/user/trade-records"

    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self._load_config(config_path)
        self.debug = self.config.get("debug", False)
        self.state_lock = threading.Lock()
        self.running = False

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
        self.last_refresh_time = ""

        self._load_trades_history()

    def _log_debug(self, message: str):
        if self.debug:
            print(f"[DEBUG] {message}")

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"未找到配置文件: {config_path}，请先复制 config.example.json 为 config.json")
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_traders(self) -> List[TraderConfig]:
        traders = []
        for item in self.config.get("traders", []):
            if item.get("platform", "").lower() != "okx":
                continue
            traders.append(
                TraderConfig(
                    name=item["name"],
                    platform="okx",
                    unique_name=item["uniqueName"],
                )
            )
        if not traders:
            raise ValueError("config.json 中未配置 okx 博主")
        return traders

    def _load_trades_history(self):
        try:
            if os.path.exists(self.trades_history_file):
                with open(self.trades_history_file, 'r', encoding='utf-8') as f:
                    history_data = json.load(f)
                    self.previous_trades = history_data.get('trades', {})
                    last_update = history_data.get('last_update', '')
                    if self.previous_trades:
                        print(f"✓ 已加载交易历史数据 (上次更新: {last_update})")
                        print(f"  包含 {len(self.previous_trades)} 个账户的历史记录")
            else:
                print("ℹ️  未找到交易历史数据文件，将创建新文件")
        except json.JSONDecodeError as e:
            print(f"⚠️  交易历史数据文件格式错误: {e}，将重新开始")
            self.previous_trades = {}
        except Exception as e:
            print(f"⚠️  加载交易历史数据失败: {e}，将重新开始")
            self.previous_trades = {}

    def _save_trades_history(self):
        try:
            history_data = {
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'trades': self.previous_trades,
                'version': '3.0'
            }
            with open(self.trades_history_file, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, ensure_ascii=False, indent=2)
            self._log_debug(f"交易历史数据已保存: {self.trades_history_file}")
        except Exception as e:
            print(f"❌ 保存交易历史数据失败: {e}")

    @staticmethod
    def format_number(num: Any, max_decimals: int = 4) -> str:
        try:
            v = float(num)
        except (TypeError, ValueError):
            return "0"
        if v == 0:
            return "0"
        abs_v = abs(v)
        if abs_v >= 1000:
            decimals = 2
        elif abs_v >= 1:
            decimals = min(max_decimals, 4)
        else:
            decimals = min(max_decimals + 2, 8)
        text = f"{v:.{decimals}f}"
        return text.rstrip("0").rstrip(".") if "." in text else text


    def _http_get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if params:
            query = urlencode(params)
            connector = '&' if '?' in url else '?'
            url = f"{url}{connector}{query}"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _http_post_json(self, url: str, data: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(data).encode("utf-8")
        req = Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}, method="POST")
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def fetch_okx_positions(self, unique_name: str) -> Optional[List[Dict[str, Any]]]:
        params = {"uniqueName": unique_name}
        try:
            payload = self._http_get_json(self.POSITION_URL, params=params)
            if payload.get("code") != "0":
                return None
            data = payload.get("data", [])
            if not data:
                return []
            return data[0].get("posData", [])
        except Exception as e:
            print(f"❌ 获取持仓失败 {unique_name}: {e}")
            return None

    def fetch_okx_trades(self, unique_name: str, limit: int = 8) -> Optional[Dict[str, Any]]:
        url = f"{self.TRADES_URL}?uniqueName={unique_name}&limit={limit}"
        try:
            return self._http_get_json(url)
        except Exception as e:
            print(f"❌ 获取交易记录失败 {unique_name}: {e}")
            return None

    def parse_okx_trade(self, trade: Dict[str, Any]) -> Tuple[str, str, str]:
        side = str(trade.get('side', '')).lower()
        pos_side = str(trade.get('posSide', '')).lower()
        if pos_side == 'net':
            if side == 'buy':
                return '买入', '🟢', '单向持仓-买入'
            return '卖出', '🔴', '单向持仓-卖出'
        if pos_side == 'long':
            if side == 'buy':
                return '开多', '🟢', '买入开多仓'
            return '平多', '🟡', '卖出平多仓'
        if side == 'sell':
            return '开空', '🔴', '卖出开空仓'
        return '平空', '🟠', '买入平空仓'

    def _trade_id(self, trade: Dict[str, Any]) -> str:
        for k in ["tradeId", "ordId", "billId", "id", "uTime", "cTime"]:
            if trade.get(k):
                return str(trade.get(k))
        return json.dumps(trade, sort_keys=True, ensure_ascii=False)

    def _position_to_view(self, pos: Dict[str, Any]) -> Dict[str, Any]:
        inst_id = pos.get("instId", "")
        contract_value = float(self.contract_values.get(inst_id, 1))
        pos_size = float(pos.get("pos", 0) or 0)
        coin_amount = pos_size * contract_value

        upl_ratio = float(pos.get("uplRatio", 0) or 0)
        mgn_ratio = float(pos.get("mgnRatio", 0) or 0)

        return {
            "instId": inst_id,
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

    def _pick_primary_position(self, pos_data: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not pos_data:
            return None
        priority = ["ETH-USDT-SWAP", "BTC-USDT-SWAP", "SOL-USDT-SWAP"]
        indexed = {p.get("instId"): p for p in pos_data}
        for inst in priority:
            if inst in indexed:
                return indexed[inst]
        return pos_data[0]

    def refresh_positions(self):
        snapshot = {}
        for trader in self.traders:
            pos_data = self.fetch_okx_positions(trader.unique_name)
            if pos_data is None:
                continue
            primary = self._pick_primary_position(pos_data)
            snapshot[trader.unique_name] = {
                "name": trader.name,
                "platform": trader.platform,
                "uniqueName": trader.unique_name,
                "hasPosition": bool(primary),
                "position": self._position_to_view(primary) if primary else None,
                "rawCount": len(pos_data),
            }

        sorted_items = sorted(
            snapshot.items(),
            key=lambda x: (0 if x[1]["hasPosition"] else 1, x[1]["name"])
        )
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
        trader_name = first['trader_name']
        unique_name = first.get('unique_name', '')
        lines = []
        for n in notifications:
            lines.append(
                f"{n.get('emoji', '📊')} **{n['action_text']}** `{self.format_number(n['size'], 4)} {n['coin_symbol']}` "
                f"@ `{self.format_number(n.get('avg_price', 0), 5)} USDT` - {n.get('time_short', '')}"
            )
        summary_text = "\n".join(lines)
        title = f"📊 {trader_name} 批量交易提醒 ({len(notifications)}笔)"
        content = f"""## 📊 {trader_name} - 批量交易提醒

### 检测到 {len(notifications)} 笔新交易

{summary_text}

> ⏰ 通知时间: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}"""
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
        conf = self.config.get('notification', {}).get('serverchan', {})
        if not conf.get('enabled', False):
            return False
        sendkey = conf.get('sendkey', '')
        if not sendkey or sendkey == 'YOUR_SERVERCHAN_SENDKEY_HERE':
            return False
        channel = conf.get('channel', '1')
        url = f"https://sctapi.ftqq.com/{sendkey}.send"
        data = {'title': title, 'desp': content, 'channel': channel}
        try:
            self._http_post_json(url, data)
            print('✓ Server酱通知发送成功')
            return True
        except Exception as e:
            print(f'❌ 发送Server酱通知失败: {e}')
            return False

    def send_email(self, subject: str, content: str, platform: str = 'okx') -> bool:
        email_config = self.config.get('notification', {}).get('email', {})
        if not email_config.get('enabled', False):
            return False
        sender_email = email_config.get('sender_email', '')
        sender_password = email_config.get('sender_password', '')
        receiver_email = email_config.get('receiver_email', '')
        smtp_server = email_config.get('smtp_server', '')
        smtp_port = email_config.get('smtp_port', 465)
        use_ssl = email_config.get('use_ssl', True)
        if not all([sender_email, sender_password, receiver_email, smtp_server]):
            return False
        try:
            msg = MIMEMultipart()
            msg['From'] = Header(sender_email)
            msg['To'] = Header(receiver_email)
            msg['Subject'] = Header(subject, 'utf-8')
            msg.attach(MIMEText(self._convert_markdown_to_html(content, platform), 'html', 'utf-8'))
            if use_ssl:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
            server.quit()
            print('✓ 邮件发送成功')
            return True
        except Exception as e:
            print(f'❌ 发送邮件失败: {e}')
            return False

    def _convert_markdown_to_html(self, content: str, platform: str = 'okx') -> str:
        import html
        text = html.escape(content)
        text = text.replace('## ', '<h2 style="color:#1f2937;margin:16px 0 10px;">')
        text = text.replace('### ', '<h3 style="color:#374151;margin:12px 0 8px;">')
        text = text.replace('\n', '<br>')

        gradient = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' if platform == 'okx' else 'linear-gradient(135deg, #f0b90b 0%, #f8d33a 100%)'
        title = 'OKX交易提醒' if platform == 'okx' else '币安交易提醒'
        return f"""
        <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;line-height:1.6;color:#1f2937;max-width:800px;margin:0 auto;padding:20px;background:#fff;">
          <div style="background:{gradient};padding:16px 20px;border-radius:10px 10px 0 0;color:#fff;"><h1 style="margin:0;font-size:22px;">{title}</h1></div>
          <div style="background:#f9fafb;padding:20px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 10px 10px;">{text}</div>
          <div style="text-align:center;margin-top:14px;color:#9ca3af;font-size:12px;">此邮件由监控系统自动发送</div>
        </body></html>
        """.strip()

    def check_trades_once(self):
        all_notifications: List[Dict[str, Any]] = []
        for trader in self.traders:
            result = self.fetch_okx_trades(trader.unique_name, limit=self.config.get("okx", {}).get("trades_limit", 8))
            if not result or result.get("code") != "0":
                continue
            trades = result.get("data", []) or []
            if trades and isinstance(trades[0], dict) and "tradeList" in trades[0]:
                trades = trades[0].get("tradeList", [])

            ids = [self._trade_id(t) for t in trades]
            old_ids = set(self.previous_trades.get(trader.unique_name, []))
            new_trades = [t for t, tid in zip(trades, ids) if tid not in old_ids]
            if new_trades:
                self._log_debug(f"{trader.name} 新交易 {len(new_trades)} 笔")
                for t in reversed(new_trades):
                    all_notifications.append(self._create_notification(trader, t))
            self.previous_trades[trader.unique_name] = ids

        if all_notifications:
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for n in all_notifications:
                grouped.setdefault(n["trader_name"], []).append(n)
            final_notifications: List[Dict[str, Any]] = []
            for _, notifs in grouped.items():
                merged = self._create_merged_notification(notifs)
                if merged:
                    final_notifications.append(merged)
                else:
                    final_notifications.extend(notifs)

            for notif in final_notifications:
                self.send_notification(notif['title'], notif['content'])
                self.send_email(notif['title'], notif['content'], notif['platform'])
                time.sleep(0.5)
        else:
            self._log_debug("本轮无新交易")

        self._save_trades_history()

    def bootstrap_history(self):
        for trader in self.traders:
            result = self.fetch_okx_trades(trader.unique_name, limit=self.config.get("okx", {}).get("trades_limit", 8))
            if result and result.get("code") == "0":
                trades = result.get("data", []) or []
                if trades and isinstance(trades[0], dict) and "tradeList" in trades[0]:
                    trades = trades[0].get("tradeList", [])
                self.previous_trades[trader.unique_name] = [self._trade_id(t) for t in trades]
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


HTML_PAGE = """<!doctype html>
<html lang=\"zh-CN\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>OKX 带单监控</title>
<style>
body{font-family:Arial,sans-serif;background:#0b1220;color:#e5e7eb;margin:0;padding:16px}
h1{font-size:22px} .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.card{background:#131c2f;border:1px solid #233252;border-radius:14px;padding:14px}
.muted{color:#94a3b8;font-size:12px}.danger{color:#f87171}.ok{color:#4ade80}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;background:#1f2a44;margin-left:6px;font-size:12px}
.kv{display:flex;justify-content:space-between;padding:3px 0;font-size:14px}
</style></head><body>
<h1>OKX 带单员持仓监控</h1><div class=\"muted\" id=\"meta\">加载中...</div><div class=\"grid\" id=\"cards\"></div>
<script>
async function load(){
 const res=await fetch('/api/status'); const data=await res.json();
 document.getElementById('meta').textContent=`更新时间: ${data.last_refresh_time} ｜ 账户: ${data.count}`;
 const cards=document.getElementById('cards'); cards.innerHTML='';
 data.items.forEach(it=>{
  const p=it.position;
  const div=document.createElement('div'); div.className='card';
  if(!it.hasPosition){
   div.innerHTML=`<h3>${it.name}<span class='badge'>空仓</span></h3><div class='muted'>当前无持仓</div>`;
  }else{
   div.innerHTML=`<h3>${it.name}<span class='badge'>${p.symbol}</span></h3>
   <div class='kv'><span>方向</span><span>${p.direction}</span></div>
   <div class='kv'><span>杠杆</span><span>${p.lever}x</span></div>
   <div class='kv'><span>开仓均价</span><span>${p.avgPx}</span></div>
   <div class='kv'><span>收益率</span><span>${p.uplRate}</span></div>
   <div class='kv'><span>持仓量</span><span>${p.coinAmount}</span></div>
   <div class='kv'><span>保证金</span><span>${p.margin}</span></div>
   <div class='kv'><span>持仓价值</span><span>${p.notionalUsd}</span></div>
   <div class='kv'><span>收益</span><span>${p.upl}</span></div>
   <div class='kv'><span>保证金率</span><span class='${p.danger?"danger":"ok"}'>${p.mgnRate}</span></div>
   <div class='kv'><span>预估爆仓价</span><span>${p.liqPx}</span></div>`;
  }
  cards.appendChild(div);
 });
}
load(); setInterval(load,5000);
</script></body></html>"""


def make_handler(monitor: OKXMonitor):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(HTML_PAGE.encode("utf-8"))
                return
            if path == "/api/status":
                with monitor.state_lock:
                    items = list(deepcopy(monitor.latest_positions).values())
                    payload = {
                        "last_refresh_time": monitor.last_refresh_time,
                        "count": len(items),
                        "items": items,
                    }
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
                return

            self.send_response(404)
            self.end_headers()

        def log_message(self, format, *args):
            return

    return Handler


def main():
    monitor = OKXMonitor("config.json")
    monitor.refresh_positions()
    if not monitor.previous_trades:
        monitor.bootstrap_history()

    t = threading.Thread(target=monitor.monitor_loop, daemon=True)
    t.start()

    web_conf = monitor.config.get("web", {})
    host = web_conf.get("host", "0.0.0.0")
    port = int(web_conf.get("port", 8080))

    server = ThreadingHTTPServer((host, port), make_handler(monitor))
    print(f"🚀 Web 已启动: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop()
        server.server_close()


if __name__ == "__main__":
    main()
