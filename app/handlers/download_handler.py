# -*- coding: utf-8 -*-

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, ConversationHandler, \
    MessageHandler, filters, CallbackQueryHandler
from telegram.error import TelegramError
import init
import re
import time
from pathlib import Path
from app.utils.cover_capture import get_movie_cover, get_av_cover
import requests
from enum import Enum
from warnings import filterwarnings
from telegram.warnings import PTBUserWarning
from app.utils.sqlitelib import *
from concurrent.futures import ThreadPoolExecutor

filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)

SELECT_MAIN_CATEGORY, SELECT_SUB_CATEGORY = range(10, 12)

# 全局线程池，用于处理下载任务
download_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="Movie_Download")

class DownloadUrlType(Enum):
    ED2K = "ED2K"
    THUNDER = "thunder"
    MAGNET = "magnet"
    UNKNOWN = "unknown"
    
    def __str__(self):
        return self.value


async def start_d_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usr_id = update.message.from_user.id
    if not init.check_user(usr_id):
        await update.message.reply_text("⚠️ 对不起，您无权使用115机器人！")
        return ConversationHandler.END

    message_text = update.message.text.strip()

    # 解析多个磁力链接（支持换行分隔）
    lines = [line.strip() for line in message_text.split('\n') if line.strip()]
    valid_links = []
    invalid_links = []

    for line in lines:
        dl_url_type = is_valid_link(line)
        if dl_url_type != DownloadUrlType.UNKNOWN:
            valid_links.append({"link": line, "type": dl_url_type})
        else:
            invalid_links.append(line)

    # 检查是否有有效链接
    if not valid_links:
        await update.message.reply_text("⚠️ 未找到有效的下载链接，请检查格式后重试！")
        return ConversationHandler.END

    # 如果有无效链接，提示用户
    if invalid_links:
        invalid_count = len(invalid_links)
        await update.message.reply_text(f"⚠️ 发现 {invalid_count} 个无效链接，将跳过处理。\n\n继续处理 {len(valid_links)} 个有效链接...")

    # 保存所有有效链接到context.user_data
    context.user_data["links"] = valid_links
    context.user_data["total_links"] = len(valid_links)
    init.logger.info(f"download links count: {len(valid_links)}")
    # 显示主分类（电影/剧集）
    keyboard = [
        [InlineKeyboardButton(f"📁 {category['display_name']}", callback_data=category['name'])] for category in
        init.bot_config['category_folder']
    ]
    # 只在有最后保存路径时才显示该选项
    if hasattr(init, 'bot_session') and "movie_last_save" in init.bot_session:
        last_save_path = init.bot_session['movie_last_save']
        keyboard.append([InlineKeyboardButton(f"📁 上次保存: {last_save_path}", callback_data="last_save_path")])
    keyboard.append([InlineKeyboardButton("取消", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    # 显示链接数量信息
    link_count = len(valid_links)
    message_text = f"📥 检测到 {link_count} 个下载链接\n\n❓请选择要保存到哪个分类："

    await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text,
                                   reply_markup=reply_markup)
    return SELECT_MAIN_CATEGORY


async def select_main_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    query_data = query.data
    if query_data == "cancel":
        return await quit_conversation(update, context)
    elif query_data == "last_save_path":
        if hasattr(init, 'bot_session') and "movie_last_save" in init.bot_session:
            last_save_path = init.bot_session["movie_last_save"]
            links = context.user_data["links"]
            user_id = update.effective_user.id
            total_count = len(links)

            await query.edit_message_text(f"✅ 已为您添加 {total_count} 个下载任务到队列！\n请稍后~")

            # 使用批量下载处理（减少API调用频率）
            download_executor.submit(download_tasks_batch, links, last_save_path, user_id)
            return ConversationHandler.END
        else:
            await query.edit_message_text("❌ 未找到最后一次保存路径，请重新选择分类")
            return ConversationHandler.END
    else:
        context.user_data["selected_main_category"] = query_data
        sub_categories = [
            item['path_map'] for item in init.bot_config["category_folder"] if item['name'] == query_data
        ][0]

        # 创建子分类按钮
        keyboard = [
            [InlineKeyboardButton(f"📁 {category['name']}", callback_data=category['path'])] for category in sub_categories
        ]
        keyboard.append([InlineKeyboardButton("取消", callback_data="cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text("❓请选择分类保存目录：", reply_markup=reply_markup)

        return SELECT_SUB_CATEGORY


async def select_sub_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # 获取用户选择的路径
    selected_path = query.data
    # 保存最后一次选择路径
    if not hasattr(init, 'bot_session'):
        init.bot_session = {}
    init.bot_session['movie_last_save'] = selected_path

    if selected_path == "cancel":
        return await quit_conversation(update, context)
    links = context.user_data["links"]
    selected_main_category = context.user_data["selected_main_category"]
    user_id = update.effective_user.id
    total_count = len(links)

    await query.edit_message_text(f"✅ 已为您添加 {total_count} 个下载任务到队列！\n请稍后~")

    # 使用批量下载处理（减少API调用频率）
    download_executor.submit(download_tasks_batch, links, selected_path, user_id)
    return ConversationHandler.END


async def handle_retry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理重试任务的回调"""
    query = update.callback_query
    await query.answer()
    
    try:
        # 从callback_data中提取task_id
        task_id = query.data.replace("retry_", "")
        
        # 从全局存储中获取任务数据
        if hasattr(init, 'pending_tasks') and task_id in init.pending_tasks:
            task_data = init.pending_tasks[task_id]
            
            # 添加到重试列表
            save_failed_download_to_db(
                task_data["resource_name"], 
                task_data["link"], 
                task_data["selected_path"]
            )
            
            await query.edit_message_text("✅ 已将失败任务添加到重试列表，系统将自动重试！")
            
            # 清理已使用的任务数据
            del init.pending_tasks[task_id]
        else:
            await query.edit_message_text("❌ 任务数据已过期")
        
    except Exception as e:
        init.logger.error(f"处理重试回调失败: {e}")
        await query.edit_message_text("❌ 添加到重试列表失败，请稍后再试")


async def handle_download_failure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理下载失败时的用户选择"""
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    
    if choice == "cancel_download":
        # 取消下载
        await query.edit_message_text("✅ 已取消，可尝试更换磁力重试！")


async def quit_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 检查是否是回调查询
    if update.callback_query:
        await update.callback_query.edit_message_text(text="🚪用户退出本次会话")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🚪用户退出本次会话")
    return ConversationHandler.END


def is_valid_link(link: str) -> DownloadUrlType:    
    # 定义链接模式字典
    patterns = {
        DownloadUrlType.MAGNET: r'^magnet:\?xt=urn:btih:([a-fA-F0-9]{40}|[a-zA-Z2-7]{32})(?:&.+)?$',
        DownloadUrlType.ED2K: r'^ed2k://\|file\|.+\|[0-9]+\|[a-fA-F0-9]{32}\|',
        DownloadUrlType.THUNDER: r'^thunder://[a-zA-Z0-9=]+'
    }
    
    # 检查基本链接类型
    for url_type, pattern in patterns.items():
        if re.match(pattern, link):
            return url_type
        
    return DownloadUrlType.UNKNOWN


def create_strm_file(new_name, file_list):
    # 检查是否需要创建软链
    if not init.bot_config['create_strm']:
        return
    try:
        init.logger.debug(f"Original new_name: {new_name}")

        # 获取根目录
        cd2_mount_root = Path(init.bot_config['mount_root'])
        strm_root = Path(init.bot_config['strm_root'])

        # 构建目标路径和 .strm 文件的路径
        relative_path = Path(new_name).relative_to(Path(new_name).anchor)
        cd2_mount_path = cd2_mount_root.joinpath(relative_path)
        strm_path = strm_root.joinpath(relative_path)

        # 日志输出以验证路径
        init.logger.debug(f"cd2_mount_root: {cd2_mount_root}")
        init.logger.debug(f"strm_root: {strm_root}")
        init.logger.debug(f"cd2_mount_path: {cd2_mount_path}")
        init.logger.debug(f"strm_path: {strm_path}")

        # 确保 strm_path 路径存在
        if not strm_path.exists():
            strm_path.mkdir(parents=True, exist_ok=True)

        # 遍历文件列表，创建 .strm 文件
        for file in file_list:
            target_file = strm_path / (Path(file).stem + ".strm")
            mkv_file = cd2_mount_path / file

            # 日志输出以验证 .strm 文件和目标文件
            init.logger.debug(f"target_file (.strm): {target_file}")
            init.logger.debug(f"mkv_file (.mp4): {mkv_file}")

            # 如果原始文件存在，写入 .strm 文件
            # if mkv_file.exists():
            with target_file.open('w', encoding='utf-8') as f:
                f.write(str(mkv_file))
                init.logger.info(f"strm文件创建成功，{target_file} -> {mkv_file}")
            # else:
            #     init.logger.info(f"原始视频文件[{mkv_file}]不存在！")
    except Exception as e:
        init.logger.info(f"Error creating .strm files: {e}")


def notice_emby_scan_library():
    emby_server = init.bot_config['emby_server']
    api_key = init.bot_config['api_key']
    if api_key is None or api_key.strip() == "" or api_key.strip().lower() == "your_api_key":
        init.logger.warn("Emby API Key 未配置，跳过通知Emby扫库")
        return False
    if str(emby_server).endswith("/"):
        emby_server = emby_server[:-1]
    url = f"{emby_server}/Library/Refresh"
    headers = {
        "X-Emby-Token": api_key
    }
    emby_response = requests.post(url, headers=headers)
    if emby_response.text == "":
        init.logger.info("通知Emby扫库成功！")
        return True
    else:
        init.logger.error(f"通知Emby扫库失败：{emby_response}")
        return False


def save_failed_download_to_db(title, magnet, save_path):
    """保存失败的下载任务到数据库"""
    try:
        with SqlLiteLib() as sqlite:
            # 检查是否已存在相同的任务
            check_sql = "SELECT * FROM offline_task WHERE magnet = ? AND save_path = ? AND title = ?"
            existing = sqlite.query_one(check_sql, (magnet, save_path, title))

            if not existing:
                sql = "INSERT INTO offline_task (title, magnet, save_path) VALUES (?, ?, ?)"
                sqlite.execute_sql(sql, (title, magnet, save_path))
                init.logger.info(f"[{title}]已添加到重试列表")
    except Exception as e:
        raise str(e)


def process_successful_download(link, selected_path, user_id, resource_name, task_index, total_count):
    """处理下载成功的任务"""
    from app.utils.message_queue import add_task_to_queue

    progress_info = f"[{task_index}/{total_count}]"
    init.logger.info(f"{progress_info} {resource_name} 开始处理下载结果")

    # 处理下载结果
    final_path = f"{selected_path}/{resource_name}"
    if init.openapi_115.is_directory(final_path):
        # 如果下载的内容是目录，清除垃圾文件
        init.openapi_115.auto_clean(final_path)
    else:
        # 如果下载的内容是文件，为文件套一个文件夹
        temp_folder = "temp"
        init.openapi_115.create_dir_for_file(selected_path, temp_folder)
        # 移动文件到临时目录
        init.openapi_115.move_file(f"{selected_path}/{resource_name}", f"{selected_path}/{temp_folder}")
        final_path = f"{selected_path}/{temp_folder}"
        resource_name = temp_folder

    # 为避免callback_data长度限制，使用时间戳作为唯一标识符
    task_id = str(int(time.time() * 1000))  # 毫秒时间戳作为唯一ID

    # 将任务数据存储到全局字典中（临时存储）
    if not hasattr(init, 'pending_tasks'):
        init.pending_tasks = {}

    init.pending_tasks[task_id] = {
        "user_id": user_id,
        "action": "manual_rename",
        "final_path": final_path,
        "resource_name": resource_name,
        "selected_path": selected_path,
        "link": link,
        "add2retry": False
    }

    # 发送下载成功通知，包含选择按钮
    keyboard = [
        [InlineKeyboardButton("指定标准的TMDB名称", callback_data=f"rename_{task_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # 添加进度信息到成功消息
    progress_text = f" {progress_info}" if total_count > 1 else ""
    message = f"✅{progress_text} 电影\\[`{resource_name}`\\]离线下载完成\\!\n\n便于削刮，请为资源指定TMDB的标准名称！"

    add_task_to_queue(user_id, None, message=message, keyboard=reply_markup)


def process_failed_download(link, selected_path, user_id, resource_name, task_index, total_count):
    """处理下载失败的任务"""
    from app.utils.message_queue import add_task_to_queue

    progress_info = f"[{task_index}/{total_count}]"

    # 下载超时，删除任务并提供选择
    init.openapi_115.clear_failed_task(link)
    timeout_message = f"❌ {progress_info} {resource_name} 离线下载超时" if resource_name else f"❌ {progress_info} 离线下载超时"
    init.logger.warn(timeout_message)

    # 为失败重试也使用时间戳ID
    retry_task_id = str(int(time.time() * 1000))

    # 将重试任务数据存储到全局字典中
    if not hasattr(init, 'pending_tasks'):
        init.pending_tasks = {}

    init.pending_tasks[retry_task_id] = {
        "user_id": user_id,
        "action": "retry_download",
        "selected_path": selected_path,
        "resource_name": resource_name if resource_name else "未知资源",
        "link": link,
        "add2retry": True
    }

    # 提供重试选项
    keyboard = [
        [InlineKeyboardButton("指定TMDB名称并添加到重试列表", callback_data=f"rename_{retry_task_id}")],
        [InlineKeyboardButton("取消", callback_data="cancel_download")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # 添加进度信息到失败消息
    failure_text = f"{progress_info} " if total_count > 1 else ""
    # 截断过长的链接
    display_link = link[:600] + "..." if len(link) > 600 else link
    message = f"`{display_link}`\n\n😭 {failure_text}离线下载超时，请选择后续操作："

    add_task_to_queue(user_id, None, message=message, keyboard=reply_markup)


def download_tasks_batch(links, selected_path, user_id):
    """批量下载任务处理（减少API调用频率）"""
    from app.utils.message_queue import add_task_to_queue

    total_count = len(links)
    init.logger.info(f"开始批量处理 {total_count} 个下载任务")

    # 第一步：批量提交所有磁力链接
    submitted_tasks = []
    for i, link_info in enumerate(links, 1):
        link = link_info["link"]
        init.logger.info(f"[{i}/{total_count}] 提交离线任务: {link[:80]}...")

        offline_success = init.openapi_115.offline_download_specify_path(link, selected_path)
        if offline_success:
            submitted_tasks.append({
                "link": link,
                "index": i,
                "submitted": True
            })
        else:
            error_message = f"❌ [{i}/{total_count}] 提交离线任务失败！"
            add_task_to_queue(user_id, f"{init.IMAGE_PATH}/male023.png", message=error_message)
            submitted_tasks.append({
                "link": link,
                "index": i,
                "submitted": False
            })
        time.sleep(2)  # 提交间隔2秒

    if not submitted_tasks:
        init.logger.error("所有任务提交失败")
        return

    # 第二步：等待固定时间（300秒 = 5分钟）
    init.logger.info(f"已提交 {len(submitted_tasks)} 个任务，等待300秒后检查状态...")
    time.sleep(300)

    # 第三步：只调用一次API获取所有任务状态
    init.logger.info("开始检查所有任务状态...")
    offline_task_status = init.openapi_115.get_offline_tasks()

    if not offline_task_status:
        init.logger.error("无法获取离线任务状态")
        add_task_to_queue(user_id, f"{init.IMAGE_PATH}/male023.png",
                         message="❌ 无法获取离线任务状态，请稍后手动检查")
        return

    # 第四步：批量处理每个任务的结果
    for task_info in submitted_tasks:
        if not task_info["submitted"]:
            continue

        link = task_info["link"]
        task_index = task_info["index"]
        progress_info = f"[{task_index}/{total_count}]"

        # 在API返回的任务列表中查找匹配的任务
        download_success = False
        resource_name = ""

        for task in offline_task_status:
            if task.get('url') == link:
                resource_name = task.get('name', '')
                if task.get('status') == 2 and task.get('percentDone') == 100:
                    download_success = True
                    init.logger.info(f"{progress_info} {resource_name} 离线下载成功！")
                else:
                    init.logger.warn(f"{progress_info} {resource_name} 离线下载超时或失败")
                break

        if download_success:
            # 处理下载成功的任务
            process_successful_download(link, selected_path, user_id, resource_name,
                                       task_index, total_count)
        else:
            # 处理下载失败的任务
            process_failed_download(link, selected_path, user_id, resource_name,
                                   task_index, total_count)

        # 添加小延时，避免时间戳ID冲突
        time.sleep(0.1)

    # 第五步：清除云端任务（批量清理一次）
    init.openapi_115.clear_cloud_task()
    init.logger.info(f"批量下载任务处理完成，共 {total_count} 个任务")


def download_task(link, selected_path, user_id, task_index=1, total_tasks=1):
    """异步下载任务（单个任务使用，已弃用，保留用于兼容）"""
    from app.utils.message_queue import add_task_to_queue

    try:
        # 添加任务进度信息到日志和通知
        progress_info = f"[{task_index}/{total_tasks}]" if total_tasks > 1 else ""
        init.logger.info(f"开始处理下载任务 {progress_info}: {link}")

        offline_success = init.openapi_115.offline_download_specify_path(link, selected_path)
        if not offline_success:
            error_message = f"❌ {progress_info} 离线遇到错误！" if progress_info else "❌ 离线遇到错误！"
            add_task_to_queue(user_id, f"{init.IMAGE_PATH}/male023.png", message=error_message)
            return

        # 检查下载状态
        download_success, resource_name = init.openapi_115.check_offline_download_success(link)

        if download_success:
            success_message = f"✅ {progress_info} {resource_name} 离线下载成功！" if progress_info else f"✅ {resource_name} 离线下载成功！"
            init.logger.info(success_message)
            time.sleep(1)
            
            # 处理下载结果
            final_path = f"{selected_path}/{resource_name}"
            if init.openapi_115.is_directory(final_path):
                # 如果下载的内容是目录，清除垃圾文件
                init.openapi_115.auto_clean(final_path)
            else:
                # 如果下载的内容是文件，为文件套一个文件夹
                temp_folder = "temp"
                init.openapi_115.create_dir_for_file(selected_path, temp_folder)
                # 移动文件到临时目录
                init.openapi_115.move_file(f"{selected_path}/{resource_name}", f"{selected_path}/{temp_folder}")
                final_path = f"{selected_path}/{temp_folder}"
                resource_name = temp_folder
            
            # 为避免callback_data长度限制，使用时间戳作为唯一标识符
            task_id = str(int(time.time() * 1000))  # 毫秒时间戳作为唯一ID
            
            # 将任务数据存储到全局字典中（临时存储）
            if not hasattr(init, 'pending_tasks'):
                init.pending_tasks = {}
            
            init.pending_tasks[task_id] = {
                "user_id": user_id,
                "action": "manual_rename", 
                "final_path": final_path,
                "resource_name": resource_name,
                "selected_path": selected_path,
                "link": link,
                "add2retry": False
            }
            
            # 发送下载成功通知，包含选择按钮
            keyboard = [
                [InlineKeyboardButton("指定标准的TMDB名称", callback_data=f"rename_{task_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # 添加进度信息到成功消息
            progress_text = f" {progress_info}" if progress_info else ""
            message = f"✅{progress_text} 电影\\[`{resource_name}`\\]离线下载完成\\!\n\n便于削刮，请为资源指定TMDB的标准名称！"

            add_task_to_queue(user_id, None, message=message, keyboard=reply_markup)
            
        else:
            # 下载超时，删除任务并提供选择
            init.openapi_115.clear_failed_task(link)
            timeout_message = f"❌ {progress_info} {resource_name} 离线下载超时" if progress_info else f"❌ {resource_name} 离线下载超时"
            init.logger.warn(timeout_message)
            
            # 为失败重试也使用时间戳ID
            retry_task_id = str(int(time.time() * 1000))
            
            # 将重试任务数据存储到全局字典中
            if not hasattr(init, 'pending_tasks'):
                init.pending_tasks = {}
                
            init.pending_tasks[retry_task_id] = {
                "user_id": user_id,
                "action": "retry_download",
                "selected_path": selected_path,
                "resource_name": resource_name,
                "link": link,
                "add2retry": True
            }
            
            # 提供重试选项
            keyboard = [
                [InlineKeyboardButton("指定TMDB名称并添加到重试列表", callback_data=f"rename_{retry_task_id}")],
                [InlineKeyboardButton("取消", callback_data="cancel_download")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # 添加进度信息到失败消息
            failure_text = f"{progress_info} " if progress_info else ""
            message = f"`{link}`\n\n😭 {failure_text}离线下载超时，请选择后续操作："

            add_task_to_queue(user_id, None, message=message, keyboard=reply_markup)
            
    except Exception as e:
        error_msg = f"💀{progress_info} 下载遇到错误: {str(e)}" if progress_info else f"💀下载遇到错误: {str(e)}"
        init.logger.error(error_msg)

        user_error_msg = f"❌ {progress_info} 下载任务执行出错: {str(e)}" if progress_info else f"❌ 下载任务执行出错: {str(e)}"
        add_task_to_queue(user_id, f"{init.IMAGE_PATH}/male023.png", message=user_error_msg)
    finally:
        # 清除云端任务，避免重复下载
        init.openapi_115.clear_cloud_task()


async def handle_manual_rename_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理手动重命名的回调"""
    query = update.callback_query
    await query.answer()
    
    try:
        # 从callback_data中提取task_id
        task_id = query.data.replace("rename_", "")
        
        # 从全局存储中获取任务数据
        if hasattr(init, 'pending_tasks') and task_id in init.pending_tasks:
            task_data = init.pending_tasks[task_id]
            
            # 将数据保存到用户上下文中（用于后续的重命名操作）
            context.user_data["rename_data"] = task_data

            await query.edit_message_text(f"`{task_data['resource_name']}`\n\n📝 请直接回复TMDB标准名称进行重命名：\n\\(点击资源名称自动复制\\)", parse_mode='MarkdownV2')

            # 清理已使用的任务数据
            del init.pending_tasks[task_id]
        else:
            await query.edit_message_text("❌ 任务数据已过期，请重新下载")
        
    except Exception as e:
        init.logger.error(f"处理手动重命名回调失败: {e}")
        await query.edit_message_text("❌ 处理失败，请稍后再试")


async def handle_manual_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理手动重命名（通过独立的消息处理器）"""
    # 检查用户是否有待处理的重命名数据
    rename_data = context.user_data.get("rename_data")
    if not rename_data:
        return
    
    try:
        new_resource_name = update.message.text.strip()
        
        # 获取重命名所需的数据
        final_path = rename_data["final_path"]
        old_resource_name = rename_data["resource_name"]
        selected_path = rename_data["selected_path"]
        download_url = rename_data["link"]
        add2retry = rename_data["add2retry"]
        
        # 添加到重试列表
        if add2retry:
            save_failed_download_to_db(
                new_resource_name, 
                download_url, 
                selected_path
            )
            await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ 已将失败任务添加到重试列表，系统将自动重试！")
            context.user_data.pop("rename_data", None)
            return

        # 执行重命名
        init.openapi_115.rename(final_path, new_resource_name)
        
        # 构建新的路径
        new_final_path = f"{selected_path}/{new_resource_name}"
        
        # 获取文件列表并创建STRM文件
        file_list = init.openapi_115.get_files_from_dir(new_final_path)
        create_strm_file(new_final_path, file_list)
        
        # 发送封面图片（如果有的话）
        cover_url = ""
        
        # 根据分类获取封面
        cover_url = get_movie_cover(new_resource_name)
        
        # 检查是否为订阅内容
        from app.core.subscribe_movie import is_subscribe, update_subscribe
        if is_subscribe(new_resource_name):
            # 更新订阅信息
            update_subscribe(new_resource_name, cover_url, download_url)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"💡订阅影片`{new_resource_name}`已手动下载成功\\！",
                parse_mode='MarkdownV2'
            )
        
        # 通知Emby扫库
        is_noticed = notice_emby_scan_library()
        if is_noticed:
            message = f"✅ 重命名成功：`{new_resource_name}`\n\n**👻 已通知Emby扫库，请稍后确认！**"
        else:
            message = f"✅ 重命名成功：`{new_resource_name}`\n\n**⚠️ 未能通知Emby，请先配置'EMBY API KEY'！**"
        if cover_url:
            try:
                init.logger.info(f"cover_url: {cover_url}")
                
                if not init.aria2_client:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id, 
                        photo=cover_url, 
                        caption=message,
                        parse_mode='MarkdownV2'
                    )
                else:
                    # 推送到aria2
                   await push2aria2(new_final_path, cover_url, message, update, context)
            except TelegramError as e:
                init.logger.warn(f"Telegram API error: {e}")
            except Exception as e:
                init.logger.warn(f"Unexpected error: {e}")
        else:
            if not init.aria2_client:
                await context.bot.send_message(
                                                chat_id=update.effective_chat.id,
                                                text=message,
                                                parse_mode='MarkdownV2'
                )
            else:
                # 推送到aria2
                await push2aria2(new_final_path, cover_url, message, update, context)
        
        # 清除重命名数据，结束当前操作
        context.user_data.pop("rename_data", None)
        init.logger.info(f"重命名操作完成：{old_resource_name} -> {new_resource_name}")
        
    except Exception as e:
        init.logger.error(f"重命名处理失败: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ 重命名失败: {str(e)}"
        )
        # 出错时也清除数据，结束当前操作
        context.user_data.pop("rename_data", None)
        
        
async def push2aria2(new_final_path, cover_url, message, update, context):
    
    # 为Aria2推送创建任务ID系统
    import uuid
    push_task_id = str(uuid.uuid4())[:8]
    
    # 初始化pending_push_tasks（如果不存在）
    if not hasattr(init, 'pending_push_tasks'):
        init.pending_push_tasks = {}
    
    # 存储推送任务数据
    init.pending_push_tasks[push_task_id] = {
        'path': new_final_path
    }
    
    device_name = init.bot_config.get('aria2', {}).get('device_name', 'Aria2') or 'Aria2'
    
    keyboard = [
        [InlineKeyboardButton(f"推送到{device_name}", callback_data=f"push2aria2_{push_task_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if cover_url:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id, 
            photo=cover_url, 
            caption=message,
            parse_mode='MarkdownV2',
            reply_markup=reply_markup
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=message,
            parse_mode='MarkdownV2',
            reply_markup=reply_markup
        )


def register_download_handlers(application):
    # 命令形式的下载交互
    download_command_handler = ConversationHandler(
        # entry_points=[CommandHandler("dl", start_d_command)],
         entry_points=[
            MessageHandler(
                filters.TEXT & filters.Regex(r'^(magnet:|ed2k://|ED2K://|thunder://)'),
                start_d_command
            )
        ],
        states={
            SELECT_MAIN_CATEGORY: [CallbackQueryHandler(select_main_category)],
            SELECT_SUB_CATEGORY: [CallbackQueryHandler(select_sub_category)]
        },
        fallbacks=[CommandHandler("q", quit_conversation)],
    )
    application.add_handler(download_command_handler)
    
    # 添加独立的回调处理器处理异步任务的后续操作
    application.add_handler(CallbackQueryHandler(handle_manual_rename_callback, pattern=r"^rename_"))
    application.add_handler(CallbackQueryHandler(handle_retry_callback, pattern=r"^retry_"))
    application.add_handler(CallbackQueryHandler(handle_download_failure, pattern=r"^cancel_download$"))
    
    # 添加消息处理器处理重命名输入（使用较低优先级的组别）
    # group=1 表示优先级低于默认的 group=0
    # application.add_handler(MessageHandler(
    #     filters.TEXT & ~filters.COMMAND, 
    #     handle_manual_rename
    # ), group=1)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(magnet:|ed2k://|ED2K://|thunder://)'), 
        handle_manual_rename
    ), group=1)
    init.logger.info("✅ Downloader处理器已注册")