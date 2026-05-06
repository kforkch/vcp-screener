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
    for t in tickers:
        try:
            tk = yf.Ticker(t)
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
            print(f"✅ {t} 最新狀態同步成功")
            
            # ==================== 2. 同步完整 2 年歷史 K 線至 stock_backtest_data ====================
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
            
            # 使用批次寫入 (Bulk Upsert)，每 500 筆打包一次，速度極快且不易出錯
            chunk_size = 500
            for i in range(0, len(backtest_records), chunk_size):
                supabase.table("stock_backtest_data").upsert(backtest_records[i:i+chunk_size]).execute()
            
            print(f"📊 {t} 共 {len(backtest_records)} 筆歷史 K 線回測數據同步成功！")

        except Exception as e:
            print(f"❌ {t} 同步過程中發生錯誤: {e}")

if __name__ == "__main__":
    target_list = []
    try:
        from data_loader import get_stock_list
        for market in ["美股 (Nasdaq 100)", "港股 (恒生指數)"]:
            tickers, _ = get_stock_list(market)
            if tickers:
                target_list.extend(tickers)
        target_list = sorted(list(set(target_list)))
    except Exception as e:
        print(f"⚠️ 自動載入市場清單時發生非致命異常 ({e})，降級使用核心測試清單。")

    if not target_list:
        target_list = ["AAPL", "0700.HK", "600519.SS"] 
        
    get_and_upload(target_list)
