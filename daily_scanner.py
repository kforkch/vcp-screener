import os
import requests
from data_loader import get_stock_list
from analyzer import calculate_sctr_ranks, check_vcp_advanced

# 從環境變數讀取，確保安全性
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def make_link(t):
    """為 Telegram 產生點擊連結"""
    t_str = str(t)
    if ".HK" in t_str:
        code = t_str.replace('.HK', '').lstrip('0')
        return f"https://www.tradingview.com/chart/?symbol=HKEX:{code}"
    elif ".SS" in t_str or ".SZ" in t_str:
        code = t_str.split('.')[0]
        prefix = "SSE" if ".SS" in t_str else "SZSE"
        return f"https://www.tradingview.com/chart/?symbol={prefix}:{code}"
    else:
        return f"https://www.tradingview.com/chart/?symbol={t_str.replace('.', '-')}"

def send_telegram_alert(message):
    """發送 HTML 格式訊息"""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("警告：未設定 Telegram Token 或 Chat ID")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"發送失敗: {e}")

def run_global_scan():
    markets = ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"]
    report = "🚀 <b>今日全球 VCP 強勢股報告</b>\n\n"
    found_any = False
    
    for market in markets:
        tickers, _ = get_stock_list(market)
        if not tickers: continue
        
        sctr_map = calculate_sctr_ranks(tickers)
        results = []
        
        # 進行掃描
        for t in tickers:
            # 這裡設定篩選條件 (例如 SCTR > 70, 突破檢測 20 天)
            res = check_vcp_advanced(t, sctr_map, b_only=False, b_days=20)
            if res and res[3] >= 70.0:
                results.append(res)
        
        # 按 SCTR 排名排序 (索引 3 是 SCTR)
        results.sort(key=lambda x: x[3], reverse=True)
        
        if results:
            found_any = True
            report += f"📊 <b>{market}</b> ({len(results)}檔，顯示前10檔):\n"
            for r in results[:10]:
                link = make_link(r[0])
                # r[0]: 代碼, r[1]: 價格, r[3]: SCTR, r[6]: 狀態
                report += f"• <a href='{link}'>{r[0]}</a> | ${r[1]} | SCTR:{r[3]} | {r[6]}\n"
            report += "\n"
    
    if found_any:
        send_telegram_alert(report)
    else:
        send_telegram_alert("⚠️ 今日掃描：全球市場無符合 VCP 條件的標的。")

if __name__ == "__main__":
    run_global_scan()
