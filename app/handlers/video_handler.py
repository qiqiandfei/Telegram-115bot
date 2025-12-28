# -*- coding: utf-8 -*-

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, ConversationHandler, \
    MessageHandler, filters, CallbackQueryHandler
import init
import os
import uuid
from datetime import datetime
from warnings import filterwarnings
from telegram.warnings import PTBUserWarning
from app.core.video_downloader import video_manager

filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)
# 过滤 Telethon 的异步会话实验性功能警告
filterwarnings(action="ignore", message="Using async sessions support is an experimental feature")


async def save_video2115(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usr_id = update.message.from_user.id
    if not init.check_user(usr_id):
        await update.message.reply_text("⚠️ 对不起，您无权使用115机器人！")
        return
    
    if not init.tg_user_client:
        message = "⚠️ Telegram 用户客户端初始化失败，配置方法请参考\nhttps://github.com/qiqiandfei/Telegram-115bot/wiki/VideoDownload"
        await update.message.reply_text(message)
        return

    # 检查和建立 Telegram 用户客户端连接
    try:
        if not init.tg_user_client.is_connected():
            init.logger.info("🔄 正在验证 Telegram 用户客户端连接...")
            await init.tg_user_client.connect()
        
        if not await init.tg_user_client.is_user_authorized():
            await update.message.reply_text("❌ Telegram 用户客户端未授权！")
            return
            
    except Exception as e:
        init.logger.error(f"Telegram 用户客户端连接失败: {e}")
        await update.message.reply_text(f"❌ 连接失败: {str(e)}")
        return

    if update.message and update.message.video:
        video = update.message.video
        file_name = video.file_name if video.file_name else f"{datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
        
        # 生成唯一任务ID
        task_id = str(uuid.uuid4())[:8]
        
        # 暂存视频信息到 context.user_data，使用 task_id 作为 key
        context.user_data[f"video_{task_id}"] = {
            "file_name": file_name,
            "file_size": video.file_size,
            "message_id": update.message.message_id,
            "chat_id": update.effective_chat.id
        }

        # 显示主分类
        keyboard = []
        
        # 添加上次保存路径按钮
        last_path = context.user_data.get('last_video_save_path')
        if last_path:
            keyboard.append([InlineKeyboardButton(f"🚀 上次保存: {last_path}", callback_data=f"quick_last_{task_id}")])
            
        keyboard.extend([
            [InlineKeyboardButton(f"📁 {category['display_name']}", callback_data=f"main_{category['name']}_{task_id}")] 
            for category in init.bot_config['category_folder']
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text=f"📹 收到视频: {file_name}\n❓请选择要保存到哪个分类：",
            reply_markup=reply_markup,
            reply_to_message_id=update.message.message_id
        )


async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        # 忽略 "Query is too old" 错误，这通常发生在点击很久之前的按钮时
        init.logger.debug(f"Callback query answer failed: {e}")
    
    data = query.data
    parts = data.split('_')
    action = parts[0]
    
    if action == "main":
        # 选择主分类: main_categoryName_taskId
        category_name = parts[1]
        task_id = parts[2]
        
        sub_categories = [
            item['path_map'] for item in init.bot_config["category_folder"] if item['name'] == category_name
        ][0]

        keyboard = [
            [InlineKeyboardButton(f"📁 {category['name']}", callback_data=f"sub_{category['path']}_{task_id}")] 
            for category in sub_categories
        ]
        keyboard.append([InlineKeyboardButton("返回", callback_data=f"back_{task_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("❓请选择子分类：", reply_markup=reply_markup)
        
    elif action == "sub" or action == "quick":
        # 选择子分类: sub_path_taskId 或 quick_last_taskId
        save_path = None
        task_id = None
        
        if action == "sub":
            task_id = parts[-1]
            save_path = "_".join(parts[1:-1])
            # 记录本次保存路径
            context.user_data['last_video_save_path'] = save_path
        elif action == "quick":
            task_id = parts[2]
            save_path = context.user_data.get('last_video_save_path')
            if not save_path:
                await query.answer("上次保存路径已失效，请重新选择", show_alert=True)
                return
        
        video_info = context.user_data.get(f"video_{task_id}")
        if not video_info:
            await query.edit_message_text("❌ 任务信息已过期")
            return

        # 获取原始消息对象
        try:
            # 确定 entity
            entity = None
            # 如果是私聊（chat_id == user_id），User Client 需要去获取和 Bot 的聊天记录
            if video_info['chat_id'] == update.effective_user.id:
                # 动态获取 Bot 用户名，无需依赖配置文件
                try:
                    bot_info = await context.bot.get_me()
                    entity = f"@{bot_info.username}"
                except Exception as e:
                    init.logger.error(f"获取Bot信息失败: {e}")
                    # 回退到配置文件
                    entity = init.bot_config.get('bot_name')
            else:
                # 群组情况，直接用 chat_id
                entity = video_info['chat_id']

            if not entity:
                await query.edit_message_text("❌ 无法确定消息来源 (Entity unknown)")
                return

            # 尝试获取消息
            target_msg = None
            
            # 方法1: 精确 ID 获取 (Telethon get_messages with ids)
            try:
                msg = await init.tg_user_client.get_messages(entity, ids=video_info['message_id'])
                if msg and msg.media:
                    target_msg = msg
            except Exception as e:
                init.logger.warning(f"精确获取消息失败: {e}")

            # 方法2: 遍历最近消息 (Fallback，兼容旧逻辑)
            if not target_msg:
                init.logger.info(f"精确获取失败，尝试遍历最近消息 (ID: {video_info['message_id']})")
                try:
                    # 获取最近 20 条消息
                    recent_msgs = await init.tg_user_client.get_messages(entity, limit=20)
                    
                    # 2.1 优先寻找 ID 匹配的消息
                    for msg in recent_msgs:
                        if msg.id == video_info['message_id'] and msg.media:
                            target_msg = msg
                            break
                    
                    # 2.2 如果没找到 ID，寻找最近的一条带视频的消息 (用户提到的"原来的写法")
                    if not target_msg:
                        for msg in recent_msgs:
                            if msg.media:
                                # 简单的校验：如果是视频/文件
                                target_msg = msg
                                init.logger.info(f"使用最近的媒体消息作为目标 (ID: {msg.id})")
                                break
                except Exception as e:
                    init.logger.error(f"遍历消息失败: {e}")

            if not target_msg:
                await query.edit_message_text(f"❌ 无法获取原始视频消息 (Entity: {entity}, ID: {video_info['message_id']})")
                return
                
            # 提交任务到管理器
            task_info = {
                "task_id": task_id,
                "file_name": video_info['file_name'],
                "file_size": video_info['file_size'],
                "save_path": save_path,
                "message": target_msg,
                "context": context,
                "chat_id": update.effective_chat.id,
                "message_id": query.message.message_id  # 更新这条消息的状态
            }
            
            await video_manager.add_task(task_info)
            
            # 清理 user_data
            del context.user_data[f"video_{task_id}"]
            
        except Exception as e:
            init.logger.error(f"提交任务失败: {e}")
            await query.edit_message_text(f"❌ 提交任务失败: {e}")

    elif action == "back":
        task_id = parts[1]
        keyboard = []
        
        # 添加上次保存路径按钮
        last_path = context.user_data.get('last_video_save_path')
        if last_path:
            keyboard.append([InlineKeyboardButton(f"🚀 上次保存: {last_path}", callback_data=f"quick_last_{task_id}")])
            
        keyboard.extend([
            [InlineKeyboardButton(f"📁 {category['display_name']}", callback_data=f"main_{category['name']}_{task_id}")] 
            for category in init.bot_config['category_folder']
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("❓请选择要保存到哪个分类：", reply_markup=reply_markup)

    elif action == "v" and parts[1] == "cancel":
        # 取消下载: v_cancel_taskId
        task_id = parts[2]
        success = await video_manager.cancel_task(task_id)
        if success:
            await query.edit_message_text("🛑 正在取消任务...")
        else:
            await query.answer("任务无法取消或已完成", show_alert=True)

    elif action == "cancel":
        # 保留旧逻辑以防万一，或者直接移除
        if len(parts) > 2 and parts[1] == "dl":
            task_id = parts[2]
            success = await video_manager.cancel_task(task_id)
            if success:
                await query.edit_message_text("🛑 正在取消任务...")


def register_video_handlers(application):
    # 注册视频消息处理器
    application.add_handler(MessageHandler(filters.VIDEO, save_video2115))
    
    # 注册回调处理器
    # 添加 v_ 前缀支持
    application.add_handler(CallbackQueryHandler(handle_category_selection, pattern="^(main|sub|back|cancel|quick|v)_"))
    
    init.logger.info("✅ Video处理器已注册 (并发版)")
    


