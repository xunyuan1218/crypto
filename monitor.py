#!/usr/bin/env python3
"""BTC / HYPE volatility monitor with IM notifications.

Features:
- Track BTCUSDT and HYPEUSDT spot prices from Binance public API.
- Compute % change inside a rolling lookback window.
- Alert when absolute change exceeds configured thresholds.
- Support Telegram, Slack, Discord, and generic webhook notifications.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Deque
from urllib import error, parse, request


BINANCE_PRICE_API = "https://api.binance.com/api/v3/ticker/price"


@dataclass
class SymbolState:
    prices: Deque[tuple[float, float]]
    last_alert_at: float = 0.0


class PriceMonitor:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.symbols: list[str] = config.get("symbols", ["BTCUSDT", "HYPEUSDT"])
        self.interval_sec: int = int(config.get("interval_sec", 30))
        self.lookback_sec: int = int(config.get("lookback_sec", 300))
        self.cooldown_sec: int = int(config.get("cooldown_sec", 300))
        self.default_threshold_pct: float = float(config.get("default_threshold_pct", 1.0))
        self.thresholds: dict[str, float] = {
            k.upper(): float(v)
            for k, v in config.get("thresholds", {"BTCUSDT": 0.8, "HYPEUSDT": 2.0}).items()
        }
        self.states: dict[str, SymbolState] = {
            symbol: SymbolState(prices=deque()) for symbol in self.symbols
        }

    def run(self) -> None:
        print(f"Starting monitor for symbols: {', '.join(self.symbols)}")
        print(
            f"interval={self.interval_sec}s lookback={self.lookback_sec}s cooldown={self.cooldown_sec}s"
        )
        while True:
            now = time.time()
            for symbol in self.symbols:
                try:
                    price = fetch_price(symbol)
                    self._record_price(symbol, now, price)
                    self._check_and_notify(symbol, now)
                except Exception as exc:  # keep monitor alive
                    print(f"[{iso_now()}] ERROR {symbol}: {exc}")
            time.sleep(self.interval_sec)

    def _record_price(self, symbol: str, ts: float, price: float) -> None:
        state = self.states[symbol]
        state.prices.append((ts, price))

        while state.prices and ts - state.prices[0][0] > self.lookback_sec:
            state.prices.popleft()

        print(f"[{iso_now()}] {symbol} = {price:.6f}")

    def _check_and_notify(self, symbol: str, now_ts: float) -> None:
        state = self.states[symbol]
        if len(state.prices) < 2:
            return

        old_ts, old_price = state.prices[0]
        _, current_price = state.prices[-1]

        if old_price <= 0:
            return

        move_pct = (current_price - old_price) / old_price * 100
        threshold_pct = self.thresholds.get(symbol.upper(), self.default_threshold_pct)

        if abs(move_pct) < threshold_pct:
            return

        if now_ts - state.last_alert_at < self.cooldown_sec:
            return

        direction = "上涨" if move_pct > 0 else "下跌"
        message = (
            f"⚠️ 波动提醒 {symbol}\n"
            f"方向: {direction}\n"
            f"当前价格: {current_price:.6f}\n"
            f"{int(self.lookback_sec/60)}分钟变动: {move_pct:+.2f}%\n"
            f"阈值: {threshold_pct:.2f}%\n"
            f"时间: {iso_now()}"
        )
        send_notifications(message, self.config.get("notifications", {}))
        state.last_alert_at = now_ts
        print(f"[{iso_now()}] ALERT sent for {symbol}: {move_pct:+.2f}%")


def fetch_price(symbol: str) -> float:
    query = parse.urlencode({"symbol": symbol.upper()})
    url = f"{BINANCE_PRICE_API}?{query}"
    req = request.Request(url, headers={"User-Agent": "vol-monitor/1.0"})
    with request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "price" not in data:
        raise RuntimeError(f"Invalid API response for {symbol}: {data}")
    return float(data["price"])


def send_notifications(message: str, config: dict[str, Any]) -> None:
    # Telegram
    telegram = config.get("telegram", {})
    if telegram.get("enabled"):
        send_telegram(
            bot_token=telegram.get("bot_token", ""),
            chat_id=telegram.get("chat_id", ""),
            text=message,
        )

    # Slack Incoming Webhook
    slack = config.get("slack", {})
    if slack.get("enabled"):
        post_json(slack.get("webhook_url", ""), {"text": message})

    # Discord Webhook
    discord = config.get("discord", {})
    if discord.get("enabled"):
        post_json(discord.get("webhook_url", ""), {"content": message})

    # Generic webhook endpoint
    generic = config.get("generic_webhook", {})
    if generic.get("enabled"):
        payload = generic.get("payload_template", {"text": "{message}"})
        payload = _format_template(payload, message)
        post_json(generic.get("url", ""), payload)


def _format_template(obj: Any, message: str) -> Any:
    if isinstance(obj, dict):
        return {k: _format_template(v, message) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_format_template(v, message) for v in obj]
    if isinstance(obj, str):
        return obj.replace("{message}", message)
    return obj


def send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    if not bot_token or not chat_id:
        raise ValueError("Telegram enabled but bot_token/chat_id missing")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    post_json(url, {"chat_id": chat_id, "text": text})


def post_json(url: str, payload: dict[str, Any]) -> None:
    if not url:
        raise ValueError("Missing webhook URL")

    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        method="POST",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "vol-monitor/1.0"},
    )
    try:
        with request.urlopen(req, timeout=10) as resp:
            status = getattr(resp, "status", 200)
            if status >= 300:
                raise RuntimeError(f"Webhook returned status {status}")
    except error.HTTPError as exc:
        raise RuntimeError(f"Webhook HTTP error {exc.code}") from exc


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def load_config(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor BTC/HYPE volatility and send IM notifications"
    )
    parser.add_argument(
        "--config", default="config.example.json", help="Path to JSON config file"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    monitor = PriceMonitor(config)
    monitor.run()


if __name__ == "__main__":
    main()
