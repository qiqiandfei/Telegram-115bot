# -*- coding: utf-8 -*-

import json
import os
import time
import asyncio
import threading
from telegram import Update, BotCommand
from telegram.ext import ContextTypes, CommandHandler, Application, TypeHandler
from telegram.request import HTTPXRequest
from telegram.helpers import escape_markdown

# 导入init模块（此时__init__.py已经设置了模块路径）
import init

from app.utils.message_queue import add_task_to_queue, queue_worker
from app.handlers.auth_handler import register_auth_handlers
from app.handlers.download_handler import register_download_handlers
from app.handlers.sync_handler import register_sync_handlers
from app.handlers.video_handler import register_video_handlers
from app.core.scheduler import start_scheduler_in_thread
from app.handlers.subscribe_movie_handler import register_subscribe_movie_handlers
from app.handlers.av_download_handler import register_av_download_handlers
from app.handlers.offline_task_handler import register_offline_task_handlers
from app.handlers.aria2_handler import register_aria2_handlers
from app.handlers.crawl_handler import register_crawl_handlers
from app.handlers.rss_handler import register_rss_handlers


def get_version(md_format=False):
    version = "v3.4.5"
    if md_format:
        return escape_markdown(version, version=2)
    return version

def get_help_info():
    version = get_version()
    help_info = f"""
<b>🍿 Telegram-115Bot {version} 使用手册</b>\n\n
<b>🔧 命令列表</b>\n
<code>/start</code> - 显示帮助信息\n
<code>/auth</code> - <i>115扫码授权 (解除授权后使用)</i>\n
<code>/reload</code> - <i>重载配置</i>\n
<code>/rl</code> - 查看重试列表\n
<code>/av</code> - <i>下载番号资源 (自动匹配磁力)</i>\n
<code>/csh</code> - <i>手动爬取涩花数据</i>\n
<code>/cjav</code> - <i>手动爬取javbee数据</i>\n
<code>/rss</code> - <i>rss订阅</i>\n
<code>/sync</code> - 同步目录并创建软链\n
<code>/q</code> - 取消当前会话\n\n
<b>✨ 功能说明</b>\n
<u>电影下载：</u>
• 直接输入下载链接，支持磁力/ed2k/迅雷
• 离线超时可选择添加到重试列表
• 根据配置自动生成 <code>.strm</code> 软链文件\n
<u>重试列表：</u>
• 输入 <code>"/rl"</code>
• 查看当前重试列表，可根据需要选择是否清空\n
<u>AV下载：</u>
• 输入 <code>"/av 番号"</code>
• 支持批量下载，一行一个链接
• 支持接收txt文件下载，文件内容每行一个链接
• 自动检索磁力并离线,默认不生成软链（建议使用削刮工具生成软链）\n
<u>手动爬取涩花：</u>
• 输入 <code>"/csh"</code>
• 基于版块配置，爬取涩花昨日数据！\n
<u>手动爬取javbee：</u>
• 输入 <code>"/cjav yyyymmdd"</code>
• 日期格式为 <code>yyyymmdd</code>，例如：20250808
• 留空则默认爬取昨日数据\n
<u>RSS订阅：</u>
• 输入 <code>"/rss"</code>
• 将rsshub地址配置到config.yaml中
• 选择RSS类别并订阅\n
<u>目录同步：</u>
• 输入 <code>"/sync"</code>
• 选择目录后会在对应的目录创建strm软链\n
<u>视频下载：</u>
• 直接转发视频给机器人，选择保存目录即可保存到115
"""
    return help_info

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_info = get_help_info()
    await context.bot.send_message(chat_id=update.effective_chat.id, text=help_info, parse_mode="html", disable_web_page_preview=True)
    
async def reload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init.load_yaml_config()
    init.logger.info("Reload configuration success:")
    init.logger.info(json.dumps(init.bot_config))
    await context.bot.send_message(chat_id=update.effective_chat.id, text="🔁重载配置完成！", parse_mode="html")

def start_async_loop():
    """启动异步事件循环的线程"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    init.logger.info("事件循环已启动")
    try:
        token = init.bot_config['bot_token']
        loop.create_task(queue_worker(loop, token))
        loop.run_forever()
    except Exception as e:
        init.logger.error(f"事件循环异常: {e}")
    finally:
        loop.close()
        init.logger.info("事件循环已关闭")

def send_start_message():
    version = get_version()  
    if init.openapi_115 is None:
        return
    
    line1, line2, line3, line4 = init.openapi_115.welcome_message()
    if not line1:
        return
    line5 = escape_markdown(f"Telegram-115Bot {version} 启动成功！", version=2)
    if line1 and line2 and line3 and line4:
        formatted_message = f"""
{line1}
{line2}
{line3}
{line4}

{line5}

