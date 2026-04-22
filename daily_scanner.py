# daily_scanner.py
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
    """發送 HTML 格式訊息至 Telegram"""
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
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ 訊息發送成功")
        else:
            print(f"❌ 發送失敗，狀態碼: {response.status_code}, 回應: {response.text}")
    except Exception as e:
        print(f"❌ 網路連線錯誤: {e}")

def run_global_scan():
    """執行全市場掃描並整理報告"""
    markets = ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"]
    report = "🏹 <b>VCP Alpha 每日決策終端</b>\n\n"
    found_any = False
    
    for market in markets:
        tickers, _ = get_stock_list(market)
        if not tickers: continue
        
        # 計算 SCTR
        sctr_map = calculate_sctr_ranks(tickers)
        results = []
        
        # 進行 VCP 掃描 (ATR 邏輯已內建在 analyzer 中)
        for t in tickers:
            # 篩選條件：SCTR > 80, 檢測 20 天內的突破
            res = check_vcp_advanced(t, sctr_map, b_only=False, b_days=20)
            if res and res[3] >= 80.0:
                results.append(res)
        
        # 按 SCTR 排名排序 (索引 3 是 SCTR)
        results.sort(key=lambda x: x[3], reverse=True)
        
        if results:
            found_any = True
            report += f"📊 <b>{market}</b> (篩選出 {len(results)} 檔)\n"
            # 限制顯示前 5 檔，避免訊息過長
            for r in results[:5]:
                link = make_link(r[0])
                # r[0]:代碼, r[1]:價格, r[3]:SCTR, r[6]:狀態, r[8]:Pivot, r[9]:SL, r[10]:Target, r[5]:量比
                report += (
                    f"• <b>{r[0]}</b> | <a href='{link}'>圖表</a>\n"
                    f"  ├ 現價: ${r[1]} | SCTR: {r[3]}\n"
                    f"  ├ 樞軸: ${r[8]} | 停損: ${r[9]} | 目標: ${r[10]}\n"
                    f"  └ 量比: {r[5]} | 狀態: {r[6]}\n"
                )
            report += "\n"
    
    if found_any:
        send_telegram_alert(report)
    else:
        send_telegram_alert("⚠️ 今日掃描：全球市場無符合 VCP 高強度條件的標的。")

if __name__ == "__main__":
    run_global_scan()
