import os
import io
import pandas as pd
import requests
import yfinance as yf
from supabase import create_client

# 安全檢測：若在 Streamlit 之外環境運行，不載入 streamlit 框架
try:
    import streamlit as st
    is_streamlit = True
except ImportError:
    is_streamlit = False

# 讀取 Supabase 金鑰 (相容 Streamlit secrets 與系統環境變數)
if is_streamlit:
    SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL"))
    SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY"))
else:
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# 初始化 Supabase
supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"⚠️ Supabase 初始化失敗: {e}")

# 自訂快取代理器：在 Streamlit 使用快取，在 Actions 背景則直接執行
def safe_cache(ttl=86400):
    def decorator(func):
        if is_streamlit:
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
            msg = f"檔案不存在: {file_path}，將返回空列表。"
            if is_streamlit:
                st.warning(msg)
            else:
                print(f"⚠️ {msg}")
            return []
    except Exception as e:
        msg = f"讀取 {filename} 發生錯誤: {e}"
        if is_streamlit:
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
        if is_streamlit:
            st.error(f"獲取市場清單失敗: {e}")
        else:
            print(f"❌ 獲取市場清單失敗: {e}")
        return [], None
    
    return [], None

@safe_cache(ttl=86400)
def get_sector_cached(ticker):
    """
    [無痛代理] 優先從 Supabase 中讀取行業分類，若中台無數據才調用 yfinance
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
