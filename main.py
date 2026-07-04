import os
import sys
import requests
import yfinance as yf
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
ALLOWED_TELEGRAM_USER_IDS = os.environ.get("ALLOWED_TELEGRAM_USER_IDS", "")


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


def send_telegram_message(text: str, chat_id: str | int = None):
    target_chat_id = chat_id or TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": target_chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }

    response = requests.post(url, json=payload, timeout=20)
    response.raise_for_status()


def fetch_quote(symbol: str):
    try:
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
    except Exception:
        return None


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
        lines.append("風險燈號：🔴 高波動，00631L 今日波動超過 5%")
    elif abs(pct_00631l) >= 3:
        lines.append("風險燈號：🟡 注意，00631L 今日波動偏大")
    else:
        lines.append("風險燈號：🟢 正常")

    return lines


def fetch_market_news():
    if not NEWS_API_KEY:
        return ["尚未設定 NEWS_API_KEY，暫時不顯示新聞。"]

    queries = [
        '(Federal Reserve OR inflation OR bond yields OR Nasdaq OR Nvidia OR Apple OR Tesla OR "S&P 500")',
        '(TSMC OR "Taiwan stocks" OR "Taiwan semiconductor" OR "Taiwan dollar" OR "Taiwan ETF")',
    ]

    articles = []

    for query in queries:
        url = "https://newsapi.org/v2/everything"
        params = {
            "apiKey": NEWS_API_KEY,
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 5,
        }

        try:
            response = requests.get(url, params=params, timeout=20)
            response.raise_for_status()
            data = response.json()

            for article in data.get("articles", []):
                title = article.get("title")
                source = article.get("source", {}).get("name", "Unknown")
                if title:
                    articles.append((title, source))
        except Exception as error:
            return [f"新聞資料暫時無法取得：{error}"]

    # 去除重複標題
    seen = set()
    unique_articles = []

    for title, source in articles:
        clean_title = title.strip()
        if clean_title not in seen:
            seen.add(clean_title)
            unique_articles.append((clean_title, source))

    if not unique_articles:
        return ["目前沒有抓到相關新聞。"]

    lines = []

    for index, (title, source) in enumerate(unique_articles[:6], start=1):
        impact = estimate_news_impact(title)
        lines.append(f"{index}. {title}")
        lines.append(f"   來源：{source}｜初步影響：{impact}")

    return lines


def estimate_news_impact(title: str):
    lower_title = title.lower()

    positive_keywords = [
        "rally",
        "surge",
        "beats",
        "record high",
        "optimism",
        "cut rates",
        "rate cut",
        "strong demand",
        "ai demand",
    ]

    negative_keywords = [
        "falls",
        "drop",
        "selloff",
        "higher yields",
        "inflation",
        "tariff",
        "war",
        "sanction",
        "weak demand",
        "recession",
    ]

    semiconductor_keywords = [
        "nvidia",
        "tsmc",
        "semiconductor",
        "chip",
        "ai",
        "taiwan",
    ]

    positive_score = sum(1 for word in positive_keywords if word in lower_title)
    negative_score = sum(1 for word in negative_keywords if word in lower_title)
    semi_score = sum(1 for word in semiconductor_keywords if word in lower_title)

    if semi_score > 0 and positive_score > negative_score:
        return "偏多半導體 / 台股電子"
    if semi_score > 0 and negative_score > positive_score:
        return "偏空半導體 / 台股電子"
    if positive_score > negative_score:
        return "偏多風險資產"
    if negative_score > positive_score:
        return "偏空風險資產"
    return "中性，需觀察市場反應"


def format_news_section():
    lines = [
        "",
        "📰 可能影響美股 / 台股的新聞",
    ]

    news_lines = fetch_market_news()
    lines.extend(news_lines)

    lines.append("")
    lines.append("新聞判讀提醒：這是根據標題做的初步分類，不代表股市一定會照此方向反應。")

    return lines


def format_market_message(report_type: str = "now"):
    now = datetime.now(ZoneInfo("Asia/Taipei"))

    if report_type == "now":
        title = "⚡ 即時台美股概況"
    else:
        title = "📈 台美股每日概況"

    lines = [
        title,
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
    lines.extend(format_news_section())

    lines.append("")
    lines.append("提醒：資料僅供個人研究與資訊參考，不構成投資建議。")

    return "\n".join(lines)


def get_updates():
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json().get("result", [])


def confirm_updates(offset: int):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    requests.get(url, params={"offset": offset}, timeout=20)


def is_user_allowed(user_id: int):
    if not ALLOWED_TELEGRAM_USER_IDS.strip():
        # 沒設定白名單時，先允許所有人。
        # 建議測試完 /whoami 後，把自己的 user id 加進 GitHub Secret。
        return True

    allowed_ids = {
        item.strip()
        for item in ALLOWED_TELEGRAM_USER_IDS.split(",")
        if item.strip()
    }

    return str(user_id) in allowed_ids


def process_telegram_commands():
    updates = get_updates()

    if not updates:
        return

    max_update_id = max(update["update_id"] for update in updates)

    for update in updates:
        message = update.get("message")
        if not message:
            continue

        text = message.get("text", "").strip()
        chat = message.get("chat", {})
        user = message.get("from", {})

        chat_id = chat.get("id")
        user_id = user.get("id")
        username = user.get("username", "")
        message_date = message.get("date", 0)

        now_timestamp = int(datetime.now(timezone.utc).timestamp())
        message_age_seconds = now_timestamp - message_date

        if text.startswith("/whoami"):
            reply = [
                "你的 Telegram 資訊：",
                f"user_id：{user_id}",
                f"chat_id：{chat_id}",
                f"username：@{username}" if username else "username：沒有設定",
                "",
                "如果要限制只有你能使用 /now，",
                "請把 user_id 填到 GitHub Secret：ALLOWED_TELEGRAM_USER_IDS",
            ]
            send_telegram_message("\n".join(reply), chat_id=chat_id)

        elif text.startswith("/now"):
            if message_age_seconds > 15 * 60:
                continue

            if not is_user_allowed(user_id):
                send_telegram_message("你沒有權限使用 /now。", chat_id=chat_id)
                continue

            send_telegram_message("收到 /now，正在產生即時市場概況並推送到 Channel。", chat_id=chat_id)

            market_message = format_market_message(report_type="now")
            send_telegram_message(market_message, chat_id=TELEGRAM_CHAT_ID)

            send_telegram_message("已推送到 Channel。", chat_id=chat_id)

    # 告訴 Telegram：這些 updates 已經處理過，避免下次重複處理
    confirm_updates(max_update_id + 1)


def main():
    mode = "send-digest"

    if len(sys.argv) >= 2:
        mode = sys.argv[1]

    if mode == "--check-commands":
        process_telegram_commands()
    else:
        message = format_market_message(report_type="digest")
        send_telegram_message(message, chat_id=TELEGRAM_CHAT_ID)


if __name__ == "__main__":
    main()
