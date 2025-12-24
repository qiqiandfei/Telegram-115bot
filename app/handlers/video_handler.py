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
from app.utils.fast_telethon import download_file_parallel

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
        message = "⚠️ Telegram 用户客户端初始化失败，配置方法请参考\nhttps://github.com/qiqiandfei/Telegram-115bot/wiki/VideoDownload"
        await update.message.reply_text(message)
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
        # 使用多线程分片下载
        saved_path = await download_file_parallel(
            init.tg_user_client,
            target_msg, 
            file_path=file_path,
            progress_callback=progress_callback,
            threads=8  # 使用8线程加速
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
    """
    通过读取文件头识别视频格式。
    支持格式：mp4, mkv, avi, mov, wmv, flv, webm, ts, mpg, m4v, 3gp, ogg
    """
    try:
        with open(file_path, "rb") as f:
            # 读取足够长的头部字节，260字节通常足够覆盖大多数格式的签名
            header = f.read(260)
    except Exception:
        return "unknown"

    if len(header) < 4:
        return "unknown"

    # 1. ISO Base Media File Format (MP4, MOV, 3GP, M4V)
    # 特征：Offset 4 处是 'ftyp' (0x66747970)
    if len(header) >= 12 and header[4:8] == b'ftyp':
        major_brand = header[8:12]
        if major_brand == b'qt  ':
            return 'mov'
        if major_brand == b'M4V ':
            return 'm4v'
        if major_brand.startswith(b'3g'):
            return '3gp'
        # 默认为 mp4 (isom, mp42, avc1, etc.)
        return 'mp4'
    
    # 2. Matroska / WebM
    # 特征：EBML Header 0x1A45DFA3
    if header.startswith(b'\x1A\x45\xDF\xA3'):
        # 尝试在头部查找 DocType
        # EBML 结构比较复杂，这里做一个简单的字符串搜索作为启发式判断
        # DocType 通常在头部的前几十个字节内
        if b'webm' in header[:64]:
            return 'webm'
        return 'mkv'

    # 3. AVI (RIFF)
    # 特征：'RIFF' (4 bytes) + size (4 bytes) + 'AVI ' (4 bytes)
    if header.startswith(b'RIFF') and len(header) >= 12 and header[8:12] == b'AVI ':
        return 'avi'

    # 4. WMV / ASF
    # 特征：GUID 30 26 B2 75 8E 66 CF 11
    if header.startswith(b'\x30\x26\xB2\x75\x8E\x66\xCF\x11'):
        return 'wmv'

    # 5. FLV
    # 特征：'FLV' (0x464C56)
    if header.startswith(b'FLV'):
        return 'flv'

    # 6. MPEG-TS
    # 特征：Sync byte 0x47，通常包长 188 字节
    # 检查第一个字节和第189个字节（如果文件足够大）
    if header[0] == 0x47:
        if len(header) >= 189 and header[188] == 0x47:
            return 'ts'
        # 如果文件很小，或者只是片段，可能只有一个包
        elif len(header) == 188:
            return 'ts'

    # 7. MPEG-PS (VOB, MPG)
    # 特征：Pack Start Code 0x000001BA
    if header.startswith(b'\x00\x00\x01\xBA'):
        return 'mpg'
        
    # 8. OGG
    # 特征：'OggS'
    if header.startswith(b'OggS'):
        return 'ogg'

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
    


