# analyzer.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from data_loader import get_sector_cached

def check_fundamentals(ticker_obj):
    """
    根據基本面條件過濾：
    ROE >= 12%, Current Ratio > 1.5, Quick Ratio > 1, Debt/Equity < 0.5
    """
    try:
        info = ticker_obj.info
        
        # 提取數據，處理缺失值
        roe = info.get('returnOnEquity', 0)
        curr_r = info.get('currentRatio', 0)
        quick_r = info.get('quickRatio', 0)
        debt_e = info.get('debtToEquity', 100) # 若無資料設為高負債
        
        # 基本面條件檢核 (調整參數以符合你的嚴格要求)
        conds = [
            (roe is not None and roe >= 0.12),
            (curr_r is not None and curr_r >= 1.5),
            (quick_r is not None and quick_r >= 1.0),
            (debt_e is not None and debt_e <= 50) # 注意：yfinance 有時單位不同，需確認是否為百分比
        ]
        
        return all(conds)
    except:
        return False # 發生錯誤則過濾掉

def calculate_sctr_ranks(tickers):
    try:
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        data = raw_data['Close'] if 'Close' in raw_data else raw_data
        
        sctr_data = []
        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                if len(series) < 200: continue
                
                sma200, sma50 = series.rolling(200).mean().iloc[-1], series.rolling(50).mean().iloc[-1]
                dist_200, dist_50 = (series.iloc[-1]/sma200-1)*100, (series.iloc[-1]/sma50-1)*100
                roc125, roc20 = (series.iloc[-1]/series.iloc[-125]-1)*100, (series.iloc[-1]/series.iloc[-20]-1)*100
                rsi = ta.rsi(series, length=14).iloc[-1]
                
                raw = (dist_200*0.3 + roc125*0.3) + (dist_50*0.15 + roc20*0.15) + (rsi*0.1)
                sctr_data.append({'ticker': ticker, 'raw': raw})
            except: continue
            
        if not sctr_data: return {}
        df_sctr = pd.DataFrame(sctr_data)
        df_sctr['rank'] = df_sctr['raw'].rank(pct=True) * 99.9
        return df_sctr.set_index('ticker')['rank'].to_dict()
    except: return {}

def check_vcp_advanced(ticker, sctr_map, b_only, b_days, use_fundamentals=False):
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period="1y", auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        # 技術面檢核
        close = df['Close']
        curr_p = float(close.iloc[-1])
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.min()), float(close.max())
        
        cond = [
            curr_p > sma150 and curr_p > sma200, sma150 > sma200, 
            sma50 > sma150 and sma50 > sma200, curr_p > sma50,
            curr_p >= (low52 * 1.25), curr_p >= (high52 * 0.75)
        ]
        
        if sum(cond) < 6: return None # 未通過趨勢模板
        
        # 基本面過濾 (僅在通過技術模板後執行，節省效能)
        if use_fundamentals:
            if not check_fundamentals(tk): return None
            
        recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
        prev_range = (close.iloc[-25:-5].max() - close.iloc[-25:-5].min()) / close.iloc[-25:-5].min()
        is_tight = "✅ 緊湊" if recent_range < (prev_range * 0.7) else "❌ 鬆散"
        
        recent_max = float(close.iloc[-(b_days+1):-1].max())
        is_breakout = curr_p > recent_max
        if b_only and not is_breakout: return None
        
        atr_series = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        atr_val = float(atr_series.iloc[-1]) if not atr_series.isna().iloc[-1] else (float(df['High'].iloc[-1]) - float(df['Low'].iloc[-1]))
        
        pivot_point = recent_max
        stop_loss = curr_p - (1.5 * atr_val)
        target_price = curr_p + (3.0 * (curr_p - stop_loss))
        
        vol_ratio = round(float(df['Volume'].iloc[-1]) / df['Volume'].rolling(20).mean().iloc[-1], 2)
        sctr_val = round(sctr_map.get(ticker, 0), 1)
        sector = get_sector_cached(ticker)
        status = f"🔥 {b_days}D突破" if is_breakout else "🚀 強勢向上"
        
        return [
            ticker, round(curr_p, 2), round((1 - curr_p/high52) * 100, 2), sctr_val, 
            is_tight, vol_ratio, status, sector,
            round(pivot_point, 2), round(stop_loss, 2), round(target_price, 2)
        ]
    except: return None
