# downloader_to_cloud.py
import os
import yfinance as yf
from supabase import create_client

# 從 GitHub Secrets 獲取連線資訊
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("❌ 錯誤：未在環境變數中偵測到 SUPABASE_URL 或 SUPABASE_KEY，請檢查 GitHub Secrets 設定。")

supabase = create_client(url, key)

def get_and_upload(tickers):
    print(f"🚀 開始同步 {len(tickers)} 檔股票數據至 Supabase 數據中台...")
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            df = tk.history(period="2y")
            if df.empty:
                print(f"⚠️ {t} 無交易數據，跳過")
                continue
            
            # 計算簡單的 SCTR 或 價格 
            data = {
                "ticker": t,
                "price": float(df['Close'].iloc[-1]),
                "sector": tk.info.get('sector', 'Unknown'),
                "last_update": df.index[-1].strftime('%Y-%m-%d')
            }
            
            # Upsert 代表：若代碼存在則更新，不存在則新增
            supabase.table("stock_warehouse").upsert(data).execute()
            print(f"✅ {t} 同步成功")
        except Exception as e:
            print(f"❌ {t} 失敗: {e}")

if __name__ == "__main__":
    from data_loader import get_stock_list
    
    # 整合你所有的市場股票名單
    all_tickers = []
    markets = ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"]
    
    for m in markets:
        tickers, _ = get_stock_list(m)
        if tickers:
            all_tickers.extend(tickers)
            
    # 去除重複股票並排序
    all_tickers = sorted(list(set(all_tickers)))
    
    # 降級防護機制：如果本地 data/hsi.txt 等檔案尚未建立完全，則自動切換至基礎預設清單，確保不空轉崩潰
    if not all_tickers:
        all_tickers = ["AAPL", "0700.HK", "600519.SS"]
        print(f"⚠️ 未獲取到任何市場股票，改為執行預設同步名單: {all_tickers}")
        
    get_and_upload(all_tickers)
