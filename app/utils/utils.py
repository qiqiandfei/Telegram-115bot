# -*- coding: utf-8 -*-
import re
import init
from datetime import datetime, timedelta, date



def random_waite(min=2, max=15):
    import random
    import time
    wait_time = random.randint(min, max)
    init.logger.info(f"随机等待 {wait_time} 秒以模拟人类行为...")
    ms = float(random.randint(1, 999)) / 1000.0
    time.sleep(wait_time + ms)
    
    
def date_convert2BJT(date_str):
    if not date_str:
        return date.today().strftime("%Y-%m-%d")
    try:
        # 解析 ISO 格式并替换 Z 为 UTC 偏移
        dt_utc = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        # 转换为北京时间（UTC+8）
        dt_beijing = dt_utc + timedelta(hours=8)
        # 只保留日期
        date_str = dt_beijing.strftime("%Y-%m-%d")
    except Exception as e:
        init.logger.error(f"日期转换失败: {e}, 输入日期字符串: {date_str}")
    return date_str  # 返回原始字符串以防万一


def get_magnet_hash(magnet):
    if not magnet:
        return None
    # 匹配 hex (40) 或 base32 (32)
    pattern = r"urn:btih:([a-fA-F0-9]{40}|[a-zA-Z2-7]{32})"
    match = re.search(pattern, magnet, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None