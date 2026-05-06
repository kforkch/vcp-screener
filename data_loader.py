import os
import io
import pandas as pd
import requests
import yfinance as yf
from supabase import create_client

# 核心安全機制：檢測當前是不是在 Streamlit 網頁環境下執行
try:
    import streamlit as st
    is_streamlit_env = True
except ImportError:
    is_streamlit_env = False

# 安全讀取金鑰 (相容 Streamlit Secrets 與 GitHub 系統環境變數)
if is_streamlit_env:
    SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL"))
    SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY"))
else:
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# 初始化 Supabase 用戶端
supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"⚠️ Supabase 連線失敗: {e}")

# 自訂快取裝飾器：在網頁端啟用快取提升速度，在 Actions 背景端則當作普通函數執行
def safe_cache(ttl=86400):
    def decorator(func):
        if is_streamlit_env:
            return st.cache_data(ttl=ttl)(func)
        return func
    return decorator

def load_tickers_from_file(filename):
    """安全讀取本地 text 檔案，若檔案不存在不崩潰"""
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
        msg = f"讀取 {filename} 失敗: {e}"
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

@safe_cache(ttl=86400)
def get_sector_cached(ticker):
    """
    [快取代理] 優先從 Supabase 中台讀取行業分類，減少 yfinance info 的請求負擔
    """
    if supabase:
        try:
            res = supabase.table("market_sctr").select("sector").eq("ticker", ticker).execute()
            if res.data and res.data[0].get('sector'):
                return res.data[0]['sector']
        except Exception as e:
            print(f"⚠️ 從中台讀取行業失敗 ({ticker}): {e}")
            
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info
        return info.get('sector', 'N/A')
    except:
        return 'N/A'
