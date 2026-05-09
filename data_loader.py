# data_loader.py
import pandas as pd
import requests
import io
import yfinance as yf
import os

# ==================== 🔌 數據中台連線初始化（解決通訊問題） ====================
supabase = None
try:
    # 讀取您原有的環境變數配置（相容本地環境與 Streamlit 雲端 Secrets 自動映射）
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    # 只有在配置存在且非預設值時才初始化，避免無效連線
    if url and key and url != "你的_SUPABASE_URL" and key != "你的_SUPABASE_SERVICE_ROLE_KEY":
        from supabase import create_client
        supabase = create_client(url, key)
        print("🚀 [中台連線] 數據中台安全連接成功，已準備好進行高速 K 線檢索！")
except Exception as e:
    # 若初始化失敗，安全將變數設為 None，確保 analyzer.py 能流暢識別並降級
    print(f"⚠️ [中台連線] 初始化失敗: {e}")
    supabase = None
# ==============================================================================

# 核心安全機制：檢測當前是不是在 Streamlit 網頁端環境下執行
try:
    import streamlit as st
    is_streamlit_env = hasattr(st, "runtime") and st.runtime.exists()
except ImportError:
    is_streamlit_env = False

def safe_cache(ttl=86400):
    def decorator(func):
        if is_streamlit_env:
            try:
                return st.cache_data(ttl=ttl)(func)
            except Exception:
                return func
        return func
    return decorator

def load_tickers_from_file(filename):
    """
    從 data/ 讀取代碼。
    若檔案或目錄不存在，則自動修復並建立，防止 FileNotFoundError 導致程式崩潰。
    """
    os.makedirs("data", exist_ok=True)
    file_path = os.path.join("data", filename)
    
    # 防禦性自建：若檔案不存在，寫入預設名單
    if not os.path.exists(file_path):
        print(f"⚠️ 偵測到 {file_path} 缺失！正在自動重建預設檔案...")
        default_tickers = []
        if filename == "hsi.txt":
            default_tickers = ["0700.HK", "9988.HK", "3690.HK", "1299.HK", "0005.HK"]
        elif filename == "csi300.txt":
            default_tickers = ["600519.SS", "601318.SS", "600036.SS", "300750.SZ"]
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(default_tickers))
        except Exception as e:
            print(f"❌ 無法建立預設檔案: {e}")
            
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tickers = [line.strip() for line in f if line.strip()]
        return tickers
    except Exception as e:
        print(f"❌ 讀取 {filename} 失敗: {e}")
        return []

@safe_cache(ttl=86400)
def get_stock_list(market):
    """獲取各市場的股票清單與對應的大盤指數"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        # 美股 (S&P 500)
        if market == "美股 (S&P 500)":
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            tables = pd.read_html(io.StringIO(requests.get(url, headers=headers, timeout=15).text))
            table = tables[0]
            col = 'Symbol' if 'Symbol' in table.columns else table.columns[0]
            return table[col].str.replace('.', '-', regex=False).tolist(), "^GSPC"
        
        # 美股 (Nasdaq 100)
        elif market == "美股 (Nasdaq 100)":
            url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
            tables = pd.read_html(io.StringIO(requests.get(url, headers=headers, timeout=15).text))
            for t in tables:
                if 'Ticker' in t.columns: return t['Ticker'].tolist(), "^IXIC"
                if 'Symbol' in t.columns: return t['Symbol'].tolist(), "^IXIC"
            # 備用保底美股
            return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META"], "^IXIC"
        
        # 港股
        elif market == "港股 (恒生指數)":
            return load_tickers_from_file("hsi.txt"), "^HSI"

        # 中國 A 股
        elif market == "中國 A 股 (滬深 300 龍頭)":
            return load_tickers_from_file("csi300.txt"), "000300.SS"
            
    except Exception as e:
        msg = f"獲取市場清單失敗 ({e})，啟用保底讀取機制。"
        print(f"⚠️ {msg}")
        if market == "港股 (恒生指數)":
            return load_tickers_from_file("hsi.txt"), "^HSI"
        elif market == "中國 A 股 (滬深 300 龍頭)":
            return load_tickers_from_file("csi300.txt"), "000300.SS"
        else:
            return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"], "^IXIC"
    
    return [], ""

@safe_cache(ttl=86400)
def get_sector_cached(ticker):
    """快取個股行業分類"""
    try:
        tk = yf.Ticker(ticker)
        return tk.info.get('sector', '未知板塊')
    except Exception:
        return '未知板塊'
