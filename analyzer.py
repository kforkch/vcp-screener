# analyzer.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import time
from data_loader import get_sector_cached

# 🌟 建立全局快取變數，用於儲存批量下載的 K 線，徹底迴避 Rate Limit[cite: 3]
_GLOBAL_BULK_KLINE_CACHE = None

def calculate_sctr_ranks(tickers, lookback=20):
    """
    計算當前與 lookback 天前的 SCTR，用來衡量動能是否持續攀升[cite: 3]
    """
    global _GLOBAL_BULK_KLINE_CACHE
    try:
        # 🌟 透過 Bulk Download 一次性抓取所有股票資料[cite: 3]
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        _GLOBAL_BULK_KLINE_CACHE = raw_data
        
        data = raw_data['Close'] if 'Close' in raw_data else raw_data

        sctr_current = []
        sctr_historical = []

        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                if len(series) < 200 + lookback: continue

                # SEPA 趨勢排名核心算法：結合長中短期動能[cite: 3]
                def get_sctr_raw(sub_series):
                    sma200, sma150, sma50 = sub_series.rolling(200).mean().iloc[-1], sub_series.rolling(150).mean().iloc[-1], sub_series.rolling(50).mean().iloc[-1]
                    dist_200, dist_50 = (sub_series.iloc[-1]/sma200-1)*100, (sub_series.iloc[-1]/sma50-1)*100
                    roc125, roc20 = (sub_series.iloc[-1]/sub_series.iloc[-125]-1)*100, (sub_series.iloc[-1]/sub_series.iloc[-20]-1)*100
                    rsi = ta.rsi(sub_series, length=14).iloc[-1]
                    # 權重分配：長期趨勢(60%) + 中期動能(30%) + 短期超買/賣(10%)[cite: 3]
                    return (dist_200*0.3 + roc125*0.3) + (dist_50*0.15 + roc20*0.15) + (rsi*0.1)

                raw_curr = get_sctr_raw(series)
                raw_hist = get_sctr_raw(series.iloc[:-lookback])

                sctr_current.append({'ticker': ticker, 'raw': raw_curr})
                sctr_historical.append({'ticker': ticker, 'raw': raw_hist})
            except Exception:
                continue

        if not sctr_current: return {}, {}

        df_curr = pd.DataFrame(sctr_current)
        df_curr['rank'] = df_curr['raw'].rank(pct=True) * 99.9
        dict_curr = df_curr.set_index('ticker')['rank'].to_dict()

        df_hist = pd.DataFrame(sctr_historical)
        df_hist['rank'] = df_hist['raw'].rank(pct=True) * 99.9
        dict_hist = df_hist.set_index('ticker')['rank'].to_dict()

        return dict_curr, dict_hist
    except Exception:
        return {}, {}