发送 `/start` 查看操作说明"""
        
        add_task_to_queue(
            init.bot_config['allowed_user'], 
            f"{init.IMAGE_PATH}/neuter010.png", 
            message=formatted_message
        )


def update_logger_level():
    import logging
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('telegram.ext.Application').setLevel(logging.WARNING)
    logging.getLogger('telegram.ext.Updater').setLevel(logging.WARNING)
    logging.getLogger('telegram.Bot').setLevel(logging.WARNING)
    
def get_bot_menu():
    return  [
        BotCommand("start", "获取帮助信息"),
        BotCommand("auth", "115扫码授权"),
        BotCommand("reload", "重载配置"),
        BotCommand("rl", "查看重试列表"),
        BotCommand("av", "指定番号下载"),
        BotCommand("csh", "手动爬取涩花数据"),
        BotCommand("cjav", "手动爬取javbee数据"),
        BotCommand("rss", "RSS订阅"),
        BotCommand("sync", "同步指定目录，并创建软链"),
        BotCommand("q", "退出当前会话")]
    

async def set_bot_menu(application):
    """异步设置Bot菜单"""
    try:
        await application.bot.set_my_commands(get_bot_menu())
        init.logger.info("Bot菜单命令已设置!")
    except Exception as e:
        init.logger.error(f"设置Bot菜单失败: {e}")

async def post_init(application):
    """应用初始化后的回调"""
    await set_bot_menu(application)


async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    """全局错误处理器，避免异常仅被静默记录而无法感知问题"""
    import traceback
    error_details = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    init.logger.error(f"处理更新时发生异常: {context.error}\n{error_details}")


async def log_raw_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """最先执行的原始更新日志，用于确认Telegram是否把该更新投递给了机器人（排查按钮点击无反应问题）"""
    if update.callback_query:
        init.logger.info(
            f"[RAW UPDATE] callback_query: data={update.callback_query.data!r}, "
            f"chat_id={update.effective_chat.id if update.effective_chat else None}, "
            f"user_id={update.effective_user.id if update.effective_user else None}"
        )


def build_bot_request():
    """构造Bot API请求客户端；proxy仅在配置了HTTP_PROXY/HTTPS_PROXY时生效，否则直连"""
    import httpx
    proxy = (os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY") or "").strip() or None
    return HTTPXRequest(
        connection_pool_size=8,
        proxy=proxy,
        connect_timeout=10,
        read_timeout=20,
        write_timeout=20,
        pool_timeout=10,
        # 主动回收长时间空闲的keep-alive连接，避免复用到被网关判定为失效的连接而报502 Bad Gateway
        httpx_kwargs={"limits": httpx.Limits(max_keepalive_connections=8, max_connections=16, keepalive_expiry=15.0)},
    )


if __name__ == '__main__':
    init.init()
    # 启动消息队列
    message_thread = threading.Thread(target=start_async_loop, daemon=True)
    message_thread.start()
    # 等待消息队列准备就绪
    import app.utils.message_queue as message_queue
    max_wait = 30  # 最多等待30秒
    wait_count = 0
    while True:
        if message_queue.global_loop is not None:
            init.logger.info("消息队列线程已准备就绪！")
            break
        time.sleep(1)
        wait_count += 1
        if wait_count >= max_wait:
            init.logger.error("消息队列线程未准备就绪，程序将退出。")
            exit(1)
    init.logger.info("Starting bot with configuration:")
    init.logger.info(json.dumps(init.bot_config))
    # 调整telegram日志级别
    update_logger_level()
    token = init.bot_config['bot_token']
    application = (
        Application.builder()
        .token(token)
        .request(build_bot_request())
        .get_updates_request(build_bot_request())
        .concurrent_updates(4)  # 避免单个耗时任务（如网络抖动）阻塞其它按钮/命令的响应
        .post_init(post_init)
        .build()
    )
    application.add_error_handler(on_error)
    # 优先级最高的原始回调日志，排查按钮点击是否真的被投递到了机器人
    application.add_handler(TypeHandler(Update, log_raw_update), group=-1)

    # 启动帮助
    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)
    # 重载配置
    reload_handler = CommandHandler('reload', reload)
    application.add_handler(reload_handler)
    
    # 初始化115open对象
    if not init.initialize_115open():
        init.logger.error("115 OpenAPI客户端初始化失败，程序无法继续运行！")
        add_task_to_queue(
            init.bot_config['allowed_user'], 
            f"{init.IMAGE_PATH}/male023.png", 
            message="❌ 115 OpenAPI客户端初始化失败，程序无法继续运行！\n请检查Token或115 AppID设置是否正确！"
        )
        # 等待消息队列处理完毕再退出
        while not message_queue.message_queue.empty():
            time.sleep(5)
        time.sleep(30)
        exit(1)


    # 注册Auth
    register_auth_handlers(application)
    # 注册下载
    register_download_handlers(application)
    # 注册电影订阅 
    # register_subscribe_movie_handlers(application)
    # 注册AV下载
    register_av_download_handlers(application)
    # 注册离线任务
    register_offline_task_handlers(application)
    # 注册Aria2
    register_aria2_handlers(application)
    # 手动爬虫
    register_crawl_handlers(application)
    # 注册RSS订阅
    register_rss_handlers(application)
    # 注册同步
    register_sync_handlers(application)
    # 注册视频
    register_video_handlers(application)
    
    init.logger.info(f"USER_AGENT: {init.USER_AGENT}")

    # 启动机器人轮询
    try:
        # 启动订阅线程
        start_scheduler_in_thread()
        init.logger.info("订阅线程启动成功！")
        time.sleep(3)  # 等待订阅线程启动
        send_start_message()
        # 显式声明接收所有更新类型，避免Telegram服务端沿用此前setWebhook/getUpdates时限制的allowed_updates，
        # 导致callback_query（按钮点击）等更新被服务端静默丢弃、机器人完全收不到
        application.run_polling(allowed_updates=Update.ALL_TYPES)  # 阻塞运行
    except KeyboardInterrupt:
        init.logger.info("程序已被用户终止（Ctrl+C）。")
    except SystemExit:
        init.logger.info("程序正在退出。")
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()  # 获取完整的异常堆栈信息
        init.logger.error(f"程序遇到错误：{str(e)}\n{error_details}")
    finally:
        init.logger.info("机器人已停止运行。")