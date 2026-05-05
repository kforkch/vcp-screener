def check_vcp_advanced(ticker, sctr_map, sctr_hist_map, b_only, b_days,
                       min_tightening=2, atr_ratio_threshold=0.78, roll_window=20):
    """
    進階 VCP 掃描器 - 滾動區間 + ATR 動態門檻
    """
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200:
            return None

        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        high = df['High'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['High']
        low = df['Low'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Low']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']

        curr_p = float(close.iloc[-1])

        # 1. Trend Template
        sma50 = ta.sma(close, 50).iloc[-1]
        sma150 = ta.sma(close, 150).iloc[-1]
        sma200 = ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.min()), float(close.max())

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
        df['ATR14'] = ta.atr(high, low, close, length=14)
        df['ATR_ratio'] = df['ATR14'] / close
        recent_atr = df['ATR_ratio'].tail(10).mean()
        hist_atr = df['ATR_ratio'].tail(60).mean()
        
        if recent_atr > hist_atr * atr_ratio_threshold:
            return None

        # 3. 滾動區間收縮檢測（核心）
        df['roll_range'] = (high.rolling(window=roll_window, min_periods=10).max() - 
                           low.rolling(window=roll_window, min_periods=10).min())
        
        roll_ranges = df['roll_range'].dropna().tail(7).values

        tightening_count = 0
        for i in range(1, len(roll_ranges)):
            if roll_ranges[i] < roll_ranges[i-1] * 0.90:   # 至少收緊10%
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

        # 7. 突破
        recent_max = float(close.iloc[-(b_days + 1):-1].max())
        is_breakout = curr_p > recent_max
        if b_only and not is_breakout:
            return None

        status = f"🔥 {b_days}D突破" if is_breakout else "🚀 強勢向上"

        # 8. 風險報酬
        atr_val = float(df['ATR14'].iloc[-1])
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
