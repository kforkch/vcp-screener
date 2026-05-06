# daily_scanner.py
import os
import requests
import pandas as pd
from datetime import datetime
from data_loader import get_stock_list
from data_loader import get_stock_list, calculate_sctr_ranks, supabase

# ==================== 核心 yfinance 攔截注入 ====================
import yfinance as yf

def mock_download(tickers, *args, **kwargs):
    ticker = tickers[0] if isinstance(tickers, list) else tickers
    try:
        response = supabase.table("stock_klines")\
            .select("date, open, high, low, close, volume")\
            .eq("ticker", ticker)\
            .order("date", ascending=True)\
            .execute()
        
        data = response.data
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df.rename(columns={
            "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"
        }, inplace=True)
        return df
    except Exception as e:
        print(f"Mock Download 發生錯誤: {e}")
        return pd.DataFrame()

yf.download = mock_download
# ===============================================================

# 載入原分析器
from analyzer import check_vcp_advanced

# 從環境變數讀取
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
        requests.post(url, json=payload)
    except Exception as e:
        print(f"❌ 訊息發送失敗: {e}")

def send_telegram_file(file_path):
    """將 Excel 檔案透過 Telegram 發送"""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    try:
        with open(file_path, 'rb') as f:
            files = {'document': f}
            data = {'chat_id': CHAT_ID, 'caption': f"📊 VCP 掃描報告: {os.path.basename(file_path)}"}
            response = requests.post(url, files=files, data=data)
            if response.status_code == 200:
                print("✅ 檔案已成功發送至 Telegram")
            else:
                print(f"❌ 檔案發送失敗: {response.text}")
    except Exception as e:
        print(f"❌ 發送檔案時發生錯誤: {e}")

def run_global_scan():
    """執行全市場掃描並整理報告與生成 Excel"""
    report_dir = "reports"
    if not os.path.exists(report_dir):
        os.makedirs(report_dir)

    markets = ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"]
    report = "🏹 <b>VCP Alpha 每日決策終端</b>\n\n"
    all_results = []
    found_any = False
    
    columns = [
        "代碼", "價格", "距離高點%", "SCTR", "收縮狀態", "量比", "狀態", "行業", 
        "樞軸(Pivot)", "停損(SL)", "目標(Target)"
    ]
    
    for market in markets:
        tickers, _ = get_stock_list(market)
        if not tickers: continue
        
        # 獲取當前與 20 天前的歷史 SCTR 對照表
        sctr_map, sctr_hist_map = calculate_sctr_ranks(tickers, lookback=20)
        results = []
        
        for t in tickers:
            res = check_vcp_advanced(t, sctr_map, sctr_hist_map, b_only=False, b_days=20)
            if res:
                results.append(res)
                all_results.append([market] + res)
        
        results.sort(key=lambda x: x[3], reverse=True)
        
        if results:
            found_any = True
            report += f"📊 <b>{market}</b> (篩選出 {len(results)} 檔)\n"
            for r in results[:5]:
                link = make_link(r[0])
                report += f"• <b>{r[0]}</b> | <a href='{link}'>圖表</a> | SCTR: {r[3]} ({r[6]})\n"
            report += "\n"
    
    if found_any:
        df_full = pd.DataFrame(all_results, columns=["市場"] + columns)
        filename = f"vcp_report_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
        file_path = os.path.join(report_dir, filename)
        
        df_full.to_excel(file_path, index=False)
        
        report += "📁 報告已生成，請參見下方附件。"
        send_telegram_alert(report)
        send_telegram_file(file_path)
        print(f"✅ 報表 {file_path} 已發送")
    else:
        send_telegram_alert("⚠️ 今日掃描：全球市場無符合 VCP 頂級收縮且 SCTR 攀升標的。")

if __name__ == "__main__":
    run_global_scan()
