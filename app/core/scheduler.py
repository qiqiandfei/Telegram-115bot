# -*- coding: utf-8 -*-

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import init
import threading
import time
from datetime import datetime, timedelta
from app.core.subscribe_movie import schedule_movie
from apscheduler.triggers.interval import IntervalTrigger
from app.core.av_daily_update import av_daily_update
from app.handlers.offline_task_handler import try_to_offline2115_again
from app.core.sehua_spider import sehua_spider_start
from app.core.offline_task_retry import offline_task_retry
from app.core.t66y import start_t66y_rss

scheduler = BlockingScheduler()

# 定义任务列表
tasks = [
    {"id": "subscribe_movie_task", "func": schedule_movie, "interval": 4 * 60 * 60, "task_type": "interval"},
    {"id": "av_daily_update_task", "func": av_daily_update, "hour": 20, "minute": 00, "task_type": "time"},
    {"id": "offline_task_retry_task", "func": offline_task_retry, "hour": "9,18", "minute": 00, "task_type": "time"},
    {"id": "retry_failed_downloads", "func": try_to_offline2115_again, "interval": 12 * 60 * 60, "task_type": "interval"},
    {"id": "sehua_spider_task", "func": sehua_spider_start, "hour": 0, "minute": 5, "task_type": "time"}
    # {"id": "t66y_rss_task", "func": start_t66y_rss, "hour": 0, "minute": 5, "task_type": "time"},
]

def subscribe_scheduler():
    for task in tasks:
        if not scheduler.get_job(task["id"]):
            if task['task_type'] == 'interval':
                scheduler.add_job(
                    task["func"],
                    IntervalTrigger(seconds=task["interval"]),
                    id=task["id"],
                )
            if task['task_type'] == 'time':
                scheduler.add_job(
                    task["func"],
                    CronTrigger(hour=task["hour"], minute=task["minute"]),
                    id=task["id"],
                )
    # 确保调度器是启动状态
    if not scheduler.running:
        scheduler.start()


def stop_all_subscriptions():
    for task in tasks:
        job = scheduler.get_job(task['id'])
        if job:
            scheduler.remove_job(task['id'])
            init.logger.info(f"任务 {task['id']} 已停止")
        else:
            init.logger.info(f"任务 {task['id']} 不存在")




def start_scheduler_in_thread():
    thread = threading.Thread(target=subscribe_scheduler)
    thread.daemon = True  # 设置为守护线程，主线程退出时自动结束
    thread.start()

