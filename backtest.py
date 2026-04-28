# backtest.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta

def get_data(ticker, period="2y"):
    """獲取個股與大盤數據"""
    # 同時下載個股與大盤 S&P 500
    df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    index_df = yf.download("^GSPC", period=period, progress=False, auto_adjust=True)
    return df, index_df

def run_backtest(ticker, initial_capital=100000):
    df, index_df = get_data(ticker)
    if len(df) < 200 or len(index_df) < 200:
        return None

    trades = []
    in_position = False
    entry_price = 0
    stop_loss = 0
    target_price = 0
    
    # 遍歷歷史數據
    for i in range(200, len(df) - 1):
        subset = df.iloc[:i+1]
        market_subset = index_df.iloc[:i+1]
        
        # --- 大盤濾網邏輯 (Market Regime Filter) ---
        market_sma150 = market_subset['Close'].rolling(150).mean().iloc[-1]
        is_market_bullish = market_subset['Close'].iloc[-1] > market_sma150
        # ------------------------------------------
        
        curr_p = float(subset['Close'].iloc[-1])
        sma50 = ta.sma(subset['Close'], 50).iloc[-1]
        sma150 = ta.sma(subset['Close'], 150).iloc[-1]
        sma200 = ta.sma(subset['Close'], 200).iloc[-1]
        
        # 1. 判斷進場
        if not in_position:
            # 必須滿足趨勢模板，且大盤處於牛市狀態
            if is_market_bullish and curr_p > sma150 > sma200 and sma50 > sma150:
                recent_max = float(subset['Close'].iloc[-21:-1].max())
                if curr_p > recent_max:
                    atr = ta.atr(subset['High'], subset['Low'], subset['Close'], length=14).iloc[-1]
                    entry_price = curr_p
                    stop_loss = entry_price - (1.5 * atr)
                    target_price = entry_price + (3.0 * (entry_price - stop_loss))
                    in_position = True
        
        # 2. 判斷出場
        else:
            # 加入額外規則：如果大盤跌破 150 日均線，立即停損/止盈，清倉避險
            if not is_market_bullish:
                profit = (curr_p - entry_price) / entry_price
                trades.append({'ticker': ticker, 'type': 'Market_Exit', 'return': profit, 'date': df.index[i]})
                in_position = False
            elif subset['Low'].iloc[-1] <= stop_loss:
                profit = (stop_loss - entry_price) / entry_price
                trades.append({'ticker': ticker, 'type': 'SL', 'return': profit, 'date': df.index[i]})
                in_position = False
            elif subset['High'].iloc[-1] >= target_price:
                profit = (target_price - entry_price) / entry_price
                trades.append({'ticker': ticker, 'type': 'TP', 'return': profit, 'date': df.index[i]})
                in_position = False

    return trades

def print_report(trades):
    if not trades:
        print("無交易紀錄 (可能受大盤濾網過濾)。")
        return
    
    df_trades = pd.DataFrame(trades)
    win_rate = len(df_trades[df_trades['return'] > 0]) / len(df_trades)
    total_return = (1 + df_trades['return']).prod() - 1
    
    print(f"--- 包含大盤濾網的回測報告 ---")
    print(f"交易次數: {len(df_trades)}")
    print(f"勝率: {win_rate:.2%}")
    print(f"累積報酬率: {total_return:.2%}")
    print(df_trades.tail(10))

if __name__ == "__main__":
    ticker = "NVDA"
    print(f"正在對 {ticker} 進行受大盤保護的 VCP 回測...")
    results = run_backtest(ticker)
    print_report(results)
