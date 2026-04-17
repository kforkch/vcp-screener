import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io

# --- 頁面配置 ---
st.set_page_config(page_title="VCP Ultimate Screener", layout="wide")
st.title("🏹 跨市場自動篩選系統 (美股/港股)")

# --- 1. 自動獲取成份股函數 ---
@st.cache_data(ttl=86400)
def get_stock_list(market):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        if market == "美股 (S&P 500)":
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            response = requests.get(url, headers=headers)
            table = pd.read_html(io.StringIO(response.text))[0]
            # yfinance 港股用點，美股用橫線
            return table['Symbol'].str.replace('.', '-', regex=False).tolist()
            
        elif market == "美股 (Nasdaq 100)":
            url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
            response = requests.get(url, headers=headers)
            tables = pd.read_html(io.StringIO(response.text))
            for t in tables:
                if 'Ticker' in t.columns: return t['Ticker'].tolist()
                if 'Symbol' in t.columns: return t['Symbol'].tolist()
            return ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA"]
            
        elif market == "港股 (恒生指數)":
            # 港股手動精選或可擴充
            return ["0700.HK", "9988.HK", "3690.HK", "1211.HK", "1810.HK", "2318.HK", "0005.HK", "0388.HK", "9618.HK", "2269.HK"]
            
    except Exception as e:
        st.error(f"獲取名單失敗: {e}")
        return []
    return []

# --- 2. 核心篩選邏輯 (VCP Trend Template) ---
def check_vcp_trend(ticker):
    try:
        # 港股數據下載需保持 0700.HK 格式
        formatted_ticker = ticker if ".HK" in ticker else ticker.replace('.', '-')
        
        df = yf.download(formatted_ticker, period="1y", progress=False, auto_adjust=True, threads=False)
        
        if df.empty or len(df) < 100:
            return None
        
        # 處理 MultiIndex 欄位問題
        if isinstance(df.columns, pd.MultiIndex):
            close_prices = df['Close'][formatted_ticker]
        else:
            close_prices = df['Close']

        close_prices = close_prices.astype(float)
        curr_price = float(close_prices.iloc[-1])

        # 計算均線
        sma50 = ta.sma(close_prices, 50)
        sma150 = ta.sma(close_prices, 150)
        sma200 = ta.sma(close_prices, 200)

        if sma50 is None or sma150 is None or sma200 is None: return None
        
        s50, s150, s200 = sma50.iloc[-1], sma150.iloc[-1], sma200.iloc[-1]
        if pd.isna(s50) or pd.isna(s150) or pd.isna(s200): return None

        low52 = float(close_prices.min())
        high52 = float(close_prices.max())

        # Mark Minervini 6 大硬性條件
        conditions = [
            curr_price > s150 and curr_price > s200,    # 價格在 150 & 200 均線上
            s150 > s200,                               # 150 均線在 200 均線上
            s50 > s150 and s50 > s200,                 # 50 均線在 150 & 200 均線上
            curr_price > s50,                          # 價格在 50 均線上
            curr_price >= (low52 * 1.25),              # 價格高於 52 週低點 25%
            curr_price >= (high52 * 0.75)              # 價格處於 52 週高點 25% 以內
        ]
        
        score = sum(conditions)
        dist_high = round((1 - curr_price/high52) * 100, 2)
        
        # 只回傳 6/6 滿分的強勢股
        if score == 6:
            return [ticker, round(curr_price, 2), dist_high, f"{score}/6", "🚀 強勢領頭羊"]
        return None

    except Exception:
        return None

# --- 3. 側邊欄控制 ---
st.sidebar.header("篩選參數")
market_choice = st.sidebar.selectbox("選擇市場範疇", ["美股 (S&P 500)", "美股 (Nasdaq 100)", "港股 (恒生指數)", "手動輸入"])

if market_choice == "手動輸入":
    tickers_input = st.sidebar.text_input("輸入代碼 (逗號隔開)", "NVDA,PLTR,0700.HK")
    tickers = [t.strip() for t in tickers_input.split(",")]
else:
    tickers = get_stock_list(market_choice)

# --- 4. 執行掃描 ---
if st.sidebar.button("🚀 開始全自動掃描"):
    st.subheader(f"📊 {market_choice} 篩選結果 (共計 {len(tickers)} 隻股票)")
    results = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, t in enumerate(tickers):
        status_text.text(f"正在分析第 {i+1}/{len(tickers)} 隻: {t}")
        res = check_vcp_trend(t)
        if res:
            results.append(res)
        progress_bar.progress((i + 1) / len(tickers))
    
    status_text.text("掃描完成！")
    
    if results:
        # 建立 DataFrame
        df_final = pd.DataFrame(results, columns=["代碼", "現價", "距離高點數值", "評分", "狀態"])
        
        # 排序：評分高在前，距離高點近（數值小）在前
        df_final = df_final.sort_values(by=["評分", "距離高點數值"], ascending=[False, True])
        
        # 顯示格式化
        df_final["距離 52 週高點 %"] = df_final["距離高點數值"].apply(lambda x: f"{x}%")
        
        # 根據用戶確認的 HKEX:%3A (即 HKEX:) 格式生成連結
        def get_tv_url(ticker):
            if ".HK" in ticker:
                # 港股格式：HKEX:700 (移除開頭的0)
                code = ticker.replace('.HK', '').lstrip('0')
                return f"https://www.tradingview.com/chart/?symbol=HKEX:{code}"
            else:
                # 美股格式：BRK-B
                return f"https://www.tradingview.com/chart/?symbol={ticker.replace('.', '-')}"

        df_final['查看圖表'] = df_final['代碼'].apply(get_tv_url)
        
        # UI 呈現
        display_cols = ["代碼", "現價", "距離 52 週高點 %", "評分", "狀態", "查看圖表"]
        st.dataframe(
            df_final[display_cols], 
            column_config={
                "查看圖表": st.column_config.LinkColumn("點擊打開 TradingView", display_text="Open Chart")
            },
            use_container_width=True
        )
        st.success(f"篩選完畢！找到了 {len(results)} 隻完全符合 6/6 趨勢模板的強勢股。")
        st.balloons()
    else:
        st.warning("⚠️ 目前沒有股票完全符合『 6/6 滿分』趨勢模板條件。這可能代表市場環境正在轉弱或進行整理。")

# --- 底部提示 ---
st.divider()
st.caption("註：S&P 500 掃描需時較久。港股連結採用 HKEX 交易所格式跳轉。")
