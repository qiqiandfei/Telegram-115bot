# -*- coding: utf-8 -*-

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import init
import threading
import time
from datetime import datetime, timedelta
from app.core.subscribe_movie import schedule_movie
from apscheduler.triggers.interval import IntervalTrigger
from app.core.av_daily_update import av_daily_update, repair_leak
from app.handlers.offline_task_handler import try_to_offline2115_again
from app.core.sehua_spider import sehua_spider_start
from app.core.offline_task_retry import offline_task_retry

scheduler = BlockingScheduler()

# 定义任务列表
tasks = [
    {"id": "subscribe_movie_task", "func": schedule_movie, "interval": 4 * 60 * 60, "task_type": "interval"},
    {"id": "av_daily_update_task", "func": av_daily_update, "hour": 20, "minute": 00, "task_type": "time"},
    {"id": "offline_task_retry_task", "func": offline_task_retry, "hour": "9,18", "minute": 00, "task_type": "time"},
    {"id": "retry_failed_downloads", "func": try_to_offline2115_again, "interval": 12 * 60 * 60, "task_type": "interval"},
    {"id": "sehua_spider_task", "func": sehua_spider_start, "hour": 0, "minute": 5, "task_type": "time"}
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


# ==================== 延迟重试功能 ====================

def schedule_sehua_retry(section_name, date, delay_minutes=30):
    """
    安排涩花爬虫延迟重试任务（一次性）
    
    Args:
        section_name: 分区名称（如"国产原创"）
        date: 爬取日期（如"2025-11-10"）  
        delay_minutes: 延迟分钟数，默认30分钟
    """
    
    # 计算延迟执行时间
    retry_time = datetime.now() + timedelta(minutes=delay_minutes)
    
    # 生成唯一任务ID，避免重复任务
    timestamp = int(time.time())
    task_id = f"sehua_retry_{section_name}_{timestamp}"
    
    # 检查是否已经有该分区的重试任务，如果有就取消
    cancel_existing_retry(section_name)
    
    # 包装重试函数，添加日志和错误处理
    def retry_wrapper():
        try:
            init.logger.info(f"🔄 开始延迟重试 [{section_name}] 分区，日期: {date}")
            sehua_spider_start()
            init.logger.info(f"✅ 延迟重试 [{section_name}] 分区完成")
        except Exception as e:
            init.logger.error(f"❌ 延迟重试 [{section_name}] 分区失败: {str(e)}")
            # 如果重试仍然失败，递增延迟后再次重试
            reschedule_on_failure(section_name, date, delay_minutes)
    
    # 添加一次性延迟任务
    scheduler.add_job(
        func=retry_wrapper,
        trigger='date',  # 一次性触发器
        run_date=retry_time,
        id=task_id,
        max_instances=1,  # 最多1个实例
        misfire_grace_time=300  # 允许5分钟的延迟容忍
    )
    
    init.logger.warn(f"🕐 已安排 [{section_name}] 分区延迟重试任务")
    init.logger.warn(f"    任务ID: {task_id}")
    init.logger.warn(f"    执行时间: {retry_time.strftime('%Y-%m-%d %H:%M:%S')}")
    init.logger.warn(f"    延迟时长: {delay_minutes} 分钟")
    
    return task_id


def cancel_existing_retry(section_name):
    """取消指定分区现有的重试任务"""
    # 获取所有任务
    jobs = scheduler.get_jobs()
    for job in jobs:
        if job.id.startswith(f"sehua_retry_{section_name}_"):
            scheduler.remove_job(job.id)
            init.logger.info(f"🗑️  已取消现有的重试任务: {job.id}")


def reschedule_on_failure(section_name, date, original_delay_minutes):
    """重试失败后的再次调度策略"""
    # 如果上次延迟已经是 120 分钟（2小时），则不再重试
    if original_delay_minutes >= 120:
        init.logger.error(f"❌ [{section_name}] 分区重试已达到最大时限(2小时)，停止重试")
        return

    # 递增延迟策略：30分钟 → 60分钟 → 120分钟（2小时上限）
    new_delay = min(original_delay_minutes * 2, 120)  # 最多等待2小时
    
    init.logger.warn(f"⏰ [{section_name}] 分区重试仍失败，将在 {new_delay} 分钟后再次重试")
    schedule_sehua_retry(section_name, date, new_delay)


def get_retry_tasks_status():
    """获取所有重试任务的状态"""
    retry_tasks = []
    jobs = scheduler.get_jobs()
    
    for job in jobs:
        if job.id.startswith("sehua_retry_"):
            retry_tasks.append({
                'id': job.id,
                'next_run_time': job.next_run_time,
                'func_name': job.func.__name__ if hasattr(job.func, '__name__') else str(job.func)
            })
    
    return retry_tasks


def cancel_all_retry_tasks():
    """取消所有重试任务"""
    jobs = scheduler.get_jobs()
    cancelled_count = 0
    
    for job in jobs:
        if job.id.startswith("sehua_retry_"):
            scheduler.remove_job(job.id)
            init.logger.info(f"🗑️  已取消重试任务: {job.id}")
            cancelled_count += 1
    
    if cancelled_count > 0:
        init.logger.info(f"✅ 共取消了 {cancelled_count} 个重试任务")
    else:
        init.logger.info("ℹ️  没有找到需要取消的重试任务")

