# data_loader.py
import streamlit as st
import pandas as pd
import requests
import io
import os
from supabase import create_client

# 初始化 Supabase 用戶端
SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", "請填入你的_SUPABASE_URL"))
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", "請填入你的_SUPABASE_KEY"))
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 輔助函數：從 data/ 資料夾讀取 txt 檔案
def load_tickers_from_file(filename):
    file_path = os.path.join("data", filename)
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        else:
            st.error(f"檔案不存在: {file_path}")
            return []
    except Exception as e:
        st.error(f"讀取 {filename} 時發生錯誤: {e}")
        return []

@st.cache_data(ttl=86400)
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
            return load_tickers_from_file("csi300.txt"), "^000300.SS"
    except Exception as e:
        st.error(f"讀取名單錯誤: {e}")
        return [], ""

# ==================== Supabase 中台解耦底層 ====================

@st.cache_data(ttl=1800)
def calculate_sctr_ranks(tickers, lookback=20):
    """
    [代理優化] 覆蓋原 yfinance 計算方法。
    直接從 Supabase 中台拉取所有 ticker 的 Raw Score，在記憶體做快速排名並返回，保持與原函數的簽名格式一致。
    """
    try:
        response = supabase.table("market_sctr").select("ticker, sctr_current, sctr_historical").in_("ticker", tickers).execute()
        data = response.data
        if not data:
            return {}, {}

        df = pd.DataFrame(data)
        
        # 記憶體內極速做 Rank 計算 (0-100分)
        df['rank_curr'] = df['sctr_current'].rank(pct=True) * 99.9
        df['rank_hist'] = df['sctr_historical'].rank(pct=True) * 99.9

        dict_curr = df.set_index('ticker')['rank_curr'].to_dict()
        dict_hist = df.set_index('ticker')['rank_hist'].to_dict()

        return dict_curr, dict_hist
    except Exception as e:
        print(f"從 Supabase 獲取 SCTR 失敗: {e}")
        return {}, {}

@st.cache_data(ttl=86400)
def get_sector_cached(ticker):
    """
    [代理優化] 快速獲取板塊分類，減少本地硬碟 I/O。
    """
    try:
        response = supabase.table("market_sctr").select("sector").eq("ticker", ticker).execute()
        if response.data:
            return response.data[0]['sector']
    except:
        pass
    return "Unknown"
