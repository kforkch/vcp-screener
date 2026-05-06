# downloader_to_cloud.py
import os
import yfinance as yf
import pandas as pd

def get_supabase_client():
    """安全獲取 Supabase 用戶端"""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    if not url or not key or url == "" or key == "":
        print("⚠️ 警告：未在 GitHub Secrets 中設定 SUPABASE_URL 或 SUPABASE_KEY！")
        return None
        
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception as e:
        print(f"❌ 初始化 Supabase 用戶端失敗: {e}")
        return None

def get_and_upload(tickers):
    supabase = get_supabase_client()
    if not supabase:
        print("⏭️ 由於未能成功連接 Supabase 數據中台，本次同步任務跳過。")
        return

    print(f"🚀 開始同步 {len(tickers)} 檔股票數據至 Supabase 數據中台...")
    
    for idx, t in enumerate(tickers, 1):
        try:
            print(f"[{idx}/{len(tickers)}] 正在抓取 {t} ...")
            tk = yf.Ticker(t)
            
            # 抓取 2 年歷史數據，用來作回測數據源
            df = tk.history(period="2y")
            if df.empty:
                print(f"⚠️ {t} 無 K 線交易數據，跳過")
                continue
            
            # ==================== 1. 同步最新狀態至 stock_warehouse ====================
            warehouse_data = {
                "ticker": t,
                "price": float(df['Close'].iloc[-1]),
                "sector": tk.info.get('sector', 'Unknown'),
                "last_update": df.index[-1].strftime('%Y-%m-%d')
            }
            supabase.table("stock_warehouse").upsert(warehouse_data).execute()
            
            # ==================== 2. 同步 2 年歷史 K 線至 stock_backtest_data ====================
            backtest_records = []
            for date, row in df.iterrows():
                backtest_records.append({
                    "ticker": t,
                    "date": date.strftime('%Y-%m-%d'),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": int(row["Volume"])
                })
            
            # 批次 Upsert (Bulk Upsert)，每 500 筆打包一次，大幅減輕 API 負擔並提升速度
            chunk_size = 500
            for i in range(0, len(backtest_records), chunk_size):
                supabase.table("stock_backtest_data").upsert(backtest_records[i:i+chunk_size]).execute()
            
            print(f"✅ {t} 同步成功 (最新價: {warehouse_data['price']}, 歷史數據: {len(backtest_records)} 筆)")

        except Exception as e:
            print(f"❌ {t} 同步過程中發生錯誤: {e}")

if __name__ == "__main__":
    target_list = []
    
    # 解決 GitHub Actions 工作目錄下的路徑定位問題
    # 若在 Actions 執行時發現 data 目錄不存在，手動將上傳的 txt 複製或建立對應結構
    if not os.path.exists("data"):
        os.makedirs("data", exist_ok=True)
        # 尋找有沒有直接放在根目錄下的 txt，有的話就搬移進 data/
        for txt_file in ["hsi.txt", "csi300.txt"]:
            if os.path.exists(txt_file):
                os.rename(txt_file, os.path.join("data", txt_file))
                print(f"📦 已自動將根目錄的 {txt_file} 歸檔至 data/ 資料夾。")

    try:
        from data_loader import get_stock_list
        
        # 🌟 精準對齊你的 data_loader.py 內的四大市場名稱！
        my_markets = [
            "美股 (S&P 500)", 
            "美股 (Nasdaq 100)", 
            "港股 (恒生指數)", 
            "中國 A 股 (滬深 300 龍頭)"  # 一字不差，精準對接
        ]
        
        for market in my_markets:
            tickers, _ = get_stock_list(market)
            if tickers:
                target_list.extend(tickers)
                print(f"📥 成功載入 【{market}】，共計 {len(tickers)} 檔股票。")
                
        # 去除重複股票代號並排序
        target_list = sorted(list(set(target_list)))
        print(f"🔥 全球名單載入完畢！本次將同步 {len(target_list)} 檔股票數據至 Supabase。")
        
    except Exception as e:
        print(f"⚠️ 自動載入市場清單時發生異常 ({e})，降級使用核心測試清單。")

    # 基礎保底
    if not target_list:
        target_list = ["AAPL", "0700.HK", "600519.SS"] 
        
    get_and_upload(target_list)
