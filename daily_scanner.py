# daily_scanner.py
import os
import pandas as pd
from datetime import datetime
from data_loader import get_stock_list
from analyzer import calculate_sctr_ranks, check_vcp_advanced
import requests

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram_alert(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"})

def run_global_scan():
    markets = ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"]
    report = "🏹 <b>VCP Alpha 每日報告</b>\n\n"
    all_results = []
    
    for market in markets:
        tickers, _ = get_stock_list(market)
        if not tickers:
            continue
        sctr_map, sctr_hist = calculate_sctr_ranks(tickers)
        results = []
        
        for t in tickers:
            res = check_vcp_advanced(t, sctr_map, sctr_hist, b_only=False, b_days=20)
            if res:
                results.append([market] + res)
        
        if results:
            report += f"<b>{market}</b> - 找到 {len(results)} 檔\n"
            # 取前5優質
            top5 = sorted(results, key=lambda x: x[-1], reverse=True)[:5]
            for r in top5:
                report += f"• {r[1]} | SCTR {r[4]} | {r[7]}\n"
            all_results.extend(results)
    
    if all_results:
        df = pd.DataFrame(all_results)
        filename = f"vcp_report_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
        df.to_excel(filename, index=False)
        send_telegram_alert(report)
        # 可再加上傳檔案功能
        print("✅ 每日報告已發送")
    else:
        send_telegram_alert("⚠️ 今日全球無優質 VCP 標的")

if __name__ == "__main__":
    run_global_scan()
