# 🎯 Polymarket / Kalshi Intel Bot

A focused Telegram bot for prediction market bettors — tracks the best bets, detects insider sharp money, and finds arbitrage opportunities between **Polymarket** and **Kalshi**.

---

## ✨ Features

### 🔀 Arbitrage Scanner (`/arb`)
| Type | Description |
|---|---|
| **Cross-Platform** | Same event priced differently on Poly vs Kalshi — buy YES on one, NO on the other |
| **Sum Deviation** | YES + NO ≠ 1.0 on a single platform — buy both sides for guaranteed profit |
| **Spread / Market Making** | Wide bid/ask spreads on Kalshi — post limit orders inside the spread |

### 📊 Best Bets (`/bets`)
| Type | Description |
|---|---|
| **Volume Spikes** | Markets where 24h volume is unusually high — sharp money moving in |
| **Edge Bets** | Extreme prices (5–20¢ long shots, 80–95¢ near-certainties) with good liquidity |
| **High Value** | Active 20–80¢ markets with deep liquidity and high 24h activity |

### 🕵️ Insider / Sharp Money (`/insider`)
| Type | Description |
|---|---|
| **Large Trades** | Single trades > $500 on the Polymarket CLOB |
| **Sharp Markets** | Vol/Liq ratio > 0.8x — someone hammering a side hard |
| **Whale Accumulation** | Same wallet buying the same market multiple times |
| **Late Resolution Bets** | Big volume on markets resolving within 7 days — classic insider timing |

### 🔔 Auto Alerts (`/alerts`)
- Arb scanner: **every 15 minutes**
- Best bets: **every 30 minutes**
- Insider signals: **every 60 minutes**
- Individually toggleable per user

---

## 🚀 Deploy on Railway

### Step 1 — Get a Telegram bot token
1. Open Telegram, find `@BotFather`
2. Send `/newbot` and follow the prompts
3. Copy the token

### Step 2 — Push to GitHub
```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/YOUR_USERNAME/polymarket-bot.git
git push -u origin main
```

### Step 3 — Deploy on Railway
1. Go to [railway.app](https://railway.app) → **New Project**
2. **Deploy from GitHub repo** → select your repo
3. Go to **Variables** tab → add:

```
TELEGRAM_BOT_TOKEN = <your token>
```

That's it. Railway detects `Procfile` and starts the bot automatically.

---

## 💻 Run Locally

```bash
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your token
python bot.py
```

---

## 📱 Commands

```
/start    — Welcome + quick-action buttons
/help     — Show help

/arb      — Arbitrage opportunities menu
/bets     — Best bet opportunities menu
/insider  — Sharp money / insider signals menu
/alerts   — Manage your alert settings
```

---

## ⚙️ How the Arb Logic Works

### Cross-Platform Arbitrage
Polymarket and Kalshi both list markets on the same real-world events (Fed rate decisions, elections, BTC price, etc.) but price them independently.

If **Polymarket YES = 0.62** and **Kalshi NO = 0.34**, total cost = **0.96** → guaranteed **$0.04 profit per $0.96 invested (~4.2%)** when the event resolves either way.

The bot matches markets across platforms using topic keyword fuzzy-matching and calculates:
```
profit = 1.0 - (best_yes_price + best_no_price)
```

### Sum Deviation Arb
On a single platform, if YES = 0.55 and NO = 0.48, sum = 1.03:
- **Sell** both sides for $1.03 total
- Pay out $1.00 when resolved
- Keep **$0.03 profit (~3%)**

Or if YES + NO < 1.0:
- **Buy** both sides for < $1.00
- Receive $1.00 when resolved
- Guaranteed profit

### Spread / Market Making
On Kalshi, if YES bid = 42¢ and YES ask = 58¢ (16¢ spread):
- Post a YES bid at 43¢ and YES ask at 57¢
- Collect the spread from both sides
- Works best on high-volume low-volatility markets

---

## 📡 Data Sources

| Platform | Endpoint | Used For |
|---|---|---|
| Polymarket Gamma API | `gamma-api.polymarket.com` | Market metadata, prices, volume |
| Polymarket CLOB API | `clob.polymarket.com` | Live trades, orderbook |
| Kalshi Trade API v2 | `trading-api.kalshi.com` | Market prices, bid/ask, volume |

All public APIs — no API keys required.

---

## 🏗️ Project Structure

```
polymarket-bot/
├── bot.py                     ← Entry point
├── Procfile / railway.toml    ← Railway config
├── requirements.txt
├── handlers/
│   ├── start.py               ← /start, /help
│   ├── arbitrage.py           ← /arb + inline callbacks
│   ├── bets.py                ← /bets + inline callbacks
│   ├── insider.py             ← /insider + inline callbacks
│   └── alerts.py              ← /alerts + toggle callbacks
├── services/
│   ├── polymarket.py          ← Gamma + CLOB API, signal detection
│   ├── kalshi.py              ← Kalshi API v2
│   ├── arbitrage.py           ← Cross-platform arb engine
│   ├── insider.py             ← Sharp money detection
│   └── scheduler.py           ← APScheduler push alerts
└── utils/
    ├── database.py            ← JSON persistence
    └── formatting.py          ← Message helpers
```

---

## ⚠️ Disclaimer

This bot provides information for educational purposes only. Prediction market trading involves risk. Always verify opportunities independently before placing real money. The bot does not execute trades on your behalf.
