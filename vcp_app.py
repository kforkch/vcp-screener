import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np

# --- 頁面配置 ---
st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 全球終端 (中港美優化版)")

# --- 1. 股票名單獲取 (修正港/A 股格式) ---
@st.cache_data(ttl=86400)
def get_stock_list(market):
    if market == "港股 (恒生指數)":
        # 確保代碼是 4 位數 + .HK
        hsi_list = ["0700.HK", "0005.HK", "1211.HK", "1810.HK", "3690.HK", "9988.HK", "2318.HK", "0388.HK", "1299.HK", "0941.HK"]
        return hsi_list, "^HSI"
    elif market == "中國 A 股 (龍頭)":
        # A 股必須帶有正確的交易所後綴
        as_list = ["600519.SS", "601318.SS", "300750.SZ", "000858.SZ", "600036.SS", "002594.SZ", "601012.SS"]
        return as_list, "000300.SS"
    elif market == "美股 (Nasdaq 100)":
        return ["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "META", "GOOGL"], "^IXIC"
    return [], None

# --- 2. 核心分析函數 (解決抓不到數據的問題) ---
def analyze_vcp(ticker, sctr_val, b_days):
    try:
        # 1. 抓取數據 (使用更穩定的參數)
        t_obj = yf.Ticker(ticker)
        df = t_obj.history(period="1y", auto_adjust=True)
        
        if df.empty or len(df) < 150: # 有些 A 股數據長度不一，降低門檻至 150
            return None
        
        # 2. 獲取產業 (增加備援機制)
        try:
            # yfinance 的 info 在非美股極不穩定
            sector = t_obj.info.get('sector', '其他/多元化')
        except:
            sector = "金融/權重" if ".HK" in ticker or ".SS" in ticker else "技術/其他"

        close = df['Close']
        vol = df['Volume']
        curr_p = float(close.iloc[-1])
        
        # 3. VCP 趨勢模板 (針對中港股微調：港股波動大，52週高位門檻可稍微放寬)
        sma50 = ta.sma(close, 50).iloc[-1]
        sma150 = ta.sma(close, 150).iloc[-1]
        sma200 = ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.min()), float(close.max())
        
        # 基本趨勢判斷
        cond = [
            curr_p > sma150,
            sma150 > sma200,
            curr_p > sma50,
            curr_p >= low52 * 1.2, # 離底至少 20%
            curr_p >= high52 * 0.7 # 離高點不超過 30%
        ]
        
        if all(cond):
            # 收縮 Tightness 檢測
            recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
            is_tight = "✅ 緊湊" if recent_range < 0.05 else "❌ 鬆散" # 5% 內的波動視為緊湊
            
            # 突破檢測
            recent_max = float(close.iloc[-(b_days+1):-1].max())
            is_breakout = curr_p > recent_max
            
            vol_ratio = round(float(vol.iloc[-1]) / vol.rolling(20).mean().iloc[-1], 2)
            dist_high = round((1 - curr_p/high52) * 100, 2)
            
            return [ticker, round(curr_p, 2), dist_high, sctr_val, is_tight, vol_ratio, sector]
    except Exception as e:
        return None
    return None

# --- 3. UI 介面 ---
st.sidebar.header("🎛️ 參數設置")
market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "港股 (恒生指數)", "中國 A 股 (龍頭)"])
b_days = st.sidebar.selectbox("突破天數", [10, 20, 50], index=1)

if st.sidebar.button("🚀 開始掃描"):
    tickers, bench = get_stock_list(market_name)
    if tickers:
        st.info(f"正在分析 {market_name} 數據，請稍候...")
        results = []
        pb = st.progress(0)
        
        for i, t in enumerate(tickers):
            # 這裡 SCTR 先給 80 作為演示，實務上可串接你的計算函數
            res = analyze_vcp(t, 80.0, b_days)
            if res:
                results.append(res)
            pb.progress((i + 1) / len(tickers))
        
        if results:
            df_final = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR", "收縮", "量比", "產業"])
            
            # --- 產業群聚統計 ---
            st.subheader("🔥 產業群聚分佈")
            group_counts = df_final['產業'].value_counts()
            st.bar_chart(group_counts)
            
            st.write("---")
            st.dataframe(df_final.sort_values("產業"), use_container_width=True)
        else:
            st.warning("當前市場環境下，未發現符合 VCP 形態的標的。")
