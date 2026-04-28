# backtest.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta

def get_data(ticker, period="2y"):
    """獲取歷史數據"""
    df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    return df

def run_backtest(ticker, initial_capital=100000):
    df = get_data(ticker)
    if len(df) < 200:
        return None

    trades = []
    in_position = False
    entry_price = 0
    stop_loss = 0
    target_price = 0
    
    # 遍歷歷史數據 (跳過前 200 天以確保均線數據完整)
    for i in range(200, len(df) - 1):
        subset = df.iloc[:i+1]
        close = subset['Close']
        high = subset['High']
        low = subset['Low']
        
        curr_p = float(close.iloc[-1])
        
        # 1. 簡單的趨勢模板篩選
        sma50 = ta.sma(close, 50).iloc[-1]
        sma150 = ta.sma(close, 150).iloc[-1]
        sma200 = ta.sma(close, 200).iloc[-1]
        
        # 2. 如果未持倉，尋找 VCP 突破信號
        if not in_position:
            # 檢查趨勢模板
            if curr_p > sma150 > sma200 and sma50 > sma150:
                # 簡單定義突破：收盤價突破過去 20 天最高
                recent_max = float(close.iloc[-21:-1].max())
                if curr_p > recent_max:
                    # 計算 ATR 用於設定停損
                    atr = ta.atr(high, low, close, length=14).iloc[-1]
                    entry_price = curr_p
                    stop_loss = entry_price - (1.5 * atr)
                    target_price = entry_price + (3.0 * (entry_price - stop_loss))
                    in_position = True
        
        # 3. 如果持倉中，檢查出場條件
        else:
            # 當日最低價低於停損，或最高價觸及目標
            if low.iloc[-1] <= stop_loss:
                profit = (stop_loss - entry_price) / entry_price
                trades.append({'ticker': ticker, 'type': 'SL', 'return': profit, 'date': df.index[i]})
                in_position = False
            elif high.iloc[-1] >= target_price:
                profit = (target_price - entry_price) / entry_price
                trades.append({'ticker': ticker, 'type': 'TP', 'return': profit, 'date': df.index[i]})
                in_position = False

    return trades

def print_report(trades):
    if not trades:
        print("無交易紀錄。")
        return
    
    df_trades = pd.DataFrame(trades)
    win_rate = len(df_trades[df_trades['return'] > 0]) / len(df_trades)
    total_return = (1 + df_trades['return']).prod() - 1
    
    print(f"--- 回測報告 ---")
    print(f"交易次數: {len(df_trades)}")
    print(f"勝率: {win_rate:.2%}")
    print(f"累積報酬率: {total_return:.2%}")
    print(df_trades.tail(10))

if __name__ == "__main__":
    # 測試單一標的
    ticker = "NVDA" 
    print(f"正在回測 {ticker} ...")
    results = run_backtest(ticker)
    print_report(results)
