# downloader_to_cloud.py
import os
import yfinance as yf

def get_supabase_client():
    """安全獲取 Supabase 用戶端，若未配置 Secrets 則優雅退出而不引發崩潰"""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    # 💡 關鍵防禦：先檢查變數是否為空！絕不傳入 None 給 create_client 避免致命崩潰
    if not url or not key or url == "" or key == "":
        print("⚠️ 警告：未在 GitHub Secrets 中設定 SUPABASE_URL 或 SUPABASE_KEY！")
        print("💡 請至 GitHub 專案設定 -> Secrets and variables -> Actions 中新增此二項配置。")
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
            
            # 準備數據
            data = {
                "ticker": t,
                "price": float(df['Close'].iloc[-1]),
                "sector": tk.info.get('sector', 'Unknown'),
                "last_update": df.index[-1].strftime('%Y-%m-%d')
            }
            
            # 若代碼存在則更新，不存在則新增
            supabase.table("stock_warehouse").upsert(data).execute()
            print(f"✅ {t} 同步成功")
        except Exception as e:
            print(f"❌ {t} 同步過程中發生非致命錯誤: {e}")

if __name__ == "__main__":
    # 嘗試引入資料庫配置中的真實股票名單
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

    # 基礎防護清單，避免名單為空
    if not target_list:
        target_list = ["AAPL", "0700.HK", "600519.SS"] 
        
    get_and_upload(target_list)
