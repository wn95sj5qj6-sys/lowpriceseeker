#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import urllib.request
import urllib.error
import ssl
import time
from datetime import datetime

# ================= 全局配置 =================
# 你的企业微信 Webhook 地址
WECHAT_WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=be857434-02bd-4975-baac-f1afeef038d1"

# 排除的主流代币黑名单
MAJOR_BLACKLIST = {
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", 
    "ADAUSDT", "DOGEUSDT", "TRXUSDT", "TONUSDT", "LINKUSDT", 
    "LTCUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT", "BCHUSDT", 
    "SUIUSDT", "APTUSDT", "NEARUSDT", "FILUSDT", "ETCUSDT",
    "ICPUSDT", "XLMUSDT", "UNIUSDT", "STXUSDT", "CROUSDT"
}

# 币安 FAPI 基础地址
BASE_URL = "https://fapi.binance.com"

# SSL 环境设置
CONTEXT = ssl.create_default_context()
CONTEXT.set_ciphers('DEFAULT@SECLEVEL=1')
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

def fetch_json(url):
    """通用的 GET 请求辅助函数"""
    req = urllib.request.Request(url, headers=HEADERS, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10, context=CONTEXT) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"❌ API 请求失败 [{url}]: {e}")
        return None

def get_valid_universe():
    """1. 获取所有纯 Crypto 山寨永续合约"""
    print("⏳ 正在获取币安合约市场元数据...")
    data = fetch_json(f"{BASE_URL}/fapi/v1/exchangeInfo")
    if not data:
        return []
    
    valid_symbols = []
    NON_CRYPTO_TYPES = {"STOCK", "EQUITY", "ETF", "INDEX", "GLOBAL_MACRO"}
    
    for s in data.get("symbols", []):
        sym = s.get("symbol", "")
        u_type = str(s.get("underlyingType", "")).upper()
        
        if (s.get("status") == "TRADING" and 
            s.get("contractType") == "PERPETUAL" and 
            s.get("quoteAsset") == "USDT" and 
            "_" not in sym and 
            sym not in MAJOR_BLACKLIST and 
            u_type not in NON_CRYPTO_TYPES):
            valid_symbols.append(sym)
            
    print(f"✅ 成功过滤出 {len(valid_symbols)} 个纯山寨/Meme USDT 永续合约")
    return valid_symbols

def calculate_linear_slope(y_values):
    """
    2. 计算线性回归斜率 (一元一次方程拟合)
    """
    n = len(y_values)
    if n < 2:
        return 0.0
    x_values = list(range(1, n + 1))
    sum_x = sum(x_values)
    sum_y = sum(y_values)
    sum_xy = sum(x * y for x, y in zip(x_values, y_values))
    sum_xx = sum(x * x for x in x_values)
    
    denominator = (n * sum_xx) - (sum_x ** 2)
    if denominator == 0:
        return 0.0
    return ((n * sum_xy) - (sum_x * sum_y)) / denominator

