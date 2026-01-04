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
from app.utils.utils import check_input
import asyncio
from app.core.javbus import rss_javbus
from app.core.t66y import start_t66y_rss_async

# RSS类别，可根据需要添加更多类别
RSS_CATEGORIES = ["JavBus", "草榴1024"]

SELECT_MAIN_CATEGORY, SELECT_SUB_CATEGORY, RSS_WAIT_INPUT = range(70, 73)

async def rss_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 权限检查
    usr_id = update.message.from_user.id
    if not init.check_user(usr_id):
        await update.message.reply_text("⚠️ 对不起，您无权使用115机器人！")
        return ConversationHandler.END
    
    # 深度检查RSS配置
    error_message = check_rss_config()
    if error_message:
        await update.message.reply_text(error_message)
        return ConversationHandler.END
    
    # 构建主类别选择键盘
    keyboard = []
    for category in RSS_CATEGORIES:
        keyboard.append([InlineKeyboardButton(category, callback_data=f"rss_main_{category}")])
    keyboard.append([InlineKeyboardButton("取消", callback_data="rss_quit")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="❓请选择要订阅的RSS类别：", reply_markup=reply_markup)
    return SELECT_MAIN_CATEGORY
    
async def select_main_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    query_data = query.data
    if query_data == "cancel":
        return await quit_conversation(update, context)
    elif query_data.startswith("rss_main_"):
        main_category = query_data[len("rss_main_"):]
        context.user_data['rss_main_category'] = main_category
        # 根据主类别构建子类别选择键盘
        keyboard = []
        # 主类别为JavBus时，添加对应子类别
        if main_category == "JavBus":
            # 检查JavBus配置
            error_message = check_rss_config(main_category="JavBus")
            if error_message:
                await query.edit_message_text(error_message)
                return ConversationHandler.END
            # 从配置文件获取子类别
            javbus_config = init.bot_config.get("rsshub", {}).get("javbus", {})
            categories_config = javbus_config.get("category", [])
            subcategories = [cat.get("name") for cat in categories_config if cat.get("name")]

            for subcat in subcategories:
                keyboard.append([InlineKeyboardButton(subcat, callback_data=f"rss_sub_{subcat}")])
            keyboard.append([InlineKeyboardButton("取消", callback_data="rss_quit")])
            reply_markup = InlineKeyboardMarkup(keyboard)
        
    
        # 后续可继续添加其他子类别处理逻辑
        if main_category == "草榴1024": 
            # 检查草榴1024配置
            error_message = check_rss_config(main_category="草榴1024")
            if error_message:
                await query.edit_message_text(error_message)
                return ConversationHandler.END
            # 从配置文件获取子类别
            t66y_config = init.bot_config.get("rsshub", {}).get("t66y", {})
            sections = t66y_config.get("sections", [])
            subcategories = [section.get("name") for section in sections if section.get("name")]
            for subcat in subcategories:
                keyboard.append([InlineKeyboardButton(subcat, callback_data=f"rss_sub_{subcat}")])
            keyboard.append([InlineKeyboardButton("取消", callback_data="rss_quit")])
            reply_markup = InlineKeyboardMarkup(keyboard)   
            
        await query.edit_message_text(text="❓请选择子类别：", reply_markup=reply_markup)
        return SELECT_SUB_CATEGORY
            
    
async def select_sub_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    query_data = query.data
    if query_data == "rss_quit":
        return await quit_conversation(update, context)
    elif query_data.startswith("rss_sub_"):
        sub_category = query_data[len("rss_sub_"):]
        context.user_data['rss_sub_category'] = sub_category
        main_category = context.user_data.get('rss_main_category')
        
        if main_category == "JavBus":
            for category in init.bot_config.get("rsshub", {}).get("javbus", {}).get("category", []):
                if category.get("name") == sub_category:
                    context.user_data['selected_category'] = category
                    if category.get("need_input", False):
                        message = escape_markdown(f"⌨️ 请输入 **{sub_category}** 的关键词：\n注意：输入的内容需保证在JavBus有返回结果！", version=2)
                        await query.edit_message_text(text=message, parse_mode='MarkdownV2')
                        return RSS_WAIT_INPUT
                    else:
                        rss_host = init.bot_config.get("rsshub").get("rss_host").rstrip('/')
                        route = category.get("route", "").rstrip('/').lstrip('/')
                        rss_url = f"{rss_host}/{route}"
                        message = escape_markdown(f"✅ 您已选择订阅：\n主类别：{main_category}\n子类别：{sub_category}\n\nJavBus订阅服务已启动，请稍后...", version=2)
                        await query.edit_message_text(text=message, parse_mode='MarkdownV2')
                        asyncio.create_task(rss_javbus(sub_category, rss_url, ""))
                        return ConversationHandler.END
                    
        if main_category == "草榴1024":
            rss_host = init.bot_config.get("rsshub").get("rss_host").rstrip('/')
            message = escape_markdown(f"✅ 您已选择订阅：\n主类别：{main_category}\n子类别：{sub_category}\n\n草榴1024订阅服务已启动，请稍后...", version=2)
            await query.edit_message_text(text=message, parse_mode='MarkdownV2')
            asyncio.create_task(start_t66y_rss_async(sub_category))

        
        return ConversationHandler.END

async def rss_handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    sub_category = context.user_data.get('rss_sub_category')
    main_category = context.user_data.get('rss_main_category')
    selected_category = context.user_data.get('selected_category')
    
    rss_host = init.bot_config.get("rsshub").get("rss_host").rstrip('/')
    rss_url = ""
    
    if main_category == "JavBus":
        rss_url = f"{rss_host}/{selected_category.get('route').rstrip('/').lstrip('/')}/{user_input}"
        # 启动后台任务
        asyncio.create_task(rss_javbus(sub_category, rss_url, user_input))

    
    if rss_url:
        message = escape_markdown(f"✅ 您已选择订阅：\n主类别：{main_category}\n子类别：{sub_category}\n关键词：{user_input}\n\nJavBus订阅服务已启动，请稍后...", version=2)
        await update.message.reply_text(text=message, parse_mode='MarkdownV2')
    else:
        await update.message.reply_text(text="⚠️ 生成RSS链接失败，请检查输入是否正确。")
        
    return ConversationHandler.END

async def quit_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 检查是否是回调查询
    if update.callback_query:
        await update.callback_query.edit_message_text(text="🚪用户退出本次会话")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🚪用户退出本次会话")
    return ConversationHandler.END

def check_rss_config(main_category=None):
    error_message = ""
    rss_config = init.bot_config.get("rsshub")
    if rss_config is None:
        error_message = "❌ RSSHub配置缺失，请检查配置文件！"
        init.logger.warn(error_message)
        return error_message
    rss_host = rss_config.get("rss_host")
    if rss_host is None:
        error_message = "❌ RSSHub地址未配置，请检查配置文件！"
        init.logger.warn(error_message)
        return error_message
    else:
        # 简单验证RSSHub地址是否可用
        try:
            response = requests.get(rss_host, timeout=5)
            if response.status_code != 200:
                return error_message
        except requests.RequestException:
            error_message = "❌ RSSHub地址不可用，请检查配置！"
            init.logger.warn(error_message)
            return error_message
    
    if main_category == "JavBus":
        # 检查javbus
        javbus_config = rss_config.get("javbus")
        if javbus_config is None:
            error_message = "❌ RSSHub JavBus配置缺失，请检查配置文件！"
            init.logger.warn(error_message)
            return error_message
        categories = javbus_config.get("category")
        if not categories or not isinstance(categories, list):
            error_message = "❌ RSSHub JavBus类别配置错误，请检查配置文件！"
            init.logger.warn(error_message)
            return error_message
        for category in categories:
            if not category.get("name") or not category.get("route") or not category.get("save_path"):
                error_message = "❌ RSSHub JavBus类别配置不完整，请检查配置文件！"
                init.logger.warn(error_message)
                return error_message
    
    if main_category == "草榴1024":
        # 检查t66y
        t66y_config = rss_config.get("t66y")
        if t66y_config is None:
            error_message = "❌ RSSHub 草榴1024配置缺失，请检查配置文件！"
            init.logger.warn(error_message)
            return error_message
        sections = t66y_config.get("sections")
        if not sections or not isinstance(sections, list):
            error_message = "❌ RSSHub 草榴1024版块配置错误，请检查配置文件！"
            init.logger.warn(error_message)
            return error_message
        for section in sections:
            if not section.get("name") or not section.get("save_path"):
                error_message = "❌ RSSHub 草榴1024版块配置不完整，请检查配置文件！"
                init.logger.warn(error_message)
                return error_message
    
    return error_message

def register_rss_handlers(application):
    # 命令形式的下载交互
    download_command_handler = ConversationHandler(
        entry_points=[CommandHandler("rss", rss_command)],
        states={
            SELECT_MAIN_CATEGORY: [CallbackQueryHandler(select_main_category)],
            SELECT_SUB_CATEGORY: [CallbackQueryHandler(select_sub_category)],
            RSS_WAIT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, rss_handle_input)],
        },
        fallbacks=[CommandHandler("q", quit_conversation)],
    )
    application.add_handler(download_command_handler)
    init.logger.info("✅ RSS处理器已注册")