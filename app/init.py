# -*- coding: utf-8 -*-

import os
import yaml
import sys
import shutil
import subprocess
from typing import Optional
from telethon import TelegramClient
from app.core.open_115 import OpenAPI_115


# 模块路径现在通过 Dockerfile 中的 PYTHONPATH 环境变量设置
# 为了兼容本地开发，添加后备路径设置
def _ensure_module_paths():
    """
    确保模块路径可用，主要用于本地开发环境
    在 Docker 环境中，PYTHONPATH 已通过环境变量设置
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    required_paths = [current_dir, os.path.dirname(current_dir)]
    
    for path in required_paths:
        if path not in sys.path:
            sys.path.insert(0, path)

# 执行路径检查
_ensure_module_paths()

from app.utils.logger import Logger
from app.utils.sqlitelib import *


# 调试模式
debug_mode = False

# 全局日志
logger:Optional[Logger] = None

# 全局配置
bot_config = dict()

# 115开放API对象
openapi_115 = None

# Tg 用户客户端
tg_user_client: Optional[TelegramClient] = None

# aria2 客户端
aria2_client = None

# 爬取状态
CRAWL_SEHUA_STATUS = 0  # 涩花爬取状态
CRAWL_JAV_STATUS = 0    # javbee爬取状态


# yaml配置文件
CONFIG_FILE = "/config/config.yaml"
# yaml配置文件示例
CONFIG_FILE_EXAMPLE = "/config/config.yaml.example"
# 抓取策略文件
STRATEGY_FILE = "/config/crawling_strategy.yaml"
# SessionFile
TG_SESSION_FILE = "/config/user_session.session"
# DB File
DB_FILE = "/config/db.db"
# 115 Token File
TOKEN_FILE = "/config/115_tokens.json"
# APP path
APP = "/app"
# Config path
CONFIG = "/config"
# Temp path
TEMP = "/tmp"
IMAGE_PATH = "/app/images"

def _get_system_chrome_version():
    """获取系统安装的 Chrome/Chromium 版本"""
    try:
        # 1. 尝试获取 google-chrome-stable 版本
        res = subprocess.run(['google-chrome-stable', '--version'], capture_output=True, text=True, check=False)
        if res.returncode == 0:
             # Output: "Google Chrome 121.0.6167.85"
            return res.stdout.strip().split()[-1]
            
        # 2. 尝试获取 chromium 版本
        res = subprocess.run(['chromium', '--version'], capture_output=True, text=True, check=False)
        if res.returncode == 0:
            # Output: "Chromium 121.0.6167.85 ..."
            return res.stdout.strip().split()[-1]
    except Exception:
        pass
    return "143.0.0.0"  # Fallback version

# 动态获取当前环境 Chrome 版本生成 User-Agent
_chrome_ver = _get_system_chrome_version()
USER_AGENT = f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{_chrome_ver} Safari/537.36"

# 调试用
if debug_mode:
    CONFIG_FILE = "config/config.yaml"
    CONFIG_FILE_EXAMPLE = "config/config.yaml.example"
    STRATEGY_FILE = "config/crawling_strategy.yaml"
    TG_SESSION_FILE = "config/user_session.session"
    DB_FILE = "config/db.db"
    TOKEN_FILE = "config/115_tokens.json"
    APP = "app"
    CONFIG = "config"
    TEMP = "tmp"
    IMAGE_PATH = "app/images"


def create_logger():
    """
    创建全局日志对象
    :return:
    """
    global logger
    import logging
    from typing import Dict
    # 日志级别映射字典
    LOG_LEVEL_MAP: Dict[str, int] = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL
    }
    log_level = bot_config.get('log_level', 'info').lower()
    log_level = LOG_LEVEL_MAP.get(log_level, logging.INFO)
    # 全局日志实例，输出到命令行和文件
    logger = Logger(level=log_level, debug_model=debug_mode)
    
    # 屏蔽 telethon 的 INFO 日志，避免刷屏
    logging.getLogger('telethon').setLevel(logging.WARNING)
    
    logger.info("Logger init success!")


def load_yaml_config():
    """
    读取配置文件
    :return:
    """
    global bot_config, CONFIG_FILE, CONFIG_FILE_EXAMPLE, APP
    yaml_path = CONFIG_FILE
    
    example_config_path = f"{APP}/config.yaml.example"
    # 尝试更新示例配置文件
    try:
        shutil.copy2(example_config_path, CONFIG_FILE_EXAMPLE)
    except Exception as e:
        print(f"Update config example file failed: {e}")

    # 获取yaml文件名称
    try:
        # 获取yaml文件路径
        if os.path.exists(yaml_path):
            with open(yaml_path, 'r', encoding='utf-8') as f:
                cfg = f.read()
                f.close()
            bot_config = yaml.load(cfg, Loader=yaml.FullLoader)
        else:
            if os.path.exists(example_config_path):
                # 确保目标目录存在
                os.makedirs(os.path.dirname(yaml_path), exist_ok=True)
                # 复制示例配置文件
                shutil.copy2(example_config_path, yaml_path)
                print(f"已复制示例配置文件到 {yaml_path}")
                # 重新读取配置文件
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    cfg = f.read()
                    f.close()
                bot_config = yaml.load(cfg, Loader=yaml.FullLoader)
            else:
                print("Config example file not found!")
    except Exception as e:
        print(f"配置文件[{yaml_path}]格式有误，请检查!")


def get_bot_token():
    global CONFIG_FILE, bot_config
    bot_token = ""
    if 'bot_token' in bot_config.keys():
        bot_token = bot_config['bot_token']
    else:
        yaml_path = CONFIG_FILE
        if os.path.exists(yaml_path):
            with open(yaml_path, 'r', encoding='utf-8') as f:
                cfg = f.read()
                f.close()
            bot_config = yaml.load(cfg, Loader=yaml.FullLoader)
            bot_token = bot_config['bot_token']
        return bot_token

def create_tmp():
    if not os.path.exists(TEMP):
        os.mkdir(TEMP, mode=0o777)
        os.chmod(TEMP, 0o777)

def initialize_tg_usr_client():
    """
    初始化Tg用户客户端
    :return: bool - 初始化是否成功
    """
    global tg_user_client, bot_config, logger
    try:
        # 兼容老版本的配置项拼写错误
        mistake = bot_config.get('bote_name', "")
        if mistake:
            logger.warn("检测到配置项 'bote_name'（拼写错误），已自动迁移到 'bot_name'。")
            bot_config['bot_name'] = mistake
            # 清理错误的配置项
            bot_config.pop('bote_name', None)
            
        if not bot_config.get('tg_api_id') or not bot_config.get('tg_api_hash') or not bot_config.get('bot_name'):
            logger.warn("缺少必要的Telegram API配置 (tg_api_id & tg_api_hash & bot_name), 无法使用视频上传功能。")
            logger.warn("配置方法请参考：https://github.com/qiqiandfei/Telegram-115bot/wiki/VideoDownload")
            tg_user_client = None
            return False
            
        api_id = bot_config['tg_api_id']
        api_hash = bot_config['tg_api_hash']

        # 检查并验证session文件
        if not create_tg_session_file():
            logger.warn("Session文件不可用，视频上传功能将被禁用。")
            logger.warn("配置方法请参考：https://github.com/qiqiandfei/Telegram-115bot/wiki/VideoDownload")
            tg_user_client = None
            return False
        
        client_params = {
            'session': TG_SESSION_FILE,
            'api_id': api_id,
            'api_hash': api_hash
        }
        # 使用环境变量的代理设置
        http_proxy = (os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY") or "").strip()
        if http_proxy:
            import socks
            from urllib.parse import urlparse
            
            # 确保有 scheme，否则 urlparse 可能解析不准确
            target_proxy = http_proxy
            if "://" not in target_proxy:
                target_proxy = f"http://{target_proxy}"
            
            try:
                parsed = urlparse(target_proxy)
                if parsed.hostname and parsed.port:
                    # 支持用户名和密码认证
                    client_params['proxy'] = (socks.HTTP, parsed.hostname, parsed.port, True, parsed.username, parsed.password)
                    auth_info = f" (user: {parsed.username})" if parsed.username else ""
                    logger.info(f"Telegram 已启用HTTP代理: {parsed.hostname}:{parsed.port}{auth_info}")
                else:
                    logger.warn(f"环境变量代理格式无效: {http_proxy}")
            except Exception as e:
                logger.warn(f"解析代理设置失败: {e}")

        tg_user_client = TelegramClient(**client_params)
        logger.info(f"Telegram User Client 初始化成功，session路径: {TG_SESSION_FILE}")
        return True
        
    except Exception as e:
        logger.warn(f"Telegram User Client 初始化失败: {e}")
        logger.warn("配置方法请参考：https://github.com/qiqiandfei/Telegram-115bot/wiki/VideoDownload")
        tg_user_client = None
        return False
    
def initialize_115open():
    """
    初始化115开放API客户端
    :return: bool - 初始化是否成功
    """
    global openapi_115, logger
    try:
        openapi_115 = OpenAPI_115()
        # 检查是否成功获取到token
        if openapi_115.access_token and openapi_115.refresh_token:
            user_info = openapi_115.get_user_info()
            if not user_info:
                logger.error("115 OpenAPI客户端初始化失败: OpenAPI测试失败！")
                return False
            logger.info("115 OpenAPI客户端初始化成功")
            return True
        else:
            logger.error("115 OpenAPI客户端初始化失败: 无法获取有效的token")
            return False
    except Exception as e:
        logger.error(f"115 OpenAPI客户端初始化失败: {e}")
        openapi_115 = None
        return False


def check_user(user_id):
    global bot_config
    if isinstance(bot_config.get('allowed_user'), int):
        if user_id == bot_config['allowed_user']:
            return True
    if isinstance(bot_config.get('allowed_user'), str):
        if str(user_id) == bot_config['allowed_user']:
            return True
    return False

def create_tg_session_file():
    """
    创建或验证Telegram session文件
    如果session文件存在但已过期，会重新创建
    """
    tg_api_id = bot_config.get('tg_api_id', "")
    tg_api_hash = bot_config.get('tg_api_hash', "")
    
    if not (tg_api_id and tg_api_hash):
        logger.error("缺少 tg_api_id 或 tg_api_hash 配置")
        return False
    
    # 检查session文件是否存在
    if os.path.exists(TG_SESSION_FILE):
        logger.info("检测到现有session文件")
        
        # 检查session文件是否为空或损坏
        try:
            file_size = os.path.getsize(TG_SESSION_FILE)
            if file_size == 0:
                logger.warn("Session文件为空，删除并提示重新创建")
                os.remove(TG_SESSION_FILE)
            else:
                logger.info("Session文件存在且不为空，假定有效")
                return True
        except Exception as e:
            logger.error(f"检查session文件时出错: {e}")
            # 删除可能损坏的session文件
            if os.path.exists(TG_SESSION_FILE):
                os.remove(TG_SESSION_FILE)
    
    # session文件不存在或无效时的提示
    if not os.path.exists(TG_SESSION_FILE):
        logger.warn("Session文件不存在，无法使用大视频转存功能！")
        logger.warn("请手动运行 create_tg_session_file.py 脚本来创建session文件。")
        logger.warn("或者将现有的 user_session.session 文件放置到 config 目录中。")
        logger.info("注意: 如果session文件过期，在实际使用时会自动重新授权")
        return False
    
    return True

def init_aria2():
    from app.utils.aria2 import create_aria2_client
    global bot_config, aria2_client
    if not bot_config.get('aria2', {}).get('enable', False):
        logger.info("Aria2功能未启用，跳过Aria2客户端初始化。")
        aria2_client = None
        return
    aria2_client = create_aria2_client(
        host=bot_config.get('aria2').get('host', ''),
        port=bot_config.get('aria2').get('port', ''),
        secret=bot_config.get('aria2').get('rpc_secret', '')
    )
    if aria2_client:
        logger.info("Aria2客户端初始化完毕！")
    else:
        aria2_client = None

def init_db():
    with SqlLiteLib() as sqlite:
        # 创建表（如果不存在）
        # create_table_query = '''
        # CREATE TABLE IF NOT EXISTS subscribe (
        #     id INTEGER PRIMARY KEY AUTOINCREMENT,
        #     actor_name TEXT, -- 演员名称
        #     actor_id TEXT, -- 演员ID
        #     number TEXT, -- 相关编号
        #     pub_date DATETIME, -- 发布时间
        #     title TEXT, -- 标题
        #     post_url TEXT, -- 封面URL
        #     is_download TINYINT DEFAULT 0, -- 是否下载, 0或1, 默认0
        #     score REAL,
        #     magnet TEXT,
        #     sub_user INTEGER,
        #     pub_url TEXT,
        #     created_at DATETIME DEFAULT CURRENT_TIMESTAMP -- 创建时间，默认当前时间
        # );
        # '''
        # sqlite.execute_sql(create_table_query)
        create_table_query = '''
        CREATE TABLE IF NOT EXISTS offline_task (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, -- 任务标题
            save_path TEXT, -- 保存路径
            magnet TEXT, -- 磁力链接
            is_download TINYINT DEFAULT 0, -- 是否下载, 0或1, 默认0
            retry_count INTEGER DEFAULT 1, -- 重试次数
            completed_at DATETIME, -- 完成时间
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP -- 创建时间，默认当前时间
        );
        '''
        sqlite.execute_sql(create_table_query)
        
        create_table_query = """
        CREATE TABLE IF NOT EXISTS av_daily_update (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            av_number TEXT, -- 番号
            publish_date DATETIME, -- 发布时间
            title TEXT, -- 标题
            post_url TEXT, -- 封面URL
            pub_url TEXT, -- 发布链接
            magnet TEXT, -- 磁力链接
            is_download TINYINT DEFAULT 0, -- 是否下载, 0或1, 默认0
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP -- 创建时间，默认当前时间
        );
        """
        sqlite.execute_sql(create_table_query)
        
        create_table_query = '''
        CREATE TABLE IF NOT EXISTS sub_movie (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movie_name TEXT, -- 电影名称
            tmdb_id INTEGER, -- TMDB ID
            size TEXT, -- 文件大小
            category_folder TEXT, -- 分类文件夹
            is_download TINYINT DEFAULT 0, -- 是否下载, 0或1, 默认0
            download_url TEXT,  -- 下载链接, magnet, ed2k, 115share
            sub_user INTEGER,
            post_url TEXT, -- 封面URL
            is_delete TINYINT DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP -- 创建时间，默认当前时间
        );
        '''
        sqlite.execute_sql(create_table_query)
        
        create_table_query = '''
        CREATE TABLE IF NOT EXISTS sehua_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_name TEXT, -- 版块名称
            av_number TEXT, -- 番号
            title TEXT, -- 标题
            movie_type TEXT, -- 有码|无码
            size TEXT, -- 文件大小
            magnet TEXT, -- 磁力链接
            post_url TEXT, -- 封面url
            publish_date DATETIME, -- 发布时间
            pub_url TEXT, -- 资源链接
            image_path TEXT, -- 图片本地路径 
            save_path TEXT, -- 保存路径
            is_download TINYINT DEFAULT 0, -- 是否下载, 0或1, 默认0
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP -- 创建时间，默认当前时间
        );
        '''
        sqlite.execute_sql(create_table_query)
        
        create_table_query = '''
        CREATE TABLE IF NOT EXISTS t66y (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_name TEXT, -- 版块名称
            movie_info TEXT, -- 影片信息
            title TEXT, -- 标题
            magnet TEXT, -- 磁力链接
            poster_url TEXT, -- 封面url
            publish_date DATE, -- 发布日期
            pub_url TEXT, -- 资源链接
            save_path TEXT, -- 保存路径
            is_download TINYINT DEFAULT 0, -- 是否下载, 0或1, 默认0
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP -- 创建时间，默认当前时间
        );
        '''
        sqlite.execute_sql(create_table_query)
        
        create_table_query = '''
        CREATE TABLE IF NOT EXISTS javbus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            av_number TEXT, -- 番号
            actress TEXT, -- 演员，多个演员逗号分隔
            sub_category TEXT, -- 订阅类别
            movie_info TEXT, -- 影片信息
            title TEXT, -- 标题
            magnet TEXT, -- 磁力链接
            poster_url TEXT, -- 封面url
            publish_date DATE, -- 发布日期
            pub_url TEXT, -- 资源链接
            save_path TEXT, -- 保存路径
            is_download TINYINT DEFAULT 0, -- 是否下载, 0或1, 默认0
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP -- 创建时间，默认当前时间
        );
        '''
        sqlite.execute_sql(create_table_query)
        logger.info("init DataBase success.")
        

def init_log():
    create_logger()


def init():
    """
    初始化应用程序
    注意：load_model() 已经在模块导入时调用，这里不再重复调用
    """
    global bot_config, logger
    load_yaml_config()
    create_logger()
    create_tmp()
    init_db()
    initialize_tg_usr_client()
    init_aria2()

if __name__ == "__main__":
    load_yaml_config()