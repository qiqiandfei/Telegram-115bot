# -*- coding: utf-8 -*-

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, ConversationHandler, \
    MessageHandler, filters, CallbackQueryHandler
from telegram.error import TelegramError
from telegram.helpers import escape_markdown
import init
import re
import time
from pathlib import Path
from app.utils.cover_capture import get_movie_cover
from app.utils.message_queue import add_task_to_queue
from app.utils.ai import get_movie_tmdb_name_with_ai
import requests
from enum import Enum
from warnings import filterwarnings
from telegram.warnings import PTBUserWarning
from app.utils.sqlitelib import *
from concurrent.futures import ThreadPoolExecutor
from app.core.open_115 import RenameFailedError

filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)

SELECT_MAIN_CATEGORY, SELECT_SUB_CATEGORY = range(10, 12)

# 全局线程池，用于处理下载任务
download_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="Movie_Download")

class DownloadUrlType(Enum):
    ED2K = "ED2K"
    THUNDER = "thunder"
    MAGNET = "magnet"
    HTTP = "http"
    UNKNOWN = "unknown"
    
    def __str__(self):
        return self.value


async def start_d_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usr_id = update.message.from_user.id
    if not init.check_user(usr_id):
        await update.message.reply_text("⚠️ 对不起，您无权使用115机器人！")
        return ConversationHandler.END
    magnet_link = update.message.text.strip()
    context.user_data["link"] = magnet_link  # 将用户参数存储起来
    init.logger.info(f"download link: {magnet_link}")
    dl_url_type = is_valid_link(magnet_link)
    # 检查链接格式是否正确
    if dl_url_type == DownloadUrlType.UNKNOWN:
        await update.message.reply_text("⚠️ 下载链接格式错误，请修改后重试！")
        return ConversationHandler.END
    # 保存下载类型到context.user_data
    context.user_data["dl_url_type"] = dl_url_type
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
    await context.bot.send_message(chat_id=update.effective_chat.id, text="❓请选择要保存到哪个分类：",
                                   reply_markup=reply_markup)
    return SELECT_MAIN_CATEGORY


