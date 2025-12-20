# -*- coding: utf-8 -*-

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, ConversationHandler, \
    MessageHandler, filters, CallbackQueryHandler
import init
import os
import shutil
from datetime import datetime
from pathlib import Path
import hashlib
from warnings import filterwarnings
from telegram.warnings import PTBUserWarning

filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)
# 过滤 Telethon 的异步会话实验性功能警告
filterwarnings(action="ignore", message="Using async sessions support is an experimental feature")


SELECT_MAIN_CATEGORY_VIDEO, SELECT_SUB_CATEGORY_VIDEO = range(20, 22)


async def save_video2115(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usr_id = update.message.from_user.id
    if not init.check_user(usr_id):
        await update.message.reply_text("⚠️ 对不起，您无权使用115机器人！")
        return ConversationHandler.END
    
    if not init.tg_user_client:
        await update.message.reply_text("⚠️ 如需使用此功能，请先配置[bot_name],[tg_app_id]和[tg_app_hash]！")
        return ConversationHandler.END

    # 检查和建立 Telegram 用户客户端连接
    try:
        init.logger.info("🔄 正在验证 Telegram 用户客户端连接...")
        # 尝试连接
        await init.tg_user_client.connect()
        
        # 检查是否已授权
        if not await init.tg_user_client.is_user_authorized():
            await update.message.reply_text(
                "❌ Telegram 用户客户端未授权或session已过期！\n"
                "请重新运行 create_tg_session_file.py 脚本进行授权，\n"
                "或将有效的 user_session.session 文件放置到 config 目录中。"
            )
            return ConversationHandler.END
        
        init.logger.info("✅ Telegram 用户客户端连接验证成功")
        
    except Exception as e:
        init.logger.error(f"Telegram 用户客户端连接失败: {e}")
        await update.message.reply_text(
            f"❌ Telegram 用户客户端连接失败: {str(e)}\n"
            "可能的原因：\n"
            "1. Session 文件已过期\n"
            "2. API 配置错误\n"
            "3. 网络连接问题\n"
            "请检查配置并重新创建 session 文件。"
        )
        return ConversationHandler.END

    if update.message and update.message.video:
        video = update.message.video
        context.user_data['video'] = {
            "file_name": video.file_name if video.file_name else None,
            "file_size": video.file_size,
            "duration": video.duration,
            "width": video.width,
            "height": video.height,
            "file_id": video.file_id
        }
        # 显示主分类（电影/剧集）
        keyboard = [
            [InlineKeyboardButton(f"📁 {category['display_name']}", callback_data=category['name'])] for category in
            init.bot_config['category_folder']
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="❓请选择要保存到哪个分类：",
                                       reply_markup=reply_markup)
        return SELECT_MAIN_CATEGORY_VIDEO


async def select_main_category_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_main_category = query.data
    if selected_main_category == "return":
        # 显示主分类
        keyboard = [
            [InlineKeyboardButton(f"📁 {category['display_name']}", callback_data=category['name'])]
            for category in init.bot_config['category_folder']
        ]
        keyboard.append([InlineKeyboardButton("退出", callback_data="quit")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                    text="❓请选择要保存到哪个分类：",
                                    reply_markup=reply_markup)
        return SELECT_MAIN_CATEGORY_VIDEO
    else:
        context.user_data["selected_main_category"] = selected_main_category
        sub_categories = [
            item['path_map'] for item in init.bot_config["category_folder"] if item['name'] == selected_main_category
        ][0]

        # 创建子分类按钮
        keyboard = [
            [InlineKeyboardButton(f"📁 {category['name']}", callback_data=category['path'])] for category in sub_categories
        ]
        keyboard.append([InlineKeyboardButton("返回", callback_data="return")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("❓请选择分类保存目录：", reply_markup=reply_markup)
        return SELECT_SUB_CATEGORY_VIDEO
    

async def select_sub_category_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # 获取用户选择的路径
    selected_path = query.data
    if selected_path == "return":
        return await select_main_category_video(update, context)
    if selected_path == "quit":
        return await quit_conversation(update, context)
    
    # 取存储好的视频信息
    video = context.user_data["video"]
    file_name = video.get("file_name")
    video_size = video.get("file_size", 0)
    
    if not file_name:
        file_name = datetime.now().strftime("%Y%m%d%H%M%S") + ".mp4"
    file_path = f"{init.TEMP}/{file_name}"

    # 显示视频信息和开始下载
    video_info = f"😼 收到视频文件: {file_name}\n"
    video_info += f"大小: {format_file_size(video_size)}\n"
    video_info += f"正在准备下载..."
    
    await query.edit_message_text(text=video_info)
    
    try:
        # 获取最后一条视频消息（连接已在 save_video2115 中验证）
        msgs = await init.tg_user_client.get_messages(init.bot_config['bot_name'], limit=5)
        target_msg = None
        for msg in msgs:
            if msg.media:
                target_msg = msg
                break
        
        if not target_msg:
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text="❌ 未找到可下载的视频消息")
            return ConversationHandler.END
        
        # 进度跟踪变量
        last_update_time = datetime.now()
        
        async def progress_callback(current, total):
            nonlocal last_update_time
            now = datetime.now()
            
            # 每5秒更新一次进度
            if (now - last_update_time).total_seconds() >= 5:
                percentage = (current / total) * 100 if total > 0 else 0
                progress_bar = create_progress_bar(percentage)
                
                progress_text = f"📹 视频文件: {file_name}\n"
                progress_text += f"📏 大小: {format_file_size(video_size)}\n"
                progress_text += f"⬇️ 下载进度:\n{progress_bar}\n"
                progress_text += f"📊 {format_file_size(current)} / {format_file_size(total)}"
                
                try:
                    await query.edit_message_text(text=progress_text)
                    last_update_time = now
                except Exception as e:
                    # 忽略消息编辑错误（比如内容相同时的错误）
                    pass
        
        # 开始下载并显示进度
        saved_path = await init.tg_user_client.download_media(
            target_msg, 
            file=file_path,
            progress_callback=progress_callback
        )
        
        if not saved_path:
            await query.edit_message_text(text="❌ 下载失败：未能保存文件")
            return ConversationHandler.END
        
        # 下载完成，更新消息
        completion_text = f"✅ [{file_name}]下载完成！"
        await query.edit_message_text(text=completion_text)
            
    except Exception as e:
        init.logger.error(f"下载视频失败: {e}")
        error_text = f"❌ [{file_name}]下载失败: {str(e)}"
        await query.edit_message_text(text=error_text)
        return ConversationHandler.END
    
    
    # 判断视频文件类型
    formate_name = detect_video_format(saved_path)
    new_file_path = saved_path[:-3] + formate_name
    if saved_path != new_file_path:
        Path(saved_path).rename(new_file_path)
    
    # 更新消息：开始上传
    upload_text = f"☁️ [{Path(new_file_path).name}] 正在上传至115网盘..."
    await query.edit_message_text(text=upload_text)
    
    file_size = os.path.getsize(new_file_path)
    # 计算文件的SHA1值
    sha1_value = file_sha1(new_file_path)
    # 创建115文件夹路径
    init.openapi_115.create_dir_recursive(selected_path)
    # 上传至115
    is_upload, bingo = init.openapi_115.upload_file(target=selected_path,
                                       file_name=Path(new_file_path).name,
                                       file_size=file_size,
                                       fileid=sha1_value,
                                       file_path=new_file_path,
                                       request_times=1)
    
    # 最终结果消息
    final_text = ""
    if is_upload:
        if bingo:
            final_text = f"⚡ [{Path(new_file_path).name}] 已秒传！\n"
        else:
            final_text = f"✅ [{Path(new_file_path).name}] 已上传！\n"
        final_text += f"📏 大小: {format_file_size(video_size)}\n"
        final_text += f"📂 保存路径: {selected_path}\n"
    else:
        final_text += f"❌ 上传失败！"

    await query.edit_message_text(text=final_text)

    # 删除本地文件
    try:
        if os.path.exists(new_file_path):
            os.remove(new_file_path)
            init.logger.debug(f"已删除临时文件: {new_file_path}")
    except Exception as e:
        init.logger.warn(f"清理临时文件时出错: {e}")
    
    # 断开 Telegram 用户客户端连接（可选，因为连接可以复用）
    try:
        if init.tg_user_client and init.tg_user_client.is_connected():
            await init.tg_user_client.disconnect()
            init.logger.debug("Telegram 用户客户端连接已断开")
    except Exception as e:
        init.logger.warn(f"断开 Telegram 用户客户端连接时出错: {e}")

    return ConversationHandler.END


async def quit_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 检查是否是回调查询
    if update.callback_query:
        await update.callback_query.edit_message_text(text="🚪用户退出本次会话")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🚪用户退出本次会话")
    return ConversationHandler.END


def detect_video_format(file_path):
    # 定义魔数字典，存储视频格式及其对应魔数
    video_signatures = {
        "mp4": [b"\x00\x00\x00\x18\x66\x74\x79\x70", b"\x00\x00\x00\x20\x66\x74\x79\x70"],
        "avi": [b"\x52\x49\x46\x46", b"\x41\x56\x49\x20"],
        "mkv": [b"\x1A\x45\xDF\xA3"],
        "flv": [b"\x46\x4C\x56"],
        "mov": [b"\x00\x00\x00\x14\x66\x74\x79\x70\x71\x74\x20\x20", b"\x6D\x6F\x6F\x76"],
        "wmv": [b"\x30\x26\xB2\x75\x8E\x66\xCF\x11"],
        "webm": [b"\x1A\x45\xDF\xA3"],
    }

    with open(file_path, "rb") as f:
        file_header = f.read(12)  # 读取前12个字节以匹配文件签名

    # 识别文件格式
    for format_name, signatures in video_signatures.items():
        if any(file_header.startswith(signature) for signature in signatures):
            return format_name
    return "unknown"

def file_sha1(file_path):
    with open(file_path, 'rb') as f:
        return hashlib.sha1(f.read()).hexdigest()


def format_file_size(size_bytes):
    """格式化文件大小"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"


def create_progress_bar(percentage):
    """创建进度条"""
    filled = int(percentage // 5)  # 每5%一个方块
    bar = "█" * filled + "░" * (20 - filled)
    return f"[{bar}] {percentage:.1f}%"


def register_video_handlers(application):
    # 转存视频
    video_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.VIDEO, save_video2115)],
        states={
            SELECT_MAIN_CATEGORY_VIDEO: [CallbackQueryHandler(select_main_category_video)],
            SELECT_SUB_CATEGORY_VIDEO: [CallbackQueryHandler(select_sub_category_video)],
        },
        fallbacks=[CommandHandler("q", quit_conversation)],
    )
    application.add_handler(video_handler)
    init.logger.info("✅ Video处理器已注册")
    


