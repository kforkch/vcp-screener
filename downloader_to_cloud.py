import os
import pandas as pd
import yfinance as yf
from supabase import create_client

# 從 GitHub Secrets 獲取連線資訊
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("❌ 錯誤：未在 GitHub Secrets 偵測到 SUPABASE_URL 或 SUPABASE_KEY。")

supabase = create_client(url, key)

def get_and_upload(tickers):
    print(f"🚀 開始將 {len(tickers)} 檔標的同步至 Supabase 數據中台...")
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            # 下載 250 天數據，完美供應 VCP 所需
            df = tk.history(period="250d")
            if df.empty:
                print(f"⚠️ {t} 無交易歷史，跳過")
                continue
            
            # 1. 寫入 K 線數據到 stock_klines
            kline_list = []
            for date_idx, row in df.iterrows():
                kline_list.append({
                    "ticker": t,
                    "date": date_idx.strftime('%Y-%m-%d'),
                    "open": float(row['Open']),
                    "high": float(row['High']),
                    "low": float(row['Low']),
                    "close": float(row['Close']),
                    "volume": int(row['Volume'])
                })
            
            if kline_list:
                supabase.table("stock_klines").upsert(kline_list).execute()

            # 2. 取得行業分類
            try:
                sector = tk.info.get('sector', 'Unknown')
            except:
                sector = 'Unknown'

            # 3. 寫入快照到 market_sctr
            snapshot_data = {
                "ticker": t,
                "price": float(df['Close'].iloc[-1]),
                "sector": sector,
                "last_update": df.index[-1].strftime('%Y-%m-%d')
            }
            
            supabase.table("market_sctr").upsert(snapshot_data).execute()
            print(f"✅ {t} 同步成功 (K 線 + 快照已更新)")
        except Exception as e:
            print(f"❌ {t} 同步失敗: {e}")

if __name__ == "__main__":
    from data_loader import get_stock_list
    
    all_tickers = []
    markets = ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"]
    
    for m in markets:
        tickers, _ = get_stock_list(m)
        if tickers:
            all_tickers.extend(tickers)
            
    all_tickers = list(set(all_tickers))
    
    # 備份降級名單（防止 data/ 文字檔尚未生成）
    if not all_tickers:
        all_tickers = ["AAPL", "MSFT", "GOOG", "0700.HK", "600519.SS"]
        print(f"⚠️ 未能獲取全局名單，切換至基本同步名單：{all_tickers}")
        
    get_and_upload(all_tickers)
