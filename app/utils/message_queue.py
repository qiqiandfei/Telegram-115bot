# -*- coding: utf-8 -*-

import asyncio
import init
from telegram import Bot
from telegram.helpers import escape_markdown

# 全局消息队列
message_queue = asyncio.Queue()
# 全局变量，用于存储事件循环
global_loop = None


def add_task_to_queue(sub_user, post_url, message, keyboard=None, retry_count=0):
    """向消息队列中添加任务（线程安全）"""
    global global_loop
    if global_loop is None:
        init.logger.error("事件循环尚未启动，无法添加任务到队列")
        return False
    
    try:
        future = asyncio.run_coroutine_threadsafe(
            message_queue.put((sub_user, post_url, message, keyboard, retry_count)),
            global_loop 
        )
        future.result(timeout=30)  # 等待任务添加到队列，设置超时时间
        init.logger.debug(f"任务已添加到队列: {sub_user}, {post_url}, {message}")
        return True
    except TimeoutError:
        init.logger.error(f"添加任务到队列超时: {sub_user}, {post_url}, {message}")
        return False
    except Exception as e:
        init.logger.error(f"添加任务到队列失败: {e}")
        return False
        
        
async def queue_worker(loop, token):
    global global_loop
    """ 后台队列处理任务 """
    global_loop = loop
    # bot
    bot = Bot(token=token)
    init.logger.info("消息队列线程启动成功！")
    while True:
        try:
            # 从队列获取任务
            task_data = await message_queue.get()
            
            # 兼容不同版本的任务格式
            if len(task_data) == 3:
                # 旧版本：三参数格式
                sub_user, post_url, message = task_data
                keyboard = None
                retry_count = 0
            elif len(task_data) == 4:
                # 中版本：四参数格式
                sub_user, post_url, message, keyboard = task_data
                retry_count = 0
            else:
                # 新版本：五参数格式（带重试计数）
                sub_user, post_url, message, keyboard, retry_count = task_data
                
            retry_suffix = f" (重试 {retry_count}/3)" if retry_count > 0 else ""
            init.logger.info(f"从消息队列中取出任务{retry_suffix}: 用户[{sub_user}], 链接[{post_url}], 消息[{message}]")
            
            # 检查键盘数据
            if keyboard:
                init.logger.info(f"键盘数据: {keyboard}")
                # 检查callback_data长度
                for row in keyboard.inline_keyboard:
                    for button in row:
                        if button.callback_data and len(button.callback_data) > 64:
                            init.logger.error(f"按钮数据过长: {len(button.callback_data)} bytes - {button.callback_data[:100]}...")
            
            # 根据是否有图片和键盘选择发送方式
            if post_url:
                # 发送图片消息
                await bot.send_photo(
                    chat_id=sub_user,
                    photo=post_url,
                    caption=message,
                    parse_mode="MarkdownV2",
                    reply_markup=keyboard
                )
            else:
                # 发送纯文本消息
                await bot.send_message(
                    chat_id=sub_user,
                    text=message,
                    parse_mode="MarkdownV2",
                    reply_markup=keyboard
                )
                
            init.logger.info(f"消息已发送至 {sub_user}")
            # 标记任务完成
            message_queue.task_done()
            # 间隔防止速率限制
            await asyncio.sleep(3)
        except Exception as e:
            # 处理发送失败的情况
            error_msg = str(e)
            init.logger.warn(f"队列任务处理失败 (尝试 {retry_count + 1}/3): {error_msg}")
            
            try:
                # 标记当前任务完成（避免队列阻塞）
                message_queue.task_done()
                
                # 检查是否为不可重试的错误
                non_retryable_errors = [
                    "Invalid file http url specified: url host is empty",
                    "Invalid file http url specified",
                    "Bad Request: invalid file URL",
                    "Bad Request: wrong file identifier/HTTP URL specified",
                    "Forbidden: bot was blocked by the user",
                    "Bad Request: chat not found",
                    "Bad Request: user is deactivated"
                ]
                
                should_retry = True
                for non_retryable in non_retryable_errors:
                    if non_retryable in error_msg:
                        should_retry = False
                        init.logger.error(f"❌ 遇到不可重试错误，直接放弃: {error_msg}")
                        break
                
                # 检查是否需要重试
                if should_retry and retry_count < 2:  # 最多重试2次（总共3次尝试）
                    # 重新入队，增加重试计数
                    new_retry_count = retry_count + 1
                    await message_queue.put((sub_user, post_url, message, keyboard, new_retry_count))
                    init.logger.info(f"任务已重新入队，将进行第 {new_retry_count + 1} 次尝试")
                    
                    # 重试前等待一段时间（指数退避）
                    retry_delay = 5 * (2 ** retry_count)  # 5秒, 10秒, 20秒
                    await asyncio.sleep(retry_delay)
                else:
                    # 超过最大重试次数或遇到不可重试错误，记录最终失败
                    if should_retry:
                        init.logger.error(f"❌ 任务重试次数已达上限，放弃重试: 用户[{sub_user}], 错误: {error_msg}")
                    else:
                        init.logger.error(f"❌ 任务因不可重试错误直接放弃: 用户[{sub_user}], 错误: {error_msg}")
                    init.logger.error(f"❌ 失败消息内容: {message}")
                    
            except Exception as retry_error:
                init.logger.error(f"重试处理失败: {retry_error}")
        