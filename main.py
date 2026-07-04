import os
import requests
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo


TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


WATCHLIST = {
    # 美股大盤
    "🇺🇸 S&P 500": "^GSPC",
    "🇺🇸 Nasdaq": "^IXIC",
    "🇺🇸 Dow Jones": "^DJI",
    "🇺🇸 VIX": "^VIX",

    # 美股科技與台股連動
    "🇺🇸 Nvidia": "NVDA",
    "🇺🇸 Apple": "AAPL",
    "🇺🇸 Tesla": "TSLA",
    "🇺🇸 TSM ADR": "TSM",

    # 台股大盤與 ETF
    "🇹🇼 台股加權": "^TWII",
    "🇹🇼 0050 元大台灣50": "0050.TW",
    "🇹🇼 00631L 元大台灣50正2": "00631L.TW",

    # 台股權值股
    "🇹🇼 台積電": "2330.TW",
    "🇹🇼 聯發科": "2454.TW",
    "🇹🇼 鴻海": "2317.TW",
}


def fetch_quote(symbol: str):
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="5d")

    if hist.empty or len(hist) < 2:
        return None

    latest = hist.iloc[-1]
    previous = hist.iloc[-2]

    close = float(latest["Close"])
    prev_close = float(previous["Close"])
    change_pct = (close - prev_close) / prev_close * 100

    return close, change_pct


def format_line(name: str, symbol: str):
    data = fetch_quote(symbol)

    if data is None:
        return f"{name}：資料暫時無法取得"

    close, change_pct = data
    arrow = "🔺" if change_pct >= 0 else "🔻"
    return f"{name}：{close:,.2f} {arrow} {change_pct:+.2f}%"


def format_leverage_etf_section():
    etf_0050 = fetch_quote("0050.TW")
    etf_00631l = fetch_quote("00631L.TW")

    lines = [
        "",
        "⚡ 0050 / 正二觀察",
    ]

    if etf_0050 is None or etf_00631l is None:
        lines.append("0050 或 00631L 資料暫時無法取得")
        return lines

    close_0050, pct_0050 = etf_0050
    close_00631l, pct_00631l = etf_00631l

    lines.append(f"0050：{close_0050:,.2f}，{pct_0050:+.2f}%")
    lines.append(f"00631L：{close_00631l:,.2f}，{pct_00631l:+.2f}%")

    if abs(pct_0050) >= 0.01:
        leverage_ratio = pct_00631l / pct_0050
        lines.append(f"00631L / 0050 單日倍數：約 {leverage_ratio:.2f}x")
    else:
        lines.append("0050 今日接近 0%，暫不計算單日倍數")

    if abs(pct_00631l) >= 5:
        lines.append("⚠️ 00631L 今日波動超過 5%，請特別注意槓桿 ETF 風險。")
    elif abs(pct_00631l) >= 3:
        lines.append("提醒：00631L 今日波動偏大。")
    else:
        lines.append("狀態：00631L 今日波動相對正常。")

    return lines


def format_market_message():
    now = datetime.now(ZoneInfo("Asia/Taipei"))

    lines = [
        "📈 台美股每日概況",
        f"時間：{now.strftime('%Y-%m-%d %H:%M')} 台北時間",
        "",
        "🇺🇸 美股",
    ]

    for name, symbol in WATCHLIST.items():
        if symbol.endswith(".TW") or symbol == "^TWII":
            continue
        lines.append(format_line(name, symbol))

    lines.append("")
    lines.append("🇹🇼 台股")

    for name, symbol in WATCHLIST.items():
        if symbol.endswith(".TW") or symbol == "^TWII":
            lines.append(format_line(name, symbol))

    lines.extend(format_leverage_etf_section())

    lines.append("")
    lines.append("提醒：資料僅供個人研究與資訊參考，不構成投資建議。")

    return "\n".join(lines)


def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }

    response = requests.post(url, json=payload, timeout=20)
    response.raise_for_status()


def main():
    message = format_market_message()
    send_telegram_message(message)


if __name__ == "__main__":
    main()