async def select_main_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    init.logger.info(f"select_main_category 收到回调: data={query.data!r}")

    query_data = query.data
    try:
        if query_data == "cancel":
            return await quit_conversation(update, context)
        elif query_data == "last_save_path":
            if hasattr(init, 'bot_session') and "movie_last_save" in init.bot_session:
                last_save_path = init.bot_session["movie_last_save"]
                link = context.user_data["link"]
                user_id = update.effective_user.id
                
                await query.edit_message_text("✅ 已为您添加到下载队列！\n请稍后~")
                
                # 使用全局线程池异步执行下载任务
                download_executor.submit(download_task, link, last_save_path, user_id)
                return ConversationHandler.END
            else:
                await query.edit_message_text("❌ 未找到最后一次保存路径，请重新选择分类")
                return ConversationHandler.END
        else:
            context.user_data["selected_main_category"] = query_data
            matched = [
                item['path_map'] for item in init.bot_config["category_folder"] if item['name'] == query_data
            ]
            if not matched:
                init.logger.error(f"未在category_folder中找到匹配项: query_data={query_data!r}, 可用name={[item.get('name') for item in init.bot_config['category_folder']]}")
                await query.edit_message_text("❌ 未找到对应的分类配置，请检查config.yaml后重试！")
                return ConversationHandler.END
            sub_categories = matched[0]

            # 创建子分类按钮
            keyboard = [
                [InlineKeyboardButton(f"📁 {category['name']}", callback_data=category['path'])] for category in sub_categories
            ]
            keyboard.append([InlineKeyboardButton("取消", callback_data="cancel")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text("❓请选择分类保存目录：", reply_markup=reply_markup)

            return SELECT_SUB_CATEGORY
    except Exception as e:
        init.logger.error(f"select_main_category 处理失败: {e}", exc_info=True)
        await query.edit_message_text("❌ 处理分类选择时出错，请重新发送磁力链接！")
        return ConversationHandler.END


async def select_sub_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    init.logger.info(f"select_sub_category 收到回调: data={query.data!r}")

    try:
        # 获取用户选择的路径
        selected_path = query.data
        # 保存最后一次选择路径
        if not hasattr(init, 'bot_session'):
            init.bot_session = {}
        init.bot_session['movie_last_save'] = selected_path
        
        if selected_path == "cancel":
            return await quit_conversation(update, context)
        link = context.user_data["link"]
        selected_main_category = context.user_data["selected_main_category"]
        user_id = update.effective_user.id
        
        await query.edit_message_text("✅ 已为您添加到下载队列！\n请稍后~")
        
        # 使用全局线程池异步执行下载任务
        download_executor.submit(download_task, link, selected_path, user_id)
        return ConversationHandler.END
    except Exception as e:
        init.logger.error(f"select_sub_category 处理失败: {e}", exc_info=True)
        await query.edit_message_text("❌ 处理保存目录时出错，请重新发送磁力链接！")
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
        DownloadUrlType.THUNDER: r'^thunder://[a-zA-Z0-9=]+',
        DownloadUrlType.HTTP: r'^(http|https)://[^\s]+$'
    }
    
    # 检查基本链接类型
    for url_type, pattern in patterns.items():
        if re.match(pattern, link):
            return url_type
        
    return DownloadUrlType.UNKNOWN


def create_strm_file(new_name, file_list):
    strm_mode = init.bot_config.get('strm_mode', 'disable')
    # 检查是否需要创建软链
    if strm_mode == "disable":
        return
    try:
        init.logger.debug(f"Original new_name: {new_name}")

        # 获取根目录
        cd2_mount_root = Path(init.bot_config.get('mount_root', '/CloudNAS/115'))
        strm_root = Path(init.bot_config.get('strm_root', '/media/115'))

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
            if strm_mode == "strm_local":
                mkv_file = cd2_mount_path / file
            else:
                mkv_file = Path(init.bot_config.get('openlist_root', '/115')) / relative_path / (Path(file))

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


def notice_emby_scan_library(path):
    strm_root = Path(init.bot_config.get("strm_root", ""))
    if not strm_root:
        init.logger.warn("未设置strm_root，无法扫库！")
        return False
    relative_path = Path(path).relative_to(Path(path).anchor)
    movie_path_in_emby = strm_root / relative_path
    emby_server = init.bot_config['emby_server']
    api_key = init.bot_config['api_key']
    if api_key is None or api_key.strip() == "" or api_key.strip().lower() == "your_api_key":
        init.logger.warn("Emby API Key 未配置，跳过通知Emby扫库")
        return False
    if str(emby_server).endswith("/"):
        emby_server = emby_server[:-1]
    url = f"{emby_server}/Library/Media/Updated"
    headers = {
        "accept": "*/*",
        "X-Emby-Token": api_key,
        "Content-Type": "application/json"
    }
    data = {
        "Updates": [
            {
                "Path": str(movie_path_in_emby),
                "UpdateType": "Created"
            }
        ]
    }
    emby_response = requests.post(url, headers=headers, json=data)
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
    
    
def download_task(link, selected_path, user_id):
    """异步下载任务"""
    from app.utils.message_queue import add_task_to_queue
    info_hash = ""
    try:
        offline_success = init.openapi_115.offline_download_specify_path(link, selected_path)
        if not offline_success:
            add_task_to_queue(user_id, f"{init.IMAGE_PATH}/male023.png", message=f"❌ 离线遇到错误！")
            return
            
        # 检查下载状态
        download_success, resource_name, info_hash = init.openapi_115.check_offline_download_success(link)
        
        if download_success:
            init.logger.info(f"✅ {resource_name} 离线下载成功！")
            time.sleep(1)
            
            # 处理下载结果
            final_path = f"{selected_path}/{resource_name}"
            if init.openapi_115.is_directory(final_path):
                # 如果下载的内容是目录，清除垃圾文件
                init.openapi_115.auto_clean_all(final_path)
            else:
                # 如果下载的内容是文件，为文件套一个文件夹
                temp_folder = Path(resource_name).stem
                init.openapi_115.create_dir_for_file(selected_path, temp_folder)
                # 移动文件到临时目录
                init.openapi_115.move_file(final_path, f"{selected_path}/{temp_folder}")
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
                [InlineKeyboardButton("指定标准的TMDB名称", callback_data=f"rename_{task_id}")],
                [InlineKeyboardButton("取消", callback_data=f"cancel_{task_id}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            movie_name = get_movie_tmdb_name_with_ai(resource_name)  # 预调用AI接口，提前准备
            if movie_name:
                message = f"✅ \\[`{resource_name}`\\]离线下载完成\\!\n\n根据AI识别，推荐的TMDB名称是：`{movie_name}`\n\n请确认！"
            else:
                message = f"✅ \\[`{resource_name}`\\]离线下载完成\\!\n\n如需削刮，请为资源指定TMDB的标准名称！"
            
            add_task_to_queue(user_id, None, message=message, keyboard=reply_markup)
            
        else:
            # 下载超时，删除任务并提供选择
            init.openapi_115.del_offline_task(info_hash)
            init.logger.warn(f"❌ {resource_name} 离线下载超时")
            
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
            message = f"`{link}`\n\n😭 离线下载超时，请选择后续操作："
            
            add_task_to_queue(user_id, None, message=message, keyboard=reply_markup)
            
    except Exception as e:
        init.logger.error(f"💀下载遇到错误: {str(e)}")
        add_task_to_queue(user_id, f"{init.IMAGE_PATH}/male023.png",
                            message=f"❌ 下载任务执行出错: {escape_markdown(str(e), version=2)}")
    finally:
        # 清除云端任务，避免重复下载
        init.openapi_115.del_offline_task(info_hash, del_source_file=0)


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
        
        
async def handle_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理取消按钮的回调"""
    query = update.callback_query
    await query.answer()
    
    try:
        # 从callback_data中提取task_id
        task_id = query.data.replace("cancel_", "")
        
        # 从全局存储中清理任务数据
        if hasattr(init, 'pending_tasks') and task_id in init.pending_tasks:
            task_data = init.pending_tasks[task_id]
            resource_name = task_data.get('resource_name', '未知资源')
            
            # 清理任务数据
            del init.pending_tasks[task_id]
            
            # 清理用户上下文中的重命名数据（如果存在）
            if "rename_data" in context.user_data:
                del context.user_data["rename_data"]
            
            await query.edit_message_text(f"✅ 已取消对资源 `{resource_name}` 的重命名操作！", parse_mode='MarkdownV2')
            init.logger.info(f"用户取消了对资源 {resource_name} 的重命名操作")
        else:
            await query.edit_message_text("✅ 重命名操作已取消！")
            
    except Exception as e:
        init.logger.error(f"处理取消重命名操作时出错: {str(e)}")
        await query.edit_message_text("✅ 重命名操作已取消！")


async def handle_manual_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理手动重命名（通过独立的消息处理器）"""
    # 检查用户是否有待处理的重命名数据
    rename_data = context.user_data.get("rename_data")
    if not rename_data:
        return
    
    # 获取重命名所需的数据
    old_resource_name = rename_data["resource_name"]
    selected_path = rename_data["selected_path"]
    download_url = rename_data["link"]
    add2retry = rename_data["add2retry"]
    final_path = rename_data["final_path"]
    
    new_resource_name = ""
    try:
        new_resource_name = update.message.text.strip()
        
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
        is_noticed = notice_emby_scan_library(new_final_path)
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
                    push2aria2(new_final_path, cover_url, message, update.effective_chat.id)
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
                push2aria2(new_final_path, cover_url, message, update.effective_chat.id)
        
        # 清除重命名数据，结束当前操作
        context.user_data.pop("rename_data", None)
        init.logger.info(f"重命名操作完成：{old_resource_name} -> {new_resource_name}")
        
    except RenameFailedError as e:
        init.logger.warn(f"捕获到重命名失败异常: {e}")
        resource_hint = new_resource_name or old_resource_name
        message = f"⚠️ 资源已存在或已入库。\n\n请直接在EMBY中搜索：{resource_hint}"
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=message
        )
        # 重命名失败时清理当前下载目录，避免留下重复资源。
        init.openapi_115.delete_single_file(final_path)
        context.user_data.pop("rename_data", None)
    except Exception as e:
        init.logger.error(f"重命名处理失败: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ 重命名失败: {str(e)}"
        )
        # 出错时也清除数据，结束当前操作
        context.user_data.pop("rename_data", None)
        
        
def push2aria2(new_final_path, cover_url, message, user_id):
    
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
        add_task_to_queue(user_id, cover_url, message=message, keyboard=reply_markup)
    else:
        add_task_to_queue(user_id, None, message=message, keyboard=reply_markup)


def register_download_handlers(application):
    # 命令形式的下载交互
    download_command_handler = ConversationHandler(
         entry_points=[
            MessageHandler(
                filters.TEXT & filters.Regex(r'^(magnet:|ed2k://|ED2K://|thunder://|http://|https://)(?!.*\n).+$'),
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
    application.add_handler(CallbackQueryHandler(handle_cancel_callback, pattern=r"^cancel_"))
    application.add_handler(CallbackQueryHandler(handle_download_failure, pattern=r"^cancel_download$"))
    
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(magnet:|ed2k://|ED2K://|thunder://|http://|https://)'), 
        handle_manual_rename
    ), group=1)
    init.logger.info("✅ Downloader处理器已注册")