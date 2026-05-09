# downloader_to_cloud.py
import os
import yfinance as yf
import pandas as pd

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
            
            # ==================== 1. 同步個股最新基本數據至 stock_warehouse ====================
            warehouse_data = {
                "ticker": t,
                "price": float(df['Close'].iloc[-1]),
                "sector": tk.info.get('sector', 'Unknown'),
                "last_update": df.index[-1].strftime('%Y-%m-%d')
            }
            supabase.table("stock_warehouse").upsert(warehouse_data).execute()
            
            # ==================== 2. 同步歷史時序 K 線數據至 stock_klines ====================
            # 重構 DataFrame 格式以符合 stock_klines 資料庫結構
            klines_records = []
            for date, row in df.iterrows():
                klines_records.append({
                    "ticker": t,
                    "date": date.strftime('%Y-%m-%d'),
                    "open": float(row['Open']),
                    "high": float(row['High']),
                    "low": float(row['Low']),
                    "close": float(row['Close']),
                    "volume": int(row['Volume'])
                })
            
            # 批次 Upsert 寫入 K 線表（避免多條單次寫入，大幅提升 GitHub Actions 同步效率）
            if klines_records:
                # 分批（每批 100 筆）寫入，防止單次 payload 過大
                chunk_size = 100
                for i in range(0, len(klines_records), chunk_size):
                    chunk = klines_records[i:i + chunk_size]
                    supabase.table("stock_klines").upsert(chunk).execute()
                    
            print(f"✅ {t} (基本資料 & 歷史 K 線) 同步成功")
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
