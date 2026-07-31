#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import urllib.request
import urllib.error
import ssl
import time
from datetime import datetime

# ================= 全局配置 =================
# 企微 Webhook 机器人地址 (请替换为你的真实 URL)
WECHAT_WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE"

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
    数学公式: m = (n*Σxy - Σx*Σy) / (n*Σx^2 - (Σx)^2)
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
    print("⏳ 正在拉取各代币过去 20 个月 (600天) 日线数据，可能需要 1~2 分钟，请稍候...")
    
    results = []
    total = len(symbols)
    
    for idx, sym in enumerate(symbols):
        # 打印进度条，防止焦虑
        if idx % 50 == 0:
            print(f"   - 扫描进度: {idx}/{total}...")
            
        url = f"{BASE_URL}/fapi/v1/klines?symbol={sym}&interval=1d&limit=600"
        klines = fetch_json(url)
        
        # 保证至少有 7 天的数据才能计算近期斜率
        if not klines or len(klines) < 7:
            continue
            
        try:
            # 解析日线数据
            # Kline 结构: [开盘时间, 开盘价, 最高价, 最低价, 收盘价, 成交量, 收盘时间, 成交额, ...]
            lows = [float(k[3]) for k in klines]
            highs = [float(k[2]) for k in klines]
            current_price = float(klines[-1][4]) # 最新收盘价
            
            min_price = min(lows)
            max_price = max(highs)
            
            if min_price <= 0 or max_price == min_price:
                continue
                
            # 计算距离底部的百分比和历史分位
            distance_to_min_pct = ((current_price - min_price) / min_price) * 100.0
            percentile_pct = ((current_price - min_price) / (max_price - min_price)) * 100.0
            
            # 提取最后 7 天的数据，计算买卖盘资金（USDT 计价）
            last_7_days = klines[-7:]
            
            total_vol_7d = []
            taker_buy_vol_7d = []
            taker_sell_vol_7d = []
            
            for k in last_7_days:
                quote_vol = float(k[7])              # 总成交额
                taker_buy_quote = float(k[10])       # 主动买盘成交额
                taker_sell_quote = quote_vol - taker_buy_quote # 主动卖盘成交额
                
                total_vol_7d.append(quote_vol)
                taker_buy_vol_7d.append(taker_buy_quote)
                taker_sell_vol_7d.append(taker_sell_quote)
                
            # 计算斜率
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
            
        # 短暂休眠防止触碰 API Rate Limit (币安 FAPI 限制 2400次/分钟)
        time.sleep(0.02)
        
    return results

def send_wechat_alert(top_20_results):
    """4. 格式化数据并推送到企业微信"""
    if not top_20_results:
        print("❌ 没有有效数据可以推送。")
        return
        
    # Markdown 消息头
    msg_lines = [
        f"### 📊 底部山寨币买盘异动扫描 (Top 20)",
        f"> **数据窗口**: 历史20个月日线极值 / 近7日动量拟合",
        f"> **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ""
    ]
    
    # 逐条格式化 Top 20 代币
    for idx, data in enumerate(top_20_results, 1):
        sym = data['symbol']
        dist = data['distance_min_pct']
        perc = data['percentile_pct']
        
        # 将 USDT 斜率数值简化为“万”级别，方便阅读
        buy_s_w = data['slope_buy'] / 10000.0
        sell_s_w = data['slope_sell'] / 10000.0
        tot_s_w = data['slope_total'] / 10000.0
        
        # 使用颜色标识买盘斜率正负
        buy_color = "info" if buy_s_w > 0 else "warning"
        
        msg_lines.append(f"**{idx}. {sym}**  (上市 {data['days_existed']} 天)")
        msg_lines.append(f"> 距底部: `<font color=\"warning\">{dist:.2f}%</font>` | 历史分位: `{perc:.2f}%`")
        msg_lines.append(f"> 7日主动买盘斜率: `<font color=\"{buy_color}\">{buy_s_w:+.1f}万</font>`")
        msg_lines.append(f"> 7日主动卖盘斜率: `{sell_s_w:+.1f}万` | 7日总额斜率: `{tot_s_w:+.1f}万`")
        msg_lines.append("")
        
    markdown_content = "\n".join(msg_lines)
    
    # 构建企微 payload
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": markdown_content
        }
    }
    
    # 发送请求
    try:
        req = urllib.request.Request(
            WECHAT_WEBHOOK_URL, 
            data=json.dumps(payload).encode('utf-8'), 
            headers={'Content-Type': 'application/json'},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10, context=CONTEXT) as response:
            res_data = response.read().decode('utf-8')
            print("✅ 企微推送成功:", res_data)
    except Exception as e:
        print(f"❌ 企微推送失败: {e}")

def run_scanner():
    print("=" * 60)
    print("🚀 启动底部动量猎犬扫描器...")
    print("=" * 60)
    
    # 1. 拿池子
    valid_symbols = get_valid_universe()
    if not valid_symbols:
        return
        
    # 2. 算极值与斜率
    raw_results = process_historical_data(valid_symbols)
    
    # 3. 按距离底部百分比升序 (越小说明离底部越近)
    raw_results.sort(key=lambda x: x["distance_min_pct"])
    
    # 4. 截取距离底部最近的 Top 20
    top_20_closest = raw_results[:20]
    
    # 5. 在这 20 个币中，按照 7 日“主动买盘斜率”降序排列 (最高最强排前面)
    top_20_closest.sort(key=lambda x: x["slope_buy"], reverse=True)
    
    # 6. 发送企微
    send_wechat_alert(top_20_closest)
    
    print("🎉 扫描与计算任务全部完成！")

if __name__ == "__main__":
    run_scanner()
