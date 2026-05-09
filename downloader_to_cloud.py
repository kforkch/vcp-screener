# downloader_to_cloud.py
import os
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

def get_supabase_client():
    """安全獲取 Supabase 用戶端，確保 Secrets 配置正確"""
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

def get_and_upload(tickers, full_history=False):
    """
    同步股票數據至 Supabase。
    full_history: True 同步 2 年資料 (適合初次建檔)；False 僅同步最近 7 天 (適合每日運行)
    """
    supabase = get_supabase_client()
    if not supabase:
        print("⏭️ 由於未能成功連接 Supabase，本次同步任務跳過。")
        return

    # 根據需求決定同步長度，避免每日過度寫入導致 409 衝突
    sync_period = "2y" if full_history else "7d"
    print(f"🚀 開始增量同步 ({sync_period}) {len(tickers)} 檔股票數據至數據中台...")

    for t in tickers:
        try:
            tk = yf.Ticker(t)
            df = tk.history(period=sync_period)
            if df.empty:
                continue
            
            # 取得最新一筆交易資訊
            last_row = df.iloc[-1]
            last_date = df.index[-1].strftime('%Y-%m-%d')
            
            # ==================== 1. 更新 stock_warehouse (個股現狀) ====================
            # 明確指定 on_conflict='ticker' 解決截圖中的 409 衝突問題
            warehouse_data = {
                "ticker": t,
                "price": float(last_row['Close']),
                "sector": tk.info.get('sector', 'Unknown'),
                "last_update": last_date
            }
            supabase.table("stock_warehouse").upsert(
                warehouse_data, 
                on_conflict="ticker"
            ).execute()
            
            # ==================== 2. 更新 stock_klines (歷史時序) ====================
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
            
            # 分批寫入，並指定 ticker,date 為衝突檢查基準
            if klines_records:
                chunk_size = 200
                for i in range(0, len(klines_records), chunk_size):
                    chunk = klines_records[i:i + chunk_size]
                    supabase.table("stock_klines").upsert(
                        chunk, 
                        on_conflict="ticker,date"
                    ).execute()
                    
            print(f"✅ {t} 同步完成 ({last_date})")
        except Exception as e:
            print(f"❌ {t} 同步失敗: {e}")

if __name__ == "__main__":
    target_list = []
    try:
        from data_loader import get_stock_list
        # 掃描主要市場名單
        for market in ["美股 (Nasdaq 100)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"]:
            tickers, _ = get_stock_list(market)
            if tickers:
                target_list.extend(tickers)
        target_list = sorted(list(set(target_list)))
    except Exception as e:
        print(f"⚠️ 載入清單異常: {e}")

    if not target_list:
        target_list = ["AAPL", "0700.HK", "600519.SS"] 
        
    # 預設執行增量同步，節省資源並避免衝突
    get_and_upload(target_list, full_history=False)
