import streamlit as st
import pandas as pd
import yfinance as yf
from data_loader import get_stock_list
from analyzer import calculate_sctr_ranks, check_vcp_advanced

st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 全球終極交易終端")

st.sidebar.header("🎛️ 系統參數")
market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"])
min_sctr_val = st.sidebar.slider("最低 SCTR 排名", 0.0, 99.9, 80.0)
b_days = st.sidebar.selectbox("突破檢測天數", [10, 20, 50], index=1)
only_b = st.sidebar.checkbox("僅看突破", value=False)

if st.sidebar.button("🚀 執行全球同步掃描"):
    res_tuple = get_stock_list(market_name)
    if res_tuple[0]:
        tickers, bench_code = res_tuple
        
        try:
            bench_df = yf.download(bench_code, period="1y", progress=False, auto_adjust=True)
            b_series = bench_df['Close'][bench_code] if isinstance(bench_df.columns, pd.MultiIndex) else bench_df['Close']
            b_close = float(b_series.iloc[-1])
            b_sma50 = float(b_series.rolling(50).mean().iloc[-1])
            health = "🟢 牛市環境" if b_close > b_sma50 else "🔴 熊市/調整"
            c1, c2, c3 = st.columns(3)
            c1.metric("市場狀態", health)
            c2.metric("大盤收盤", f"{b_close:.2f}")
            c3.metric("50MA 距離", f"{((b_close/b_sma50-1)*100):.2f}%")
        except: pass

        st.write("---")
        st.info(f"📊 正在計算 {market_name} 的 SCTR 排名與 VCP 形態...")
        sctr_ranks = calculate_sctr_ranks(tickers)
        
        results = []
        pb = st.progress(0)
        for i, t in enumerate(tickers):
            res = check_vcp_advanced(t, sctr_ranks, only_b, b_days)
            if res and res[3] >= min_sctr_val: results.append(res)
            pb.progress((i + 1) / len(tickers))

        if results:
            # 更新 DataFrame 欄位，加入「行業」
            df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "狀態", "行業"])
            
            def make_link(t):
                t_str = str(t)
                if ".HK" in t_str:
                    code = t_str.replace('.HK', '').lstrip('0')
                    return f"https://www.tradingview.com/chart/?symbol=HKEX:{code}"
                elif ".SS" in t_str or ".SZ" in t_str:
                    code = t_str.split('.')[0]
                    prefix = "SSE" if ".SS" in t_str else "SZSE"
                    return f"https://www.tradingview.com/chart/?symbol={prefix}:{code}"
                else:
                    return f"https://www.tradingview.com/chart/?symbol={t_str.replace('.', '-')}"
            
            df['圖表'] = df['代碼'].apply(make_link)
            df_sorted = df.sort_values("SCTR排名", ascending=False)
            st.dataframe(
                df_sorted, 
                column_config={"圖表": st.column_config.LinkColumn("查看", display_text="Open")}, 
                use_container_width=True,
                hide_index=True
            )
            st.success(f"掃描完成！在 {len(tickers)} 隻股票中找到 {len(df)} 隻符合條件。")
