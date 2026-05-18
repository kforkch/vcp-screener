# daily_scanner.py
import os
import requests
import pandas as pd
from datetime import datetime
from data_loader import get_stock_list
from analyzer import calculate_sctr_ranks, check_vcp_advanced

# Load config from env vars
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def make_link(t):
    """Generate TradingView links based on ticker format"""
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
    """Send HTML formatted message to Telegram"""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Warning: TELEGRAM_TOKEN or CHAT_ID not set")
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
        print(f"❌ Message failed: {e}")

def send_telegram_file(file_path):
    """Send generated Excel report to Telegram"""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    try:
        with open(file_path, 'rb') as f:
            files = {'document': f}
            data = {'chat_id': CHAT_ID, 'caption': f"📊 VCP Alpha Daily Report: {os.path.basename(file_path)}"}
            response = requests.post(url, files=files, data=data)
            if response.status_code == 200:
                print("✅ File sent to Telegram")
            else:
                print(f"❌ File send failed: {response.text}")
    except Exception as e:
        print(f"❌ File error: {e}")

def run_global_scan():
    """
    Execution loop for the daily global scan.
    Coordinates data loading, VCP analysis, and reporting.
    """
    report_dir = "reports"
    if not os.path.exists(report_dir):
        os.makedirs(report_dir)

    markets = ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"]
    report = "🏹 <b>VCP Alpha Daily Terminal</b>\n\n"
    all_results = []
    found_any = False
    
    columns = [
        "Ticker", "Price", "Dist_High%", "SCTR", "Tightness", "Vol_Ratio", "Status", "Sector", 
        "Pivot", "StopLoss", "Target"
    ]
    
    for market in markets:
        tickers, _ = get_stock_list(market)
        if not tickers: continue
        
        # Step 1: Momentum Ranks (O'Neil/Minervini Relative Strength)
        sctr_map, sctr_hist_map = calculate_sctr_ranks(tickers, lookback=20)
        results = []
        
        for t in tickers:
            # Use advanced VCP logic based on 'Bible' strategies
            res = check_vcp_advanced(t, sctr_map, sctr_hist_map, b_only=False, b_days=20)
            if res:
                results.append(res)
                all_results.append([market] + res)
        
        # Sort by SCTR rank (Strongest first)
        results.sort(key=lambda x: x[3], reverse=True)
        
        if results:
            found_any = True
            report += f"📊 <b>{market}</b> (Found {len(results)} targets)\n"
            for r in results[:5]: # Top 5 per market
                link = make_link(r[0])
                report += f"• <b>{r[0]}</b> | <a href='{link}'>Chart</a> | SCTR: {r[3]} ({r[6]})\n"
            report += "\n"
    
    if found_any:
        df_full = pd.DataFrame(all_results, columns=["Market"] + columns)
        filename = f"vcp_report_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
        file_path = os.path.join(report_dir, filename)
        
        df_full.to_excel(file_path, index=False)
        
        report += "📁 Report generated. See attachment below."
        send_telegram_alert(report)
        send_telegram_file(file_path)
        print(f"✅ Report {file_path} sent successfully")
    else:
        send_telegram_alert("⚠️ Daily Scan: No top-tier VCP targets found across global markets today.")

if __name__ == "__main__":
    run_global_scan()
