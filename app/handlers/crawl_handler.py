from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
import init
from datetime import datetime
import threading


async def crawl_sehua(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usr_id = update.message.from_user.id
    if not init.check_user(usr_id):
        await update.message.reply_text("⚠️ 对不起，您无权使用115机器人！")
        return
    date = datetime.now().strftime("%Y-%m-%d")
    context.user_data["date"] = date  # 默认使用当天日期
    init.logger.info("涩花默认爬取当日数据")
    
    if init.CRAWL_SEHUA_STATUS == 1:
        await update.message.reply_text("⚠️ 涩花爬取任务正在进行中，请稍后再试！")
        return
    else:
        init.CRAWL_SEHUA_STATUS = 1
        await update.message.reply_text(f"🕷️ 开始爬取涩花数据，日期: {context.user_data['date']}，爬取完成后会发送通知，请稍后...")
        from app.core.sehua_spider import sehua_spider_by_date
        thread = threading.Thread(target=sehua_spider_by_date, args=(context.user_data['date'],))
        thread.start()
        return
    
async def rss_t66y(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usr_id = update.message.from_user.id
    if not init.check_user(usr_id):
        await update.message.reply_text("⚠️ 对不起，您无权使用115机器人！")
        return
    init.logger.info("t66y默认爬取当日数据")
    
    if init.RSS_T66Y_STATUS == 1:
        await update.message.reply_text("⚠️ t66y订阅任务正在进行中，请稍后再试！")
        return
    else:
        init.RSS_T66Y_STATUS = 1
        await update.message.reply_text(f"🕷️ 开始订阅t66y数据，订阅完成后会发送通知，请稍后...")
        from app.core.t66y import start_t66y_rss
        thread = threading.Thread(target=start_t66y_rss, args=())
        thread.start()
        return

async def crawl_jav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usr_id = update.message.from_user.id
    if not init.check_user(usr_id):
        await update.message.reply_text("⚠️ 对不起，您无权使用115机器人！")
        return

    if context.args:
        date = " ".join(context.args)
        date_obj = datetime.strptime(date, "%Y%m%d")
        formatted_date = date_obj.strftime("%Y-%m-%d")
        context.user_data["date"] = formatted_date  # 将用户参数存储起来
    else:
        date = datetime.now().strftime("%Y-%m-%d")
        context.user_data["date"] = date  # 默认使用当天日期
        init.logger.info("用户没有输入日期参数，默认爬取当日数据")
        
    if init.CRAWL_JAV_STATUS == 1:
        await update.message.reply_text("⚠️ javbee爬取任务正在进行中，请稍后再试！")
        return
    else:
        init.CRAWL_JAV_STATUS = 1
        await update.message.reply_text(f"🕷️ 开始爬取javbee数据，日期: {context.user_data['date']}，爬取完成后会发送通知，请稍后...")
        from app.core.av_daily_update import crawl_javbee_by_date
        thread = threading.Thread(target=crawl_javbee_by_date, args=(context.user_data['date'],))
        thread.start()
        return


def register_crawl_handlers(application):
    """crawl处理器注册函数"""
    crawl_sehua_handler = CommandHandler('csh', crawl_sehua)
    application.add_handler(crawl_sehua_handler)
    rss_t66y_handler = CommandHandler('rt66y', rss_t66y)
    application.add_handler(rss_t66y_handler)
    crawl_jav_handler = CommandHandler('cjav', crawl_jav)
    application.add_handler(crawl_jav_handler)
    init.logger.info("✅ Crawl处理器已注册")