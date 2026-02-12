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

scheduler = BlockingScheduler()

def get_sync_time(category):
    sync_time = {'hour': 3, 'minute': 0}  # 默认时间03:00
    if category == "sehua":
        # 使用 or {} 处理配置项为 None 的情况，避免 AttributeError
        sehua_config = init.bot_config.get("sehua_spider") or {}
        sehua_sync_time = sehua_config.get("sync_time", "03:00")
        try:
            hour, minute = map(int, sehua_sync_time.split(":"))
            sync_time['hour'] = hour
            sync_time['minute'] = minute
        except Exception as e:
            init.logger.warn(f"解析涩花同步时间失败: {e}，将使用默认时间 03:00")
        return sync_time
    
    if category == "jav":
        # 使用 or {} 处理配置项为 None 的情况，避免 AttributeError
        jav_config = init.bot_config.get("av_daily_update") or {}
        jav_sync_time = jav_config.get("sync_time", "20:00")
        try:
            hour, minute = map(int, jav_sync_time.split(":"))
            sync_time['hour'] = hour
            sync_time['minute'] = minute
        except Exception as e:
            init.logger.warn(f"解析JAV同步时间失败: {e}，将使用默认时间 20:00")
        return sync_time

    return sync_time

def clear_request_count():
    """清除115请求计数"""
    init.logger.info(f"昨日累计115 OpenAPI请求次数: [{init.openapi_115.request_count}]")
    cache_hit_rate = (init.openapi_115.cache_hit / init.openapi_115.request_count * 100) if init.openapi_115.request_count > 0 else 0
    init.logger.info(f"昨日累计115 缓存命中率: [{cache_hit_rate:.2f}%]")
    init.logger.info("正在重置115请求计数...")
    init.openapi_115.clear_request_count()
    init.logger.info("115请求计数已重置！")

# 定义任务列表
tasks = []

def init_tasks():
    global tasks
    sehua_sync_time = get_sync_time("sehua")
    jav_sync_time = get_sync_time("jav")

    tasks = [
        {"id": "subscribe_movie_task", "func": schedule_movie, "interval": 4 * 60 * 60, "task_type": "interval"},
        {"id": "av_daily_update_task", "func": av_daily_update, "hour": jav_sync_time.get("hour", 20), "minute": jav_sync_time.get("minute", 0), "task_type": "time"},
        {"id": "offline_task_retry_task", "func": offline_task_retry, "hour": "9,18", "minute": 0, "task_type": "time"},
        {"id": "retry_failed_downloads", "func": try_to_offline2115_again, "interval": 12 * 60 * 60, "task_type": "interval"},
        {"id": "clear_request_count_task", "func": clear_request_count, "hour": 0, "minute": 0, "task_type": "time"},
        {"id": "sehua_spider_task", "func": sehua_spider_start, "hour": sehua_sync_time.get("hour", 3), "minute": sehua_sync_time.get("minute", 0), "task_type": "time"}
    ]


def subscribe_scheduler():
    # 初始化任务列表，确保配置已加载
    init_tasks()
    
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

