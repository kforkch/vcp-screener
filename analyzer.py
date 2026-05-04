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
        data = raw_data['Close'] if 'Close' in raw_data else raw_data

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


def check_vcp_advanced(ticker, sctr_map, sctr_hist_map, b_only, b_days):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200:
            return None

        # 處理單一股票與多股票下載的欄位差異
        close = df['Close'] if 'Close' in df.columns else df['Close'][ticker]
        high = df['High'] if 'High' in df.columns else df['High'][ticker]
        low = df['Low'] if 'Low' in df.columns else df['Low'][ticker]
        vol = df['Volume'] if 'Volume' in df.columns else df['Volume'][ticker]

        curr_p = float(close.iloc[-1])

        # 趨勢模板（保留高品質過濾）
        sma50 = ta.sma(close, 50).iloc[-1]
        sma150 = ta.sma(close, 150).iloc[-1]
        sma200 = ta.sma(close, 200).iloc[-1]
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

        # ====================== 新版 VCP 核心：Pivot-based 多段收縮 ======================
        atr = ta.atr(high, low, close, length=14)
        atr_ma30 = atr.rolling(30).mean()

        # 使用 pivot 找出 Swing High
        pivot_high = ta.pivothigh(high, low, left=5, right=5)

        # 收集最近的 contraction legs（收縮段）
        legs = []
        for i in range(len(df) - 120, len(df) - 8):   # 過去約半年
            if pd.notna(pivot_high.iloc[i]):
                swing_high = float(high.iloc[i])
                # 找後續的 pivot low
                for j in range(i + 3, min(i + 40, len(df) - 1)):
                    if pd.notna(ta.pivotlow(high, low, left=5, right=5).iloc[j]):
                        leg_range = (swing_high - float(low.iloc[j])) / float(low.iloc[j])
                        legs.append(leg_range)
                        break
                if len(legs) >= 6:
                    break

        if len(legs) < 2:
            return None

        # 判斷是否逐漸收縮（後段比前段窄）
        is_contracting = all(legs[i] > legs[i + 1] * 0.78 for i in range(len(legs) - 1))
        latest_contraction = legs[-1]
        recent_atr_ratio = float(atr.iloc[-1] / atr_ma30.iloc[-1]) if not atr_ma30.isna().iloc[-1] else 1.0

        # 美股 5-10 檔門檻（已調鬆）
        if not (is_contracting and 
                latest_contraction < 0.145 and      # 最後一段收縮 <14.5%
                recent_atr_ratio < 0.88 and         # ATR 動態收縮
                len(legs) >= 2):
            return None

        # 最近5天緊湊度
        recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
        is_tight = "✅ 緊湊" if recent_range < 0.075 else "⚠️ 一般"

        # 成交量檢查（適度放鬆）
        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        if vol.iloc[-1] > vol_ma20 * 1.35:
            return None

        # SCTR（降至75以增加訊號）
        sctr_val = round(sctr_map.get(ticker, 0), 1)
        sctr_hist = round(sctr_hist_map.get(ticker, 0), 1)
        if sctr_val < 75.0 or sctr_val <= sctr_hist:
            return None

        # 突破檢測
        recent_max = float(close.iloc[-(b_days + 1):-1].max())
        is_breakout = curr_p > recent_max
        if b_only and not is_breakout:
            return None

        status = f"🔥 {b_days}D突破" if is_breakout else f"🚀 強勢向上 (VCP{len(legs)}段)"

        # 風險報酬計算
        atr_val = float(atr.iloc[-1]) if not atr.isna().iloc[-1] else (float(high.iloc[-1]) - float(low.iloc[-1]))
        pivot_point = recent_max
        stop_loss = curr_p - (1.5 * atr_val)
        target_price = curr_p + (3.0 * (curr_p - stop_loss))

        dist_high = round((1 - curr_p / high52) * 100, 2)
        vol_ratio = round(float(vol.iloc[-1]) / vol_ma20, 2)
        sector = get_sector_cached(ticker)

        return [
            ticker, round(curr_p, 2), dist_high, sctr_val, 
            is_tight, vol_ratio, status, sector,
            round(pivot_point, 2), round(stop_loss, 2), round(target_price, 2)
        ]
    except Exception as e:
        # print(f"Error processing {ticker}: {e}")  # debug 用
        return None
