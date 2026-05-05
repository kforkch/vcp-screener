# analyzer.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from data_loader import get_sector_cached


def calculate_sctr_ranks(tickers, lookback=20):
    """
    計算當前與 lookback 天前的 SCTR，用來衡量動能是否持續攀升
    """
    try:
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        data = raw_data['Close'] if isinstance(raw_data, pd.DataFrame) and 'Close' in raw_data.columns else raw_data

        sctr_current = []
        sctr_historical = []

        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                if len(series) < 200 + lookback:
                    continue

                def get_sctr_raw(sub_series):
                    sma200 = sub_series.rolling(200).mean().iloc[-1]
                    sma50 = sub_series.rolling(50).mean().iloc[-1]
                    dist_200 = (sub_series.iloc[-1] / sma200 - 1) * 100
                    dist_50 = (sub_series.iloc[-1] / sma50 - 1) * 100
                    roc125 = (sub_series.iloc[-1] / sub_series.iloc[-125] - 1) * 100
                    roc20 = (sub_series.iloc[-1] / sub_series.iloc[-20] - 1) * 100
                    rsi = ta.rsi(sub_series, length=14).iloc[-1]
                    return (dist_200 * 0.3 + roc125 * 0.3) + (dist_50 * 0.15 + roc20 * 0.15) + (rsi * 0.1)

                raw_curr = get_sctr_raw(series)
                raw_hist = get_sctr_raw(series.iloc[:-lookback])

                sctr_current.append({'ticker': ticker, 'raw': raw_curr})
                sctr_historical.append({'ticker': ticker, 'raw': raw_hist})
            except:
                continue

        if not sctr_current:
            return {}, {}

        df_curr = pd.DataFrame(sctr_current)
        df_curr['rank'] = df_curr['raw'].rank(pct=True) * 99.9
        dict_curr = df_curr.set_index('ticker')['rank'].to_dict()

        df_hist = pd.DataFrame(sctr_historical)
        df_hist['rank'] = df_hist['raw'].rank(pct=True) * 99.9
        dict_hist = df_hist.set_index('ticker')['rank'].to_dict()

        return dict_curr, dict_hist
    except:
        return {}, {}


def check_vcp_advanced(ticker, sctr_map, sctr_hist_map, b_only, b_days,
                       min_tightening=2, atr_ratio_threshold=0.78, roll_window=20):
    """
    進階 VCP 掃描器 - 滾動區間 + ATR 動態門檻
    """
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200:
            return None

        # 處理 MultiIndex
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        high = df['High'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['High']
        low = df['Low'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Low']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']

        curr_p = float(close.iloc[-1])

        # 1. Trend Template
        sma50 = ta.sma(close, length=50).iloc[-1]
        sma150 = ta.sma(close, length=150).iloc[-1]
        sma200 = ta.sma(close, length=200).iloc[-1]
        low52 = float(close.min())
        high52 = float(close.max())

        cond = [
            curr_p > sma150 and curr_p > sma200,
            sma150 > sma200,
            sma50 > sma150 and sma50 > sma200,
            curr_p > sma50,
            curr_p >= (low52 * 1.25),
            curr_p >= (high52 * 0.75)
        ]
        if sum(cond) < 6:
            return None

        # 2. ATR 動態緊密度
        atr14 = ta.atr(high=high, low=low, close=close, length=14)
        df['ATR14'] = atr14
        df['ATR_ratio'] = atr14 / close
        
        recent_atr = df['ATR_ratio'].tail(10).mean()
        hist_atr = df['ATR_ratio'].tail(60).mean()
        
        if recent_atr > hist_atr * atr_ratio_threshold:
            return None

        # 3. 滾動區間收縮檢測
        df['roll_range'] = (high.rolling(window=roll_window, min_periods=10).max() - 
                           low.rolling(window=roll_window, min_periods=10).min())
        
        roll_ranges = df['roll_range'].dropna().tail(7).values

        tightening_count = 0
        for i in range(1, len(roll_ranges)):
            if roll_ranges[i] < roll_ranges[i-1] * 0.90:
                tightening_count += 1

        if tightening_count < min_tightening:
            return None

        # 4. 最近極窄確認
        recent_range = (close.iloc[-7:].max() - close.iloc[-7:].min()) / close.iloc[-7:].min()
        is_tight = "✅ 極緊" if recent_range < 0.06 else "⚠️ 尚可"

        # 5. 成交量
        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        vol_ratio = float(vol.iloc[-1]) / vol_ma20 if vol_ma20 > 0 else 1.0
        if vol_ratio > 1.3:
            return None

        # 6. SCTR
        sctr_val = round(sctr_map.get(ticker, 0), 1)
        sctr_hist = round(sctr_hist_map.get(ticker, 0), 1)
        if sctr_val < 80.0 or sctr_val <= sctr_hist:
            return None

        # 7. 突破檢測
        recent_max = float(close.iloc[-(b_days + 1):-1].max())
        is_breakout = curr_p > recent_max
        if b_only and not is_breakout:
            return None

        status = f"🔥 {b_days}D突破" if is_breakout else "🚀 強勢向上"

        # 8. 風險報酬
        atr_val = float(atr14.iloc[-1]) if not pd.isna(atr14.iloc[-1]) else (high.iloc[-1] - low.iloc[-1])
        pivot_point = recent_max
        stop_loss = curr_p - (1.5 * atr_val)
        target_price = curr_p + (3.0 * (curr_p - stop_loss))

        dist_high = round((1 - curr_p / high52) * 100, 2)
        sector = get_sector_cached(ticker)

        return [
            ticker, round(curr_p, 2), dist_high, sctr_val, is_tight,
            round(vol_ratio, 2), status, sector,
            round(pivot_point, 2), round(stop_loss, 2), round(target_price, 2)
        ]

    except Exception:
        return None
