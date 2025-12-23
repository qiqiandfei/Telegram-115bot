# -*- coding: utf-8 -*-

from telegram import Update
from telegram.ext import CommandHandler, ConversationHandler, ContextTypes
import init
import os


# 定义对话的步骤
# ASK_COOKIE, RECEIVE_COOKIE = range(0, 2)


async def auth_pkce_115(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usr_id = update.message.from_user.id
    if init.check_user(usr_id):
        if check_115_app_id():
            if os.path.exists(init.TOKEN_FILE):
                os.remove(init.TOKEN_FILE)
            init.openapi_115.auth_pkce(usr_id, init.bot_config['115_app_id'])
            if init.openapi_115.access_token and init.openapi_115.refresh_token:
                await update.message.reply_text("✅ 授权成功！")
            else:
                await update.message.reply_text("⚠️ 授权失败，请检查配置文件中的app_id是否正确！")
        else:
            await update.message.reply_text("⚠️ 115开放平台APPID未配置！")
    else:
        await update.message.reply_text(f"⚠️ 对不起，您无权使用115机器人！")
    # 结束对话
    return ConversationHandler.END


def check_115_app_id():
    api_key = str(init.bot_config.get('115_app_id'))
    if api_key is None or api_key.strip() == "" or api_key.strip().lower() == "your_115_app_id":
        init.logger.error("115 Open APPID未配置!")
        return False
    return True


async def quit_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 检查是否是回调查询
    if update.callback_query:
        await update.callback_query.edit_message_text(text="🚪用户退出本次会话")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🚪用户退出本次会话")
    return ConversationHandler.END


def register_auth_handlers(application):
    auth_handler = ConversationHandler(
        entry_points=[CommandHandler("auth", auth_pkce_115)],
        states={},  # 添加空的states字典
        fallbacks=[CommandHandler("q", quit_conversation)],
    )
    application.add_handler(auth_handler)
    init.logger.info("✅ Auth处理器已注册")