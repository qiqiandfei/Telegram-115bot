# -*- coding: utf-8 -*-
import re
import init
from datetime import datetime, timedelta, date
import yaml
import os
from urllib.parse import urlparse, parse_qs

def read_yaml_file(yaml_path):
    # 获取yaml文件名称
    try:
        # 获取yaml文件路径
        if os.path.exists(yaml_path):
            with open(yaml_path, 'r', encoding='utf-8') as f:
                cfg = f.read()
                f.close()
            yaml_conf = yaml.load(cfg, Loader=yaml.FullLoader)
            return yaml_conf
        else:
           return False
    except Exception as e:
        init.logger.warn(f"配置文件[{yaml_path}]格式有误，请检查!")
        return False


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


def check_magnet(magnet):
    pattern = r"^magnet:\?xt=urn:btih:([a-fA-F0-9]{40}|[a-zA-Z2-7]{32})(?:&.*)?$"
    if not isinstance(magnet, str) or not magnet.startswith('magnet:'):
        return False
    return re.fullmatch(pattern, magnet) is not None


def check_input(input_str):
    """_summary_
    判断输入字符串的内容
    纯英文 返回 1
    纯数字 返回 2
    纯中文 返回 3
    纯日文 返回 4
    中文 + 日文 返回 5
    英文 + 数字 返回 6
    其他 返回 0
    Args:
        input_str (_type_): _description_
    """
    if not input_str:
        return 0
        
    # 纯英文
    if re.fullmatch(r'[a-zA-Z]+', input_str):
        return 1
    # 纯数字
    elif re.fullmatch(r'[0-9]+', input_str):
        return 2
    # 纯中文 (汉字)
    elif re.fullmatch(r'[\u4e00-\u9fa5]+', input_str):
        return 3
    # 纯日文 (平假名/片假名)
    elif re.fullmatch(r'[\u3040-\u309F\u30A0-\u30FF]+', input_str):
        return 4
    # 中文 + 日文
    elif re.fullmatch(r'[\u4e00-\u9fa5\u3040-\u309F\u30A0-\u30FF]+', input_str):
        return 5
    # 英文 + 数字
    elif re.fullmatch(r'[a-zA-Z0-9]+', input_str):
        return 6
    
    return 0


def clean_magnet(magnet_link):
    """
    Clean magnet link, remove trackers and other parameters, keep only xt.
    """
    if not magnet_link:
        return ""
    try:
        parsed = urlparse(magnet_link)
        if parsed.scheme != 'magnet':
            return magnet_link
        
        params = parse_qs(parsed.query)
        xt = params.get('xt', [])
        if xt:
            return f"magnet:?xt={xt[0]}"
    except:
        pass
    return magnet_link