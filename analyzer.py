# analyzer.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from data_loader import get_sector_cached

# ... (calculate_sctr_ranks 函式保持不變) ...

def check_vcp_strict(ticker, sctr_map, sctr_hist_map, b_only, b_days):
    """嚴苛版 - 適合牛市，好市場用"""
    return _check_vcp_base(ticker, sctr_map, sctr_hist_map, b_only, b_days, mode='strict')

def check_vcp_loose(ticker, sctr_map, sctr_hist_map, b_only, b_days):
    """寬鬆版 - 適合調整市或想抓早期 Stage 2，用來建立觀察名單"""
    return _check_vcp_base(ticker, sctr_map, sctr_hist_map, b_only, b_days, mode='loose')

def _check_vcp_base(ticker, sctr_map, sctr_hist_map, b_only, b_days, mode='strict'):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: 
            return None
        
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        high = df['High'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['High']
        low = df['Low'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Low']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        
        curr_p = float(close.iloc[-1])
        sma50 = ta.sma(close, 50).iloc[-1]
        sma150 = ta.sma(close, 150).iloc[-1]
        sma200 = ta.sma(close, 200).iloc[-1]
        low52 = float(close.min())
        high52 = float(close.max())
        
        # ==================== 趨勢模板 ====================
        if mode == 'strict':
            cond = [
                curr_p > sma150 and curr_p > sma200,
                sma150 > sma200,                    # 嚴苛要求
                sma50 > sma150 and sma50 > sma200,  # 嚴苛要求
                curr_p > sma50,
                curr_p >= (low52 * 1.30),           # 你指定的 30%
                curr_p >= (high52 * 0.75)
            ]
            if sum(cond) < 6: 
                return None
        else:  # loose
            cond = [
                curr_p > sma200,                    # 核心：高於 200 日均線
                curr_p > sma50,                     # 放寬，不強求 50>150
                curr_p >= (low52 * 1.30),           # 核心：高於低點 30%
                curr_p >= (high52 * 0.75)
            ]
            if sum(cond) < 4: 
                return None
            # 150>200 可有可無，不硬性排除

        # ==================== VCP 收縮 + 其他條件 (兩版共用) ====================
        # T1/T2/T3 收縮邏輯...
        t1_high = close.iloc[-65:-35].max()
        t1_low = close.iloc[-65:-35].min()
        t1_contraction = (t1_high - t1_low) / t1_high if t1_high > 0 else 0.3
        
        t2_high = close.iloc[-35:-15].max()
        t2_low = close.iloc[-35:-15].min()
        t2_contraction = (t2_high - t2_low) / t2_high if t2_high > 0 else 0.2
        
        t3_high = close.iloc[-15:-1].max()
        t3_low = close.iloc[-15:-1].min()
        t3_contraction = (t3_high - t3_low) / t3_high if t3_high > 0 else 0.1
        
        if not (t1_contraction > t2_contraction and t2_contraction > t3_contraction and t3_contraction < 0.12):
            return None
            
        # 近期 5 天緊湊度
        recent_max = close.iloc[-5:].max()
        recent_min = close.iloc[-5:].min()
        recent_range = (recent_max - recent_min) / recent_min
        
        if recent_range <= 0.05:
            is_tight = "💎 極度緊湊"
        elif recent_range <= 0.08:
            is_tight = "✅ 緊湊"
        else:
            return None

        # 量縮
        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        if vol.iloc[-1] > vol_ma20 * 0.95: 
            return None 
            
        # SCTR
        sctr_val = round(sctr_map.get(ticker, 0), 1)
        sctr_hist = round(sctr_hist_map.get(ticker, 0), 1)
        if sctr_val < 80.0 or sctr_val <= sctr_hist: 
            return None
        
        # 突破檢測
        breakout_max = float(close.iloc[-(b_days+1):-1].max())
        is_breakout = curr_p > breakout_max
        if b_only and not is_breakout: 
            return None
        
        status = f"🔥 {b_days}D突破" if is_breakout else "🚀 強勢向上"
        
        # 風險報酬計算...
        atr_series = ta.atr(high, low, close, length=14)
        atr_val = float(atr_series.iloc[-1]) if not atr_series.isna().iloc[-1] else (float(high.iloc[-1]) - float(low.iloc[-1]))
        
        pivot_point = breakout_max  
        stop_loss = curr_p - (1.5 * atr_val)  
        target_price = curr_p + (3.0 * (curr_p - stop_loss)) 
        
        dist_high = round((1 - curr_p/high52) * 100, 2)
        vol_ratio = round(float(vol.iloc[-1]) / vol_ma20, 2)
        
        sector = get_sector_cached(ticker)
        
        return [
            ticker, round(curr_p, 2), dist_high, sctr_val, is_tight, vol_ratio, 
            status, sector, round(pivot_point, 2), round(stop_loss, 2), round(target_price, 2)
        ]
    except Exception as e:
        # print(f"Error on {ticker}: {e}")  # 除錯用
        return None