def process_historical_data(symbols):
    """3. 获取历史日线数据并计算极值与分位"""
    print("⏳ 正在拉取各代币日线数据计算极值与动量...")
    
    results = []
    total = len(symbols)
    
    for idx, sym in enumerate(symbols):
        if idx > 0 and idx % 50 == 0:
            print(f"   - 扫描进度: {idx}/{total}...")
            
        url = f"{BASE_URL}/fapi/v1/klines?symbol={sym}&interval=1d&limit=600"
        klines = fetch_json(url)
        
        if not klines or len(klines) < 7:
            continue
            
        try:
            lows = [float(k[3]) for k in klines]
            highs = [float(k[2]) for k in klines]
            current_price = float(klines[-1][4])
            
            min_price = min(lows)
            max_price = max(highs)
            
            if min_price <= 0 or max_price == min_price:
                continue
                
            distance_to_min_pct = ((current_price - min_price) / min_price) * 100.0
            percentile_pct = ((current_price - min_price) / (max_price - min_price)) * 100.0
            
            last_7_days = klines[-7:]
            
            total_vol_7d = []
            taker_buy_vol_7d = []
            taker_sell_vol_7d = []
            
            for k in last_7_days:
                quote_vol = float(k[7])
                taker_buy_quote = float(k[10])
                taker_sell_quote = quote_vol - taker_buy_quote
                
                total_vol_7d.append(quote_vol)
                taker_buy_vol_7d.append(taker_buy_quote)
                taker_sell_vol_7d.append(taker_sell_quote)
                
            slope_total = calculate_linear_slope(total_vol_7d)
            slope_buy = calculate_linear_slope(taker_buy_vol_7d)
            slope_sell = calculate_linear_slope(taker_sell_vol_7d)
            
            results.append({
                "symbol": sym,
                "distance_min_pct": distance_to_min_pct,
                "percentile_pct": percentile_pct,
                "slope_buy": slope_buy,
                "slope_sell": slope_sell,
                "slope_total": slope_total,
                "days_existed": len(klines)
            })
            
        except Exception as e:
            continue
            
        time.sleep(0.02)
        
    return results

def send_wechat_alert(top_20_results):
    """4. 格式化数据并推送到企业微信"""
    if not top_20_results:
        print("❌ 没有有效数据可以推送。")
        return
        
    msg_lines = [
        f"### 📊 底部买盘异动扫描 (Top 20)",
        f"> **数据窗口**: 历史极值 / 近7日动量拟合",
        f"> **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ""
    ]
    
    for idx, data in enumerate(top_20_results, 1):
        sym = data['symbol']
        dist = data['distance_min_pct']
        perc = data['percentile_pct']
        
        buy_s_w = data['slope_buy'] / 10000.0
        sell_s_w = data['slope_sell'] / 10000.0
        tot_s_w = data['slope_total'] / 10000.0
        
        buy_color = "info" if buy_s_w > 0 else "warning"
        
        msg_lines.append(f"**{idx}. {sym}**  (上市 {data['days_existed']} 天)")
        msg_lines.append(f"> 距底部: `<font color=\"warning\">{dist:.2f}%</font>` | 历史分位: `{perc:.2f}%`")
        msg_lines.append(f"> 买盘斜率: `<font color=\"{buy_color}\">{buy_s_w:+.1f}万</font>` | 卖盘斜率: `{sell_s_w:+.1f}万`")
        msg_lines.append("")
        
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": "\n".join(msg_lines)
        }
    }
    
    try:
        req = urllib.request.Request(
            WECHAT_WEBHOOK_URL, 
            data=json.dumps(payload).encode('utf-8'), 
            headers={'Content-Type': 'application/json'},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10, context=CONTEXT) as response:
            print("✅ 企微推送成功")
    except Exception as e:
        print(f"❌ 企微推送失败: {e}")

def run_scanner():
    print("\n" + "=" * 60)
    print(f"🚀 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动扫描任务...")
    print("=" * 60)
    
    valid_symbols = get_valid_universe()
    if not valid_symbols:
        return
        
    raw_results = process_historical_data(valid_symbols)
    
    raw_results.sort(key=lambda x: x["distance_min_pct"])
    top_20_closest = raw_results[:20]
    top_20_closest.sort(key=lambda x: x["slope_buy"], reverse=True)
    
    send_wechat_alert(top_20_closest)
    print("🎉 本轮扫描完成！")

if __name__ == "__main__":
    print("🕒 初始化常驻后台扫描器...")
    # 4 小时 = 14400 秒
    INTERVAL_SECONDS = 14400 
    
    while True:
        try:
            run_scanner()
        except Exception as e:
            print(f"❌ 扫描循环发生未捕获异常: {e}")
            
        print(f"⏳ 任务完成，进入 4 小时休眠，下次执行将在 {INTERVAL_SECONDS/3600} 小时后...")
        time.sleep(INTERVAL_SECONDS)
