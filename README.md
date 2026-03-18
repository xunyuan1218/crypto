# BTC / HYPE 波动提醒工具

这是一个轻量 Python 脚本，用于监控 `BTCUSDT` 和 `HYPEUSDT` 的短时波动，并通过 IM 工具发送提醒。

## 功能

- 基于 Binance 公共 API 获取实时价格
- 按滚动窗口计算涨跌幅（例如 5 分钟）
- 超过阈值自动告警
- 支持多种通知渠道：
  - Telegram
  - Slack Incoming Webhook
  - Discord Webhook
  - 通用 Webhook（用于自定义 IM 系统）

## 快速开始

1. 准备 Python 3.10+
2. 复制配置文件并填写通知配置：

```bash
cp config.example.json config.json
```

3. 运行：

```bash
python3 monitor.py --config config.json
```

## 配置说明

- `symbols`: 监控交易对（默认 `BTCUSDT`, `HYPEUSDT`）
- `interval_sec`: 轮询间隔（秒）
- `lookback_sec`: 波动计算窗口（秒）
- `cooldown_sec`: 告警冷却时间（秒）
- `thresholds`: 各交易对触发阈值（百分比）

### Telegram

在 `notifications.telegram` 中配置：

- `enabled: true`
- `bot_token`
- `chat_id`

### Slack / Discord

填入对应平台的 Webhook URL 并启用 `enabled`。

### 通用 Webhook

可在 `payload_template` 中定义你自己的 JSON 模板，`{message}` 会被替换为实际提醒内容。

## 示例提醒

```text
⚠️ 波动提醒 BTCUSDT
方向: 下跌
当前价格: 103456.120000
5分钟变动: -1.28%
阈值: 0.80%
时间: 2026-03-18 10:00:00 UTC
```

## 注意

- 请合理设置阈值和冷却时间，避免消息过多。
- 生产环境建议配合进程管理器运行（如 systemd / supervisor）。
