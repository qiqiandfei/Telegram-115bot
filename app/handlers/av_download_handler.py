# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.error import TelegramError
import time
import init
from app.utils.message_queue import add_task_to_queue
import re
from concurrent.futures import ThreadPoolExecutor
from app.utils.cover_capture import get_av_cover
from telegram.helpers import escape_markdown

# 全局线程池，用于处理下载任务
download_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="AV_Download")



SELECT_MAIN_CATEGORY, SELECT_SUB_CATEGORY = range(60, 62)

async def start_av_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usr_id = update.message.from_user.id
    if not init.check_user(usr_id):
        await update.message.reply_text("⚠️ 对不起，您无权使用115机器人！")
        return ConversationHandler.END

    if context.args:
        av_number = " ".join(context.args)
        context.user_data["av_number"] = av_number  # 将用户参数存储起来
    else:
        await update.message.reply_text("⚠️ 请在'/av '命令后输入车牌！")
        return ConversationHandler.END
    # 显示主分类（电影/剧集）
    keyboard = [
        [InlineKeyboardButton(f"📁 {category['display_name']}", callback_data=category['name'])] for category in
        init.bot_config['category_folder']
    ]
    # 只在有最后保存路径时才显示该选项
    if hasattr(init, 'bot_session') and "av_last_save" in init.bot_session:
        last_save_path = init.bot_session['av_last_save']
        keyboard.append([InlineKeyboardButton(f"📁 上次保存: {last_save_path}", callback_data="last_save_path")])
    keyboard.append([InlineKeyboardButton("取消", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="❓请选择要保存到哪个分类：",
                                   reply_markup=reply_markup)
    return SELECT_MAIN_CATEGORY


async def start_batch_download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usr_id = update.message.from_user.id
    if not init.check_user(usr_id):
        await update.message.reply_text("⚠️ 对不起，您无权使用115机器人！")
        return ConversationHandler.END
    
    if not update.message or not update.message.text:
        await update.message.reply_text("⚠️ 没有检测到下载链接！")
        return ConversationHandler.END
    
    context.user_data["dl_links"] = update.message.text
    # 显示主分类（电影/剧集）
    keyboard = [
        [InlineKeyboardButton(f"📁 {category['display_name']}", callback_data=category['name'])] for category in
        init.bot_config['category_folder']
    ]
    # 只在有最后保存路径时才显示该选项
    if hasattr(init, 'bot_session') and "av_last_save" in init.bot_session:
        last_save_path = init.bot_session['av_last_save']
        keyboard.append([InlineKeyboardButton(f"📁 上次保存: {last_save_path}", callback_data="last_save_path")])
    keyboard.append([InlineKeyboardButton("取消", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="❓请选择要保存到哪个分类：",
                                   reply_markup=reply_markup)
    return SELECT_MAIN_CATEGORY

async def download_from_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usr_id = update.message.from_user.id
    if not init.check_user(usr_id):
        await update.message.reply_text(" 对不起，您无权使用115机器人！")
        return ConversationHandler.END
    if (not update.message.document or 
        not update.message.document.mime_type or 
        update.message.document.mime_type != 'text/plain'):
        await update.message.reply_text("⚠️ 请发送一个TXT文本文件，文件中每行一个下载链接！")
        return ConversationHandler.END
    
    file = await context.bot.get_file(update.message.document.file_id)
    if file.file_size > 20 * 1024 * 1024:  # 20MB
        await update.message.reply_text("⚠️ 文件太大，请发送小于20MB的文件！")
        return ConversationHandler.END
     # 下载文件
    file_content = await file.download_as_bytearray()
    text_content = file_content.decode('utf-8', errors='ignore')
    # 提取每行的链接
    links = check_file(text_content)
    context.user_data["dl_links"] = links
    # 显示主分类（电影/剧集）
    keyboard = [
        [InlineKeyboardButton(f"📁 {category['display_name']}", callback_data=category['name'])] for category in
        init.bot_config['category_folder']
    ]
    # 只在有最后保存路径时才显示该选项
    if hasattr(init, 'bot_session') and "av_last_save" in init.bot_session:
        last_save_path = init.bot_session['av_last_save']
        keyboard.append([InlineKeyboardButton(f"📁 上次保存: {last_save_path}", callback_data="last_save_path")])
    keyboard.append([InlineKeyboardButton("取消", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="❓请选择要保存到哪个分类：",
                                   reply_markup=reply_markup)
    return SELECT_MAIN_CATEGORY


async def select_main_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_main_category = query.data
    if selected_main_category == "cancel":
        return await quit_conversation(update, context)
    elif selected_main_category == "last_save_path":
        # 直接使用最后一次保存的路径
        if hasattr(init, 'bot_session') and "av_last_save" in init.bot_session:
            last_path = init.bot_session['av_last_save']
            # 批量磁力下载
            if "dl_links" in context.user_data:
                magnet_links = context.user_data["dl_links"]
                await query.edit_message_text(f"✅ 已为您添加{len(magnet_links.splitlines())}个链接到下载队列！\n请稍后...")
                download_executor.submit(batch_download_task, magnet_links, last_path, user_id)
                return ConversationHandler.END
            else:
                av_number = context.user_data["av_number"]
                context.user_data["selected_path"] = last_path
                user_id = update.effective_user.id
                
                # 抓取磁力
                await query.edit_message_text(f"🔍 正在搜索 [{av_number}] 的磁力链接...")
                av_result = get_av_result(av_number)
                
                if not av_result:
                    await query.edit_message_text(f"😵‍💫很遗憾，没有找到{av_number.upper()}的对应磁力~")
                    return ConversationHandler.END
                
                # 立即反馈用户
                await query.edit_message_text(f"✅ [{av_number}] 已为您添加到下载队列！\n保存路径: {last_path}\n请稍后...")
                
                # 使用全局线程池异步执行下载任务
                download_executor.submit(download_task, av_result, av_number, last_path, user_id)
                
                return ConversationHandler.END
        else:
            await query.edit_message_text("❌ 未找到最后一次保存路径，请重新选择分类")
            return ConversationHandler.END
    else:
        context.user_data["selected_main_category"] = selected_main_category
        sub_categories = [
            item['path_map'] for item in init.bot_config["category_folder"] if item['name'] == selected_main_category
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
    if selected_path == "cancel":
        return await quit_conversation(update, context)
    
    context.user_data["selected_path"] = selected_path
    user_id = update.effective_user.id
    
    # 保存最后一次使用的路径
    if not hasattr(init, 'bot_session'):
        init.bot_session = {}
    init.bot_session['av_last_save'] = selected_path
    
    if "dl_links" in context.user_data:
        magnet_links = context.user_data["dl_links"]
        await query.edit_message_text(f"✅ 已为您添加{len(magnet_links.splitlines())}个链接到下载队列！\n请稍后...")
        download_executor.submit(batch_download_task, magnet_links, selected_path, user_id)
        return ConversationHandler.END
    else:
        av_number = context.user_data["av_number"]
        # 抓取磁力
        await query.edit_message_text(f"🔍 正在搜索 [{av_number}] 的磁力链接...")
        av_result = get_av_result(av_number)
        
        if not av_result:
            await query.edit_message_text(f"😵‍💫很遗憾，没有找到{[av_number.upper()]}的对应磁力~")
            return ConversationHandler.END
        
        # 立即反馈用户
        await query.edit_message_text(f"✅ [{av_number}] 已为您添加到下载队列！\n请稍后...")
        
        # 使用全局线程池异步执行下载任务
        download_executor.submit(download_task, av_result, av_number, selected_path, user_id)
        
        return ConversationHandler.END


async def quit_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 检查是否是回调查询
    if update.callback_query:
        await update.callback_query.edit_message_text(text="🚪用户退出本次会话")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🚪用户退出本次会话")
    return ConversationHandler.END


def get_av_result(av_number):
    result = []
    url = f"https://sukebei.nyaa.si/?q={av_number}&f=0&c=0_0"
    response = requests.get(url)
    if response.status_code != 200:
        return result
    soup = BeautifulSoup(response.text, 'html.parser')
    for tr in soup.find_all('tr', class_='default'):
        # 提取标题
        title_a = tr.find('a', href=lambda x: x and x.startswith('/view/'))
        title = title_a.get_text(strip=True) if title_a else "No title found"
        
        # 提取磁力链接
        magnet_a = tr.find('a', href=lambda x: x and x.startswith('magnet:'))
        magnet = magnet_a['href'] if magnet_a else "No magnet found"
        
        result.append({
            'title': title,
            'magnet': magnet
        })
    return result

def download_task(av_result, av_number, save_path, user_id):
    """异步下载任务"""
    magnet = ""
    info_hash = ""
    try:
        for item in av_result:
            magnet = item['magnet']
            title = item['title']
            # 离线下载到115
            offline_success = init.openapi_115.offline_download_specify_path(magnet, save_path)
            if not offline_success:
                continue
            
            # 检查下载状态
            download_success, resource_name, info_hash = init.openapi_115.check_offline_download_success(magnet)
            
            if download_success:
                init.logger.info(f"✅ {av_number} 离线下载成功！")
                
                # 按照AV番号重命名
                if resource_name != av_number.upper():
                    old_name = f"{save_path}/{resource_name}"
                    init.openapi_115.rename(old_name, av_number.upper())
                
                # 删除垃圾
                init.openapi_115.auto_clean_all(f"{save_path}/{av_number.upper()}")
                
                # 提取封面
                cover_url, title = get_av_cover(av_number.upper())
                msg_av_number = escape_markdown(f"#{av_number.upper()}", version=2)
                av_title = escape_markdown(title, version=2)
                msg_title = escape_markdown(f"[{av_number.upper()}] 下载完成", version=2)
                # 发送成功通知
                message = f"""
**{msg_title}**

**番号:** `{msg_av_number}`
**标题:** `{av_title}`
**磁力:** `{magnet}`
**保存目录:** `{save_path}/{av_number.upper()}`
                """           
                if not init.aria2_client:
                    add_task_to_queue(user_id, cover_url, message)
                else:
                    push2aria2(f"{save_path}/{av_number.upper()}", user_id, cover_url, message)
                return  # 成功后直接返回
            else:
                # 删除失败的离线任务
                init.openapi_115.del_offline_task(info_hash)
        
        # 如果循环结束都没有成功，发送失败通知
        init.logger.info(f"❌ {av_number} 所有磁力链接都下载失败")
        add_task_to_queue(user_id, None, f"❌ [{av_number}] 所有磁力链接都下载失败，请稍后重试！")
        
    except Exception as e:
        init.logger.warn(f"💀下载遇到错误: {str(e)}")
        add_task_to_queue(init.bot_config['allowed_user'], f"{init.IMAGE_PATH}/male023.png",
                            message=f"❌ 下载任务执行出错: {escape_markdown(str(e), version=2)}")
    finally:
        # 清空离线任务
        init.openapi_115.clear_cloud_task()
        
def push2aria2(save_path, user_id, cover_image, message):
    # 为Aria2推送创建任务ID系统
    import uuid
    push_task_id = str(uuid.uuid4())[:8]
    
    # 初始化pending_push_tasks（如果不存在）
    if not hasattr(init, 'pending_push_tasks'):
        init.pending_push_tasks = {}
    
    # 存储推送任务数据
    init.pending_push_tasks[push_task_id] = {
        'path': save_path
    }
    
    device_name = init.bot_config.get('aria2', {}).get('device_name', 'Aria2') or 'Aria2'
    
    keyboard = [
        [InlineKeyboardButton(f"推送到{device_name}", callback_data=f"push2aria2_{push_task_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    add_task_to_queue(user_id, cover_image, message, reply_markup)
    

def batch_download_task(magnet_links, save_path, user_id):
    """批量下载任务"""
    all_links = magnet_links.splitlines()
    valid_links = []
    for link in all_links:
        if not link.strip():
            continue
        link_type = is_valid_link(link.strip())
        if link_type != "unknown":
            valid_links.append(link.strip())
    if not valid_links:
        init.logger.warn("❌ 没有发现有效链接，请检查链接格式！")
        add_task_to_queue(user_id, f"{init.IMAGE_PATH}/male023.png", "❌ 没有发现有效链接，请检查链接格式！")
        return
    
    init.logger.info(f"发现 {len(valid_links)} 个有效链接，准备添加离线任务...")
    # 配额检查
    quota_info = init.openapi_115.get_quota_info()
    left_offline_quota = quota_info['count'] - quota_info['used']
    # 离线配额不足
    if left_offline_quota < len(valid_links):
        init.logger.warn("❌ 离线配额不足，无法添加离线任务！")
        add_task_to_queue(user_id, f"{init.IMAGE_PATH}/male023.png", "❌ 离线配额不足，无法添加离线任务！")
        return
    
    # 分割磁力，避免数量太多超过接口限制
    dl_list = split_list_compact(valid_links)
    success_append_count = 0
    # 添加到离线列表
    for sub_list in dl_list:
        offline_tasks = "\n".join(sub_list)
        # 调用115的离线下载API
        offline_success = init.openapi_115.offline_download_specify_path(offline_tasks, save_path)
        if offline_success: 
            success_append_count += len(sub_list)
        time.sleep(2)
    
    init.logger.info(f"✅ 离线任务添加成功：{success_append_count}/{len(valid_links)}")
    
    time.sleep(120)  # 等待一段时间让离线任务开始处理

    success_count = 0
    offline_task_status = init.openapi_115.get_offline_tasks()
    for link in valid_links:
        for task in offline_task_status:
            if task['url'] == link:
                if task['status'] == 2 and task['percentDone'] == 100:
                    success_count += 1
                else:
                    init.logger.warn(f"[{task['name']}] 离线下载失败或未完成!")
                    # 删除离线失败的文件
                    init.openapi_115.del_offline_task(task['info_hash'])
                break
    message = f"✅ 批量离线任务完成！\n离线成功: {success_count}/{len(valid_links)}\n保存目录: {save_path}"
    
    add_task_to_queue(user_id, f"{init.IMAGE_PATH}/male022.png", message)
    
    # 删除垃圾文件
    init.openapi_115.auto_clean_all(save_path)
    
    # 清空离线任务
    init.openapi_115.clear_cloud_task()
                    

def split_list_compact(original_list, chunk_size=100):
    """
    使用列表推导式分割列表
    """
    return [original_list[i:i + chunk_size] 
            for i in range(0, len(original_list), chunk_size)]


def is_valid_link(link: str) -> str:    
    # 定义链接模式字典
    patterns = {
        "magnet": r'^magnet:\?xt=urn:btih:([a-fA-F0-9]{40}|[a-zA-Z2-7]{32})(?:&.+)?$',
        "ed2k": r'^ed2k://\|file\|.+\|[0-9]+\|[a-fA-F0-9]{32}\|',
        "thunder": r'^thunder://[a-zA-Z0-9=]+'
    }
    
    # 检查基本链接类型
    for url_type, pattern in patterns.items():
        if re.match(pattern, link):
            return url_type

    return "unknown"

def check_file(text_content):
    links = []
    for line in text_content.splitlines():
        line = line.strip()
        if not line:
            continue
        link_type = is_valid_link(line)
        if link_type != "unknown":
            links.append(line)
    return "\n".join(links)   

def register_av_download_handlers(application):
    # download下载交互
    download_handler = ConversationHandler(
        entry_points=[CommandHandler("av", start_av_command),
                      MessageHandler(filters.TEXT & filters.Regex(r'^(magnet:|ed2k://|ED2K://|thunder://).+\n.+'), start_batch_download_command),
                      MessageHandler( filters.Document.TXT, download_from_file)],
        states={
            SELECT_MAIN_CATEGORY: [CallbackQueryHandler(select_main_category)],
            SELECT_SUB_CATEGORY: [CallbackQueryHandler(select_sub_category)]
        },
        fallbacks=[CommandHandler("q", quit_conversation)],
    )
    application.add_handler(download_handler)
    init.logger.info("✅ AV Downloader处理器已注册")
    
    