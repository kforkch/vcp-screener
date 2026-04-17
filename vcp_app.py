import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta

# --- 頁面配置 ---
st.set_page_config(page_title="J Law VCP Ultimate Screener", layout="wide")
st.title("🏹 J Law 跨市場自動篩選系統 (美股/港股)")

# --- 1. 自動獲取成份股函數 (加入 S&P 500) ---
@st.cache_data(ttl=86400) # 每天自動更新名單
def get_stock_list(market):
    try:
        if market == "美股 (S&P 500)":
            # 從 Wikipedia 抓取標普 500 名單
            table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')[0]
            return table['Symbol'].tolist()
        elif market == "美股 (Nasdaq 100)":
            # 從 Wikipedia 抓取納指 100 名單
            table = pd.read_html('https://en.wikipedia.org/wiki/Nasdaq-100')[4]
            return table['Symbol'].tolist()
        elif market == "港股 (恒生指數)":
            # 港股核心藍籌
            return ["0700.HK", "9988.HK", "3690.HK", "1211.HK", "1810.HK", "2318.HK", "0005.HK", "0388.HK", "9618.HK", "2269.HK"]
    except Exception as e:
        st.error(f"獲取名單失敗: {e}")
        return []
    return []

# --- 2. 核心篩選邏輯 (VCP Trend Template) ---
def check_vcp_trend(ticker):
    try:
        # yfinance 抓取數據 (修正符號：S&P 500 裡有些符號帶點，如 BRK.B 需轉成 BRK-B)
        formatted_ticker = ticker.replace('.', '-')
        df = yf.download(formatted_ticker, period="1y", progress=False)
        
        if len(df) < 200: return None
        
        curr_price = float(df['Close'].iloc[-1])
        sma50 = ta.sma(df['Close'], 50).iloc[-1]
        sma150 = ta.sma(df['Close'], 150).iloc[-1]
        sma200 = ta.sma(df['Close'], 200).iloc[-1]
        low52 = df['Close'].min()
        high52 = df['Close'].max()

        # J Law / Minervini 篩選條件
        c1 = curr_price > sma150 and curr_price > sma200
        c2 = sma150 > sma200
        c3 = sma50 > sma150 and sma50 > sma200
        c4 = curr_price > sma50
        c5 = curr_price >= (low52 * 1.25)
        c6 = curr_price >= (high52 * 0.75)

        if all([c1, c2, c3, c4, c5, c6]):
            dist_high = (1 - curr_price/high52) * 100
            return [ticker, round(curr_price, 2), f"{round(float(dist_high), 2)}%"]
    except:
        return None
    return None

# --- 3. 側邊欄控制與執行 ---
st.sidebar.header("篩選參數")
market_choice = st.sidebar.selectbox("選擇市場範疇", ["美股 (S&P 500)", "美股 (Nasdaq 100)", "港股 (恒生指數)", "手動輸入"])

if market_choice == "手動輸入":
    tickers = st.sidebar.text_input("輸入代碼 (逗號隔開)", "NVDA,PLTR").split(",")
else:
    tickers = get_stock_list(market_choice)

if st.sidebar.button("🚀 開始全自動掃描"):
    st.subheader(f"📊 {market_choice} 篩選結果 (共計 {len(tickers)} 隻股票)")
    results = []
    
    # 建立進度條與顯示文字
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 執行循環篩選
    for i, t in enumerate(tickers):
        status_text.text(f"正在分析第 {i+1}/{len(tickers)} 隻: {t}")
        res = check_vcp_trend(t)
        if res:
            results.append(res)
        progress_bar.progress((i + 1) / len(tickers))
    
    status_text.text("掃描完成！")
    
    if results:
        df_final = pd.DataFrame(results, columns=["代碼", "現價", "距離 52 週高點 %"])
        # 生成 TradingView 連結
        df_final['查看圖表'] = df_final['代碼'].apply(lambda x: f"https://www.tradingview.com/chart/?symbol={x.replace('.HK', '').replace('.', '-')}")
        
        st.dataframe(
            df_final, 
            column_config={"查看圖表": st.column_config.Link_Column("點擊打開 TradingView")},
            use_container_width=True
        )
        st.success(f"篩選完畢！在 {len(tickers)} 隻股票中找到了 {len(results)} 隻符合趨勢的強勢股。")
        st.balloons()
    else:
        st.warning("目前沒有股票符合『第二階段』趨勢模板條件。")

# --- 底部提示 ---
st.divider()
st.caption("註：S&P 500 掃描可能需要 2-3 分鐘，請耐心等候進度條完成。")
