{\rtf1\ansi\ansicpg950\cocoartf2761
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\paperw11900\paperh16840\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 import streamlit as st\
import yfinance as yf\
import pandas as pd\
import pandas_ta as ta\
\
# --- \uc0\u38913 \u38754 \u37197 \u32622  ---\
st.set_page_config(page_title="J Law VCP Ultimate Screener", layout="wide")\
st.title("\uc0\u55356 \u57337  J Law \u36328 \u24066 \u22580 \u33258 \u21205 \u31721 \u36984 \u31995 \u32113  (\u32654 \u32929 /\u28207 \u32929 )")\
\
# --- 1. \uc0\u33258 \u21205 \u29554 \u21462 \u25104 \u20221 \u32929 \u20989 \u25976  (\u21152 \u20837  S&P 500) ---\
@st.cache_data(ttl=86400) # \uc0\u27599 \u22825 \u33258 \u21205 \u26356 \u26032 \u21517 \u21934 \
def get_stock_list(market):\
    try:\
        if market == "\uc0\u32654 \u32929  (S&P 500)":\
            # \uc0\u24478  Wikipedia \u25235 \u21462 \u27161 \u26222  500 \u21517 \u21934 \
            table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')[0]\
            return table['Symbol'].tolist()\
        elif market == "\uc0\u32654 \u32929  (Nasdaq 100)":\
            # \uc0\u24478  Wikipedia \u25235 \u21462 \u32013 \u25351  100 \u21517 \u21934 \
            table = pd.read_html('https://en.wikipedia.org/wiki/Nasdaq-100')[4]\
            return table['Symbol'].tolist()\
        elif market == "\uc0\u28207 \u32929  (\u24658 \u29983 \u25351 \u25976 )":\
            # \uc0\u28207 \u32929 \u26680 \u24515 \u34253 \u31820 \
            return ["0700.HK", "9988.HK", "3690.HK", "1211.HK", "1810.HK", "2318.HK", "0005.HK", "0388.HK", "9618.HK", "2269.HK"]\
    except Exception as e:\
        st.error(f"\uc0\u29554 \u21462 \u21517 \u21934 \u22833 \u25943 : \{e\}")\
        return []\
    return []\
\
# --- 2. \uc0\u26680 \u24515 \u31721 \u36984 \u37007 \u36655  (VCP Trend Template) ---\
def check_vcp_trend(ticker):\
    try:\
        # yfinance \uc0\u25235 \u21462 \u25976 \u25818  (\u20462 \u27491 \u31526 \u34399 \u65306 S&P 500 \u35041 \u26377 \u20123 \u31526 \u34399 \u24118 \u40670 \u65292 \u22914  BRK.B \u38656 \u36681 \u25104  BRK-B)\
        formatted_ticker = ticker.replace('.', '-')\
        df = yf.download(formatted_ticker, period="1y", progress=False)\
        \
        if len(df) < 200: return None\
        \
        curr_price = float(df['Close'].iloc[-1])\
        sma50 = ta.sma(df['Close'], 50).iloc[-1]\
        sma150 = ta.sma(df['Close'], 150).iloc[-1]\
        sma200 = ta.sma(df['Close'], 200).iloc[-1]\
        low52 = df['Close'].min()\
        high52 = df['Close'].max()\
\
        # J Law / Minervini \uc0\u31721 \u36984 \u26781 \u20214 \
        c1 = curr_price > sma150 and curr_price > sma200\
        c2 = sma150 > sma200\
        c3 = sma50 > sma150 and sma50 > sma200\
        c4 = curr_price > sma50\
        c5 = curr_price >= (low52 * 1.25)\
        c6 = curr_price >= (high52 * 0.75)\
\
        if all([c1, c2, c3, c4, c5, c6]):\
            dist_high = (1 - curr_price/high52) * 100\
            return [ticker, round(curr_price, 2), f"\{round(float(dist_high), 2)\}%"]\
    except:\
        return None\
    return None\
\
# --- 3. \uc0\u20596 \u37002 \u27396 \u25511 \u21046 \u33287 \u22519 \u34892  ---\
st.sidebar.header("\uc0\u31721 \u36984 \u21443 \u25976 ")\
market_choice = st.sidebar.selectbox("\uc0\u36984 \u25799 \u24066 \u22580 \u31684 \u30087 ", ["\u32654 \u32929  (S&P 500)", "\u32654 \u32929  (Nasdaq 100)", "\u28207 \u32929  (\u24658 \u29983 \u25351 \u25976 )", "\u25163 \u21205 \u36664 \u20837 "])\
\
if market_choice == "\uc0\u25163 \u21205 \u36664 \u20837 ":\
    tickers = st.sidebar.text_input("\uc0\u36664 \u20837 \u20195 \u30908  (\u36887 \u34399 \u38548 \u38283 )", "NVDA,PLTR").split(",")\
else:\
    tickers = get_stock_list(market_choice)\
\
if st.sidebar.button("\uc0\u55357 \u56960  \u38283 \u22987 \u20840 \u33258 \u21205 \u25475 \u25551 "):\
    st.subheader(f"\uc0\u55357 \u56522  \{market_choice\} \u31721 \u36984 \u32080 \u26524  (\u20849 \u35336  \{len(tickers)\} \u38587 \u32929 \u31080 )")\
    results = []\
    \
    # \uc0\u24314 \u31435 \u36914 \u24230 \u26781 \u33287 \u39023 \u31034 \u25991 \u23383 \
    progress_bar = st.progress(0)\
    status_text = st.empty()\
    \
    # \uc0\u22519 \u34892 \u24490 \u29872 \u31721 \u36984 \
    for i, t in enumerate(tickers):\
        status_text.text(f"\uc0\u27491 \u22312 \u20998 \u26512 \u31532  \{i+1\}/\{len(tickers)\} \u38587 : \{t\}")\
        res = check_vcp_trend(t)\
        if res:\
            results.append(res)\
        progress_bar.progress((i + 1) / len(tickers))\
    \
    status_text.text("\uc0\u25475 \u25551 \u23436 \u25104 \u65281 ")\
    \
    if results:\
        df_final = pd.DataFrame(results, columns=["\uc0\u20195 \u30908 ", "\u29694 \u20729 ", "\u36317 \u38626  52 \u36913 \u39640 \u40670  %"])\
        # \uc0\u29983 \u25104  TradingView \u36899 \u32080 \
        df_final['\uc0\u26597 \u30475 \u22294 \u34920 '] = df_final['\u20195 \u30908 '].apply(lambda x: f"https://www.tradingview.com/chart/?symbol=\{x.replace('.HK', '').replace('.', '-')\}")\
        \
        st.dataframe(\
            df_final, \
            column_config=\{"\uc0\u26597 \u30475 \u22294 \u34920 ": st.column_config.Link_Column("\u40670 \u25802 \u25171 \u38283  TradingView")\},\
            use_container_width=True\
        )\
        st.success(f"\uc0\u31721 \u36984 \u23436 \u30050 \u65281 \u22312  \{len(tickers)\} \u38587 \u32929 \u31080 \u20013 \u25214 \u21040 \u20102  \{len(results)\} \u38587 \u31526 \u21512 \u36264 \u21218 \u30340 \u24375 \u21218 \u32929 \u12290 ")\
        st.balloons()\
    else:\
        st.warning("\uc0\u30446 \u21069 \u27794 \u26377 \u32929 \u31080 \u31526 \u21512 \u12302 \u31532 \u20108 \u38542 \u27573 \u12303 \u36264 \u21218 \u27169 \u26495 \u26781 \u20214 \u12290 ")\
\
# --- \uc0\u24213 \u37096 \u25552 \u31034  ---\
st.divider()\
st.caption("\uc0\u35387 \u65306 S&P 500 \u25475 \u25551 \u21487 \u33021 \u38656 \u35201  2-3 \u20998 \u37912 \u65292 \u35531 \u32784 \u24515 \u31561 \u20505 \u36914 \u24230 \u26781 \u23436 \u25104 \u12290 ")}