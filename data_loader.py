import os
import io
import pandas as pd
import requests
import yfinance as yf

# 1. 核心安全檢測：辨識目前是處於 Streamlit 網頁端還是 GitHub Action 背景端
try:
    import streamlit as st
    is_streamlit = True
except ImportError:
    is_streamlit = False

# 2. 讀取 Supabase 金鑰 (自動相容網頁端 Secrets 與 背景端環境變數)
if is_streamlit:
    SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL"))
    SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY"))
else:
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# 3. 初始化 Supabase 用戶端
supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"⚠️ Supabase 初始化失敗: {e}")

# 4. 安全快取裝飾器：如果是網頁端就用 cache_data 提速，背景端則當成一般函數執行，防止崩潰
def safe_cache(ttl=86400):
    def decorator(func):
        if is_streamlit:
            return st.cache_data(ttl=ttl)(func)
        return func
    return decorator

# 5. 安全讀取本地 txt 檔
def load_tickers_from_file(filename):
    file_path = os.path.join("data", filename)
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        else:
            msg = f"找不到檔案: {file_path}"
            if is_streamlit:
                st.warning(msg)
            else:
                print(f"⚠️ {msg}")
            return []
    except Exception as e:
        msg = f"讀取 {filename} 失敗: {e}"
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

# 6. 行業分類快取代理 (解決 analyzer.py 的導入需求，並防止死循環)
def get_sector_cached(ticker):
    """
    優先從 Supabase 中台 (market_sctr) 獲取行業分類，若無才去請求 yfinance
    """
    if supabase:
        try:
            res = supabase.table("market_sctr").select("sector").eq("ticker", ticker).execute()
            if res.data and res.data[0].get('sector'):
                return res.data[0]['sector']
        except Exception as e:
            print(f"⚠️ 從數據中台獲取行業分類失敗 ({ticker}): {e}")
            
    try:
        ticker_obj = yf.Ticker(ticker)
        return ticker_obj.info.get('sector', 'Unknown')
    except:
        return 'Unknown'
