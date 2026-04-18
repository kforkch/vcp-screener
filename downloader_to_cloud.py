import os
import yfinance as yf
from supabase import create_client

# 從 GitHub Secrets 獲取連線資訊
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key)

def get_and_upload(tickers):
    # 這裡整合你之前的下載邏輯
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            df = tk.history(period="2y")
            if df.empty: continue
            
            # 計算簡單的 SCTR 或 價格 (示範)
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
    # 這裡放你的美、港、中名單
    target_list = ["AAPL", "0700.HK", "600519.SS"] 
    get_and_upload(target_list)
