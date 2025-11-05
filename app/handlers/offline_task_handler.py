# -*- coding: utf-8 -*-

import init
from app.utils.sqlitelib import *
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from app.utils.message_queue import add_task_to_queue
import time
from warnings import filterwarnings
from telegram.warnings import PTBUserWarning
from telegram.error import TelegramError
from app.utils.cover_capture import get_movie_cover

filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)


def get_failed_tasks():
    """获取所有失败的下载任务"""
    with SqlLiteLib() as sqlite:
        sql = "SELECT * FROM offline_task WHERE is_download = 0"
        return sqlite.query_all(sql)

def mark_task_as_completed(task_id: int):
    """标记任务为已完成"""
    with SqlLiteLib() as sqlite:
        sql = "UPDATE offline_task SET is_download = 1, completed_at = datetime('now') WHERE id = ?"
        sqlite.execute_sql(sql, (task_id,))
        
def update_retry_time(task_id: int):
    """更新重试次数"""
    with SqlLiteLib() as sqlite:
        sql = "UPDATE offline_task SET retry_count = retry_count + 1 WHERE id = ?"
        sqlite.execute_sql(sql, (task_id,))
        
def clear_failed_tasks():
    """清空所有失败的重试任务"""
    with SqlLiteLib() as sqlite:
        sql = "DELETE FROM offline_task WHERE is_download = 0"
        sqlite.execute_sql(sql, ())
    

def try_to_offline2115_again():
    """重新尝试失败的下载任务"""
    failed_tasks = get_failed_tasks()
    if not failed_tasks:
        init.logger.info("重试列表为空，暂时没有需要重试的任务！")
        return
    
    from app.core.offline_task_retry import create_offline_url
    create_offline_url_list = create_offline_url(failed_tasks)
    for offline_tasks in create_offline_url_list:
        if not offline_tasks:
            continue
        offline_success = init.openapi_115.offline_download_specify_path(offline_tasks, failed_tasks[0]['save_path'])
        if offline_success:
            init.logger.info(f"重试任务 {offline_tasks} 添加离线成功")
        else:
            init.logger.error(f"重试任务 {offline_tasks} 添加离线失败")
        time.sleep(2)  

    time.sleep(300)  # 等待5秒，确保任务状态更新
    
    offline_task_status = init.openapi_115.get_offline_tasks()
    for failed_task in failed_tasks:
        task_id = failed_task['id']
        link = failed_task['magnet']
        title = failed_task['title']
        save_path = failed_task['save_path']
        retry_count = failed_task['retry_count']
        for task in offline_task_status:
            if task['url'] == link:
                if task['status'] == 2 and task['percentDone'] == 100:
                    resource_name = task['name']
                    init.logger.info(f"重试任务 {title} 下载完成！")
                    # 处理下载成功后的清理和重命名准备
                    if init.openapi_115.is_directory(f"{save_path}/{resource_name}"):
                        # 清除垃圾文件
                        init.openapi_115.auto_clean_all(f"{save_path}/{resource_name}")
                        old_name = f"{save_path}/{resource_name}"
                    else:
                        init.openapi_115.create_dir_for_file(f"{save_path}", "temp")
                        # 移动文件到临时目录
                        init.openapi_115.move_file(f"{save_path}", f"{save_path}/temp")
                        old_name = f"{save_path}/temp"
                    
                    # 执行重命名
                    init.openapi_115.rename(old_name, title)
                    new_final_path = f"{save_path}/{title}"
                    file_list = init.openapi_115.get_files_from_dir(new_final_path)
                    # 创建软链
                    from app.handlers.download_handler import create_strm_file, notice_emby_scan_library
                    create_strm_file(new_final_path, file_list)
                    
                    # 发送封面图片（如果有的话）
                    cover_url = ""
                    
                    # 根据分类获取封面
                    cover_url = get_movie_cover(title)
                    
                    # 检查是否为订阅内容
                    from app.core.subscribe_movie import is_subscribe, update_subscribe
                    if is_subscribe(title):
                        # 更新订阅信息
                        update_subscribe(title, cover_url, link)
                        init.logger.info(f"订阅影片[{title}]已手动下载成功！")
                    
                    # 通知Emby扫库
                    notice_emby_scan_library()
                    # 避免link过长
                    if len(link) > 600:
                        link = link[:600] + "..."
                    
                    message = f"""✅ **重试任务 `{title}` 下载成功！**

**资源名称:** `{title}`
**磁力链接:** `{link}`
**保存路径:** `{save_path}`
        """
                    if cover_url:
                        try:
                            init.logger.info(f"cover_url: {cover_url}")
                            # 发送通知给授权用户
                            add_task_to_queue(
                                init.bot_config['allowed_user'], 
                                cover_url, 
                                message=message
                            )
                        except TelegramError as e:
                            init.logger.warn(f"Telegram API error: {e}")
                        except Exception as e:
                            init.logger.warn(f"Unexpected error: {e}")
                    else:
                        add_task_to_queue(init.bot_config['allowed_user'], None, message=message)
                    
                    # 标记任务为完成
                    mark_task_as_completed(task_id)
                    
                else:
                    init.logger.warn(f"重试任务 {title} 下载超时！")
                    # 更新重试次数
                    update_retry_time(task_id)
                    # 删除失败资源
                    init.openapi_115.del_offline_task(task['info_hash'])
                break
    # 清除云端任务
    init.openapi_115.clear_cloud_task()
    


async def view_retry_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看重试任务列表"""
    retry_list = get_failed_tasks()
    if not retry_list:
        await update.message.reply_text("🈳当前重试列表为空")
        return
   
    retry_text = "**重试列表：**\n\n"
    for i, task in enumerate(retry_list):
        # 使用magnet字段显示，因为offline_task表中可能没有title字段
        retry_text += f"{i + 1}\\. `{task['title']}`\n"
    
    # 显示重试任务列表
    keyboard = [
        [InlineKeyboardButton("清空所有", callback_data="clear_all")],
        [InlineKeyboardButton("返回", callback_data="return")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(retry_text, reply_markup=reply_markup, parse_mode='MarkdownV2')
    
    
async def handle_clear_retry_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理清空重试列表的回调"""
    query = update.callback_query
    await query.answer()
    callback_data = query.data
    
    if callback_data == "clear_all":
        clear_failed_tasks()
        await query.edit_message_text("✅ 重试列表已清空！")
    elif callback_data == "return":
        await query.edit_message_text("操作已取消")


def register_offline_task_handlers(application):
    """注册离线任务处理器"""
    # 添加独立的命令处理器用于查看重试列表
    application.add_handler(CommandHandler("rl", view_retry_list))
    
    # 添加独立的清空重试列表处理器
    application.add_handler(CallbackQueryHandler(handle_clear_retry_list, pattern="^(clear_all|return)$"))
    init.logger.info("✅ Offline Task处理器已注册")