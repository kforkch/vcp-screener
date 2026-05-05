# analyzer.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta
# 從 data_loader 匯入行業抓取函式
from data_loader import get_sector_cached

def calculate_sctr_ranks(tickers, lookback=20, pre_downloaded_data=None):
    """
    計算當前與 lookback 天前的 SCTR，支援傳入已預載的 DataFrame 減輕 API 負擔
    """
    try:
        if pre_downloaded_data is not None:
            data = pre_downloaded_data
        else:
            raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
            data = raw_data['Close'] if 'Close' in raw_data else raw_data
        
        sctr_current = []
        sctr_historical = []
        
        for ticker in tickers:
            try:
                # 兼容處理 Multi-Index 與單一 Index 的 DataFrame 提取
                if isinstance(data, pd.DataFrame):
                    if ticker in data.columns:
                        series = data[ticker].dropna()
                    else:
                        continue
                else:
                    series = data.dropna()
                
                if len(series) < 200 + lookback: continue
                
                # SCTR 核心計算
                def get_sctr_raw(sub_series):
                    sma200, sma50 = sub_series.rolling(200).mean().iloc[-1], sub_series.rolling(50).mean().iloc[-1]
                    dist_200, dist_50 = (sub_series.iloc[-1]/sma200-1)*100, (sub_series.iloc[-1]/sma50-1)*100
                    roc125, roc20 = (sub_series.iloc[-1]/sub_series.iloc[-125]-1)*100, (sub_series.iloc[-1]/sub_series.iloc[-20]-1)*100
                    rsi = ta.rsi(sub_series, length=14).iloc[-1]
                    return (dist_200*0.3 + roc125*0.3) + (dist_50*0.15 + roc20*0.15) + (rsi*0.1)
                
                raw_curr = get_sctr_raw(series)
                raw_hist = get_sctr_raw(series.iloc[:-lookback])
                
                sctr_current.append({'ticker': ticker, 'raw': raw_curr})
                sctr_historical.append({'ticker': ticker, 'raw': raw_hist})
            except:
                continue
            
        if not sctr_current: return {}, {}
        
        df_curr = pd.DataFrame(sctr_current)
        df_curr['rank'] = df_curr['raw'].rank(pct=True) * 99.9
        dict_curr = df_curr.set_index('ticker')['rank'].to_dict()
        
        df_hist = pd.DataFrame(sctr_historical)
        df_hist['rank'] = df_hist['raw'].rank(pct=True) * 99.9
        dict_hist = df_hist.set_index('ticker')['rank'].to_dict()
        
        return dict_curr, dict_hist
    except:
        return {}, {}

def check_vcp_advanced_preloaded(ticker, ticker_df, sctr_map, sctr_hist_map, b_only, b_days):
    """
    實戰進階 VCP 掃描器 (本地記憶體極速版)
    直接分析傳入的個股本地 DataFrame，免除 yfinance API 重複存取
    """
    try:
        if ticker_df.empty or len(ticker_df) < 200: return None
        
        close = ticker_df['Close'].dropna()
        high = ticker_df['High'].dropna()
        low = ticker_df['Low'].dropna()
        vol = ticker_df['Volume'].dropna()
        
        if len(close) < 200: return None
        
        curr_p = float(close.iloc[-1])
        
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.min()), float(close.max())
        
        # 1. 經典馬克趨勢模板過濾 (Trend Template)
        cond = [
            curr_p > sma150 and curr_p > sma200, sma150 > sma200, 
            sma50 > sma150 and sma50 > sma200, curr_p > sma50,
            curr_p >= (low52 * 1.25), curr_p >= (high52 * 0.75)
        ]
        if sum(cond) < 6: return None
        
        # 2. ATR 動態計算與波動基準
        atr_series = ta.atr(high, low, close, length=14)
        atr_val = float(atr_series.iloc[-1]) if not atr_series.isna().iloc[-1] else (float(high.iloc[-1]) - float(low.iloc[-1]))
        atr_pct = atr_val / curr_p  
        
        # 3. 滾動區間波動收縮演算法 (Rolling Window Extremes)
        roll_high = high.rolling(window=15, min_periods=1)
        roll_low = low.rolling(window=15, min_periods=1)
        
        t1_high = float(roll_high.max().iloc[-45])
        t1_low  = float(roll_low.min().iloc[-45])
        t1_contraction = (t1_high - t1_low) / t1_low if t1_low > 0 else 0.3
        
        t2_high = float(roll_high.max().iloc[-20])
        t2_low  = float(roll_low.min().iloc[-20])
        t2_contraction = (t2_high - t2_low) / t2_low if t2_low > 0 else 0.2
        
        t3_high = float(roll_high.max().iloc[-5])
        t3_low  = float(roll_low.min().iloc[-5])
        t3_contraction = (t3_high - t3_low) / t3_low if t3_low > 0 else 0.1
        
        # VCP 收縮核心邏輯：滾動波幅遞減 + ATR 動態門檻
        dynamic_t3_threshold = min(0.08, atr_pct * 1.5)
        
        if not (t1_contraction > t2_contraction > t3_contraction and t3_contraction < dynamic_t3_threshold):
            return None
            
        # 5 日極窄收緊確認
        recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
        is_tight = "✅ 緊湊" if recent_range < dynamic_t3_threshold else "❌ 鬆散"

        # 4. 成交量乾涸度檢查 (VUD 籌碼安靜點：萎縮至 20 日均量的 80% 以下)
        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        if vol.iloc[-1] > vol_ma20 * 0.8: return None 
            
        # 5. SCTR 持續攀升檢查
        sctr_val = round(sctr_map.get(ticker, 0), 1)
        sctr_hist = round(sctr_hist_map.get(ticker, 0), 1)
        if sctr_val < 80.0 or sctr_val <= sctr_hist: return None
        
        # 6. 突破檢測
        recent_max = float(close.iloc[-(b_days+1):-1].max())
        is_breakout = curr_p > recent_max
        if b_only and not is_breakout: return None
        
        status = f"🔥 {b_days}D突破" if is_breakout else "🚀 強勢向上"
        
        # 7. 風險報酬計算
        pivot_point = recent_max  
        stop_loss = curr_p - (1.5 * atr_val)  
        target_price = curr_p + (3.0 * (curr_p - stop_loss)) 
        
        dist_high = round((1 - curr_p/high52) * 100, 2)
        vol_ratio = round(float(vol.iloc[-1]) / vol_ma20, 2)
        
        sector = get_sector_cached(ticker)
        
        return [
            ticker, round(curr_p, 2), dist_high, sctr_val, is_tight, vol_ratio, status, sector,
            round(pivot_point, 2), round(stop_loss, 2), round(target_price, 2)
        ]
    except Exception as e:
        return None

# 保留原有的 check_vcp_advanced 接口以防外部呼叫，其內部同樣升級為動態 ATR 核心
def check_vcp_advanced(ticker, sctr_map, sctr_hist_map, b_only, b_days):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty: return None
        return check_vcp_advanced_preloaded(ticker, df, sctr_map, sctr_hist_map, b_only, b_days)
    except:
        return None
