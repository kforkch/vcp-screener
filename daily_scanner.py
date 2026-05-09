# daily_scanner.py
import os
import requests
import pandas as pd
from datetime import datetime
import concurrent.futures
from data_loader import get_stock_list
from analyzer import calculate_sctr_ranks, check_vcp_advanced

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
        print("⚠️ 警告：未設定 Telegram Token 或 Chat ID")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        res = requests.post(url, json=payload)
        if res.status_code != 200:
            print(f"⚠️ 訊息發送狀態異常: {res.text}")
    except Exception as e:
        print(f"❌ 訊息發送失敗: {e}")

def send_telegram_file(file_path):
    """將報告檔案透過 Telegram 發送"""
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

def process_single_ticker(t, sctr_map, sctr_hist_map):
    """獨立的工作節點函數：供多執行緒調用以執行單檔股票的 VCP 檢測"""
    try:
        res = check_vcp_advanced(t, sctr_map, sctr_hist_map, b_only=False, b_days=20)
        return res
    except Exception as e:
        print(f"⚠️ 掃描單檔股票 {t} 時發生錯誤: {e}")
        return None

def run_global_scan():
    """執行全市場掃描並整理報告與生成 Excel"""
    report_dir = "reports"
    if not os.path.exists(report_dir):
        try:
            os.makedirs(report_dir, exist_ok=True)
        except Exception as e:
            print(f"⚠️ 無法建立 reports 資料夾: {e}，改用當前目錄儲存")
            report_dir = "."

    markets = ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"]
    report = "🏹 <b>VCP Alpha 每日決策終端</b>\n\n"
    all_results = []
    found_any = False
    
    columns = [
        "代碼", "價格", "距離高點%", "SCTR", "收縮狀態", "量比", "狀態", "行業", 
        "樞軸(Pivot)", "停損(SL)", "目標(Target)"
    ]
    
    for market in markets:
        try:
            tickers, _ = get_stock_list(market)
            if not tickers: continue
            
            # 獲取當前與 20 天前的歷史 SCTR 對照表
            sctr_map, sctr_hist_map = calculate_sctr_ranks(tickers, lookback=20)
            results = []
            
            print(f"🚀 開始並行掃描 {market} ({len(tickers)} 檔)...")
            
            # 💡 優化：啟動 10 個執行緒進行並行掃描，大幅壓榨 I/O 與 CPU 效能
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                # 提交所有任務
                future_to_ticker = {
                    executor.submit(process_single_ticker, t, sctr_map, sctr_hist_map): t 
                    for t in tickers
                }
                
                # 收集完成的結果
                for future in concurrent.futures.as_completed(future_to_ticker):
                    res = future.result()
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
        except Exception as e:
            print(f"⚠️ 掃描市場 {market} 失敗: {e}")
    
    if found_any:
        df_full = pd.DataFrame(all_results, columns=["市場"] + columns)
        date_str = datetime.now().strftime('%Y-%m-%d')
        
        # 💡 防禦性寫入：優先導出 Excel，若缺少 openpyxl 庫則自動降級為 CSV
        try:
            filename = f"vcp_report_{date_str}.xlsx"
            file_path = os.path.join(report_dir, filename)
            df_full.to_excel(file_path, index=False)
        except Exception as e:
            print(f"⚠️ 無法導出 Excel ({e})，自動降級為 CSV 導出...")
            filename = f"vcp_report_{date_str}.csv"
            file_path = os.path.join(report_dir, filename)
            df_full.to_csv(file_path, index=False, encoding='utf-8-sig')
        
        report += "📁 報告已生成，請參見下方附件。"
        send_telegram_alert(report)
        send_telegram_file(file_path)
        print(f"✅ 報表 {file_path} 已發送")
    else:
        send_telegram_alert("⚠️ 今日掃描：全球市場無符合 VCP 頂級收縮且 SCTR 攀升標的。")

if __name__ == "__main__":
    run_global_scan()
