import os
import io
import pandas as pd
import requests
import yfinance as yf

# 核心安全機制：檢測當前是不是在 Streamlit 網頁環境下執行
try:
    import streamlit as st
    is_streamlit_env = True
except ImportError:
    is_streamlit_env = False

# 自訂快取裝飾器：在網頁端啟用快取提升速度，在 Actions 背景端則當作普通函數執行
def safe_cache(ttl=86400):
    def decorator(func):
        if is_streamlit_env:
            return st.cache_data(ttl=ttl)(func)
        return func
    return decorator

# 輔助函數：從 data/ 資料夾讀取 txt 檔案
def load_tickers_from_file(filename):
    file_path = os.path.join("data", filename)
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        else:
            msg = f"找不到檔案: {file_path}，將返回空名單。"
            if is_streamlit_env:
                st.warning(msg)
            else:
                print(f"⚠️ {msg}")
            return []
    except Exception as e:
        msg = f"讀取 {filename} 發生錯誤: {e}"
        if is_streamlit_env:
            st.error(msg)
        else:
            print(f"❌ {msg}")
        return []

@safe_cache(ttl=86400)
def get_stock_list(market):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        if market == "美股 (S&P 500)":
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            table = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))[0]
            return table['Symbol'].str.replace('.', '-', regex=False).tolist(), "^GSPC"
        
        elif market == "美股 (Nasdaq 100)":
            url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
            tables = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))
            for t in tables:
                if 'Ticker' in t.columns: return t['Ticker'].tolist(), "^IXIC"
                if 'Symbol' in t.columns: return t['Symbol'].tolist(), "^IXIC"
        
        elif market == "港股 (恒生指數)":
            return load_tickers_from_file("hsi.txt"), "^HSI"

        elif market == "中國 A 股 (滬深 300 龍頭)":
            return load_tickers_from_file("csi300.txt"), "000300.SS"
            
    except Exception as e:
        if is_streamlit_env:
            st.error(f"獲取市場清單失敗: {e}")
        else:
            print(f"❌ 獲取市場清單失敗: {e}")
        return [], None
    
    return [], None

# 行業分類快照快取 (優化效能，優先讀取 Supabase)
def get_sector_cached(ticker):
    # 如果 Supabase 連接成功，優先由 Supabase 查表，避免頻繁調用 yf.Ticker(t).info 導致被 Block
    try:
        # 這裡會由 supabase 連線（若有的話）
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if url and key:
            supabase = create_client(url, key)
            res = supabase.table("market_sctr").select("sector").eq("ticker", ticker).execute()
            if res.data and res.data[0].get('sector'):
                return res.data[0]['sector']
    except:
        pass

    # 備用方案：調用原 yfinance
    try:
        tk = yf.Ticker(ticker)
        return tk.info.get('sector', 'Unknown')
    except:
        return 'Unknown'