def check_vcp_advanced(ticker, sctr_map, sctr_hist_map, b_only, b_days):
    """
    頂級 VCP 偵測：整合 Minervini SEPA 標準與多段波動收縮判定
    """
    global _GLOBAL_BULK_KLINE_CACHE
    try:
        df = None
        from_cache = False
        if _GLOBAL_BULK_KLINE_CACHE is not None and not _GLOBAL_BULK_KLINE_CACHE.empty:
            if isinstance(_GLOBAL_BULK_KLINE_CACHE.columns, pd.MultiIndex):
                if ticker in _GLOBAL_BULK_KLINE_CACHE.columns.get_level_values(1):
                    df = _GLOBAL_BULK_KLINE_CACHE.xs(ticker, level=1, axis=1)
                    from_cache = True
            else:
                df = _GLOBAL_BULK_KLINE_CACHE
                from_cache = True
        
        if not from_cache or df is None or df.empty:
            df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        
        df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])
        if df.empty or len(df) < 200 or df['Volume'].iloc[-1] == 0: return None

        close, high, low, vol = df['Close'], df['High'], df['Low'], df['Volume']
        curr_p = float(close.iloc[-1])
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.tail(252).min()), float(close.tail(252).max())

        # ========== 1. SEPA 趨勢模板核心標準 ==========
        cond = [
            curr_p > sma150 and curr_p > sma200,                      # 價格在 150/200 日線之上
            sma150 > sma200,                                          # 150 日線在 200 日線之上
            sma200.rolling(20).mean() > sma200.rolling(20).mean().shift(1), # 200 日線趨勢向上
            sma50 > sma150 and sma50 > sma200,                        # 50 日線在 150/200 日線之上
            curr_p > sma50,                                           # 價格在 50 日線之上
            curr_p >= low52 * 1.30,                                   # 價格較 52 週低點至少上漲 30%
            curr_p >= high52 * 0.75                                   # 價格距離 52 週高點在 25% 以內
        ]
        if sum(cond) < 7: return None

        # ========== 2. VCP 成交量枯竭 (Quiet Point)[cite: 3] ==========
        vol_ma50, vol_ma20 = vol.rolling(50).mean().iloc[-1], vol.rolling(20).mean().iloc[-1]
        # 尋找近 10 天內是否有成交量顯著低於均量的安靜點
        has_quiet_point = vol.iloc[-max(10, b_days):-1].min() < (vol_ma50 * 0.8)

        # ========== 3. 波動收縮判定 (多段收縮)[cite: 3] ==========
        def get_v(series): return (series.max() - series.min()) / series.min()
        v1 = get_v(close.iloc[-60:-40]) # 早期波動
        v2 = get_v(close.iloc[-40:-20]) # 中期波動
        v3 = get_v(close.iloc[-15:])    # 近期波動
        # 判定收縮是否遞減且近期趨於緊湊 (V3 < 10% 且 V3 < V2)[cite: 3]
        is_contracting = v3 < 0.10 and v3 <= v2 * 1.1

        # ========== 4. 緊湊度評級 (ATR 基準)[cite: 3] ==========
        atr = ta.atr(high, low, close, length=14).iloc[-1]
        w1_range = close.iloc[-5:].max() - close.iloc[-5:].min()
        
        if w1_range <= 1.2 * atr:
            contraction_status = "🎯 極度緊湊"
        elif w1_range <= 2.5 * atr:
            contraction_status = "✅ 緊湊"
        else:
            return None

        # ========== 5. SCTR 動能要求[cite: 3] ==========
        sctr_val = round(sctr_map.get(ticker, 0), 1)
        sctr_hist = round(sctr_hist_map.get(ticker, 0), 1)
        if sctr_val < 70: return None # Minervini 偏好 RS > 70 的股票

        # ========== 6. 狀態判定 (Pivot 樞軸點)[cite: 3] ==========
        resistance = float(high.iloc[-(b_days+2):-2].max())
        dist_to_pivot = (curr_p / resistance - 1) * 100
        sma20 = ta.sma(close, 20).iloc[-1]
        is_on_trend = curr_p > sma20 * 0.99

        status = ""
        if -1.5 <= dist_to_pivot <= 0.5:
            status = "⚡蓄勢待發"
        elif 0.5 < dist_to_pivot <= 5.0:
            status = "🔥 剛突破"
        elif 5.0 < dist_to_pivot <= 12.0 and (sctr_val > 90 or sctr_val > sctr_hist) and is_on_trend:
            status = "🚀 強勢續航"
        else:
            return None

        if b_only and status != "🔥 剛突破": return None
        # 必須具備安靜點或收縮型態[cite: 3]
        if not (has_quiet_point or is_contracting): return None

        # ========== 7. 風險報酬 (3R)[cite: 3, 4] ==========
        stop_loss = curr_p - (1.5 * atr)
        target_price = curr_p + (3.0 * (curr_p - stop_loss))
        vol_ratio = round(float(vol.iloc[-1]) / vol_ma20, 2)
        sector = get_sector_cached(ticker)

        return [
            ticker, round(curr_p, 2), round((1-curr_p/high52)*100, 2), sctr_val, contraction_status,
            vol_ratio, status, sector,
            round(resistance, 2), round(stop_loss, 2), round(target_price, 2)
        ]
    except Exception:
        return None
