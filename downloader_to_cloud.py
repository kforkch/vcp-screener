import os
import pandas as pd
import yfinance as yf
from supabase import create_client

# 從 GitHub Secrets 或系統環境變數獲取
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("❌ 錯誤：未偵測到 SUPABASE_URL 或 SUPABASE_KEY 環境變數。")

supabase = create_client(url, key)

def get_and_upload(tickers):
    """
    下載全歷史日 K 數據並 Upsert 到 Supabase 進行中台緩存
    """
    print(f"🚀 開始同步 {len(tickers)} 檔標的至 Supabase 數據中台...")
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            # 抓取 1 年半至 2 年的數據，確保足夠計算 SMA200 與 52 週新高
            df = tk.history(period="500d")
            if df.empty:
                print(f"⚠️ {t} 無數據")
                continue
            
            # 1. 整理最近 250 筆 K 線數據 (精簡存儲，保障高效)
            kline_list = []
            recent_df = df.tail(250)
            for date_idx, row in recent_df.iterrows():
                kline_list.append({
                    "ticker": t,
                    "date": date_idx.strftime('%Y-%m-%d'),
                    "open": float(row['Open']),
                    "high": float(row['High']),
                    "low": float(row['Low']),
                    "close": float(row['Close']),
                    "volume": int(row['Volume'])
                })
            
            # 將 K 線批次寫入 (Upsert 到 stock_klines 表)
            if kline_list:
                supabase.table("stock_klines").upsert(kline_list).execute()

            # 2. 獲取並更新個股快照 (行業與當前最新價格)
            try:
                sector = tk.info.get('sector', 'Unknown')
            except:
                sector = 'Unknown'

            snapshot_data = {
                "ticker": t,
                "price": float(df['Close'].iloc[-1]),
                "sector": sector,
                "last_update": df.index[-1].strftime('%Y-%m-%d')
            }
            
            # Upsert 到主要資料表
            supabase.table("stock_warehouse").upsert(snapshot_data).execute()
            print(f"✅ {t} 同步成功 (含歷史 K 線與個股快照)")
        except Exception as e:
            print(f"❌ {t} 同步失敗: {e}")

if __name__ == "__main__":
    # 自動加載所有要監控的市場清單
    from data_loader import get_stock_list
    
    all_tickers = []
    markets = ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"]
    for m in markets:
        tickers, _ = get_stock_list(m)
        if tickers:
            all_tickers.extend(tickers)
            
    # 去除重複值
    all_tickers = list(set(all_tickers))
    
    if not all_tickers:
        # 備用核心監控名單
        all_tickers = ["AAPL", "MSFT", "GOOG", "0700.HK", "600519.SS"]
        
    get_and_upload(all_tickers)
