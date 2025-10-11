from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from pathlib import Path
import time
import os
import init
from concurrent.futures import ThreadPoolExecutor
from app.utils.aria2 import download_by_url, check_status_by_url
from app.utils.message_queue import add_task_to_queue
from telegram.helpers import escape_markdown

aria2_download_check_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="Aria2_Download")

async def push2aria2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("push2aria2_"):
        # 检查是否是新的ID格式
        task_id = data[len("push2aria2_"):]
        save_path = ""
        if hasattr(init, 'pending_push_tasks') and task_id in init.pending_push_tasks:
            # 新格式：从全局存储中获取数据
            task_data = init.pending_push_tasks[task_id]
            save_path = task_data["path"]
            init.logger.info(f"推送任务ID: {task_id}, 文件路径: {save_path}")
            # 清理已使用的任务数据
            del init.pending_push_tasks[task_id]
        else:
            init.logger.warn("❌ 无效的任务ID或任务已过期。")
            await query.answer("❌ 无效的任务ID或任务已过期。", show_alert=True)
            return
        try:
            if not save_path:
                init.logger.warn("❌ 无效的文件路径，无法推送到Aria2。")
                await query.answer("❌ 无效的文件路径，无法推送到Aria2。", show_alert=True)
                return
            download_urls = init.openapi_115.get_file_download_url(save_path)
            init.logger.info(f"[{save_path}]目录发现{len(download_urls)}个文件需要下载")
            
            # 获取文件夹名作为下载目录
            path = Path(save_path)
            last_part = path.parts[-1] if path.parts[-1] else path.parts[-2]
            download_dir = os.path.join(init.bot_config.get("aria2", {}).get("download_path", ""), last_part)
            init.logger.info(f"推送到Aria2，下载目录: {download_dir}")
            all_pushed = True
            # 获取设备名称
            device_name = init.bot_config.get('aria2', {}).get('device_name', 'Aria2') or 'Aria2'
            for download_url in download_urls:
                download = download_by_url(download_url, download_dir)
                if not download:
                    all_pushed = False
                    init.logger.error(f"推送到Aria2失败，下载链接: {download_url}")
                else:
                    # 添加到检查队列
                    aria2_download_check_executor.submit(check_download_complete, download_url, update.effective_chat.id, device_name)
                time.sleep(1)  # 避免短时间内添加过多任务
            
            
            try:
                # 尝试编辑消息，处理不同的消息类型
                if all_pushed:
                    # 首先尝试编辑caption（适用于图片消息）
                    await query.edit_message_caption(caption=f"✅ [{last_part}]已推送至{device_name}！")
                else:
                    await query.edit_message_caption(caption=f"❌ [{last_part}]推送到{device_name}失败，请检查配置或稍后再试。")
            except Exception:
                try:
                    # 如果编辑caption失败，尝试编辑文本（适用于纯文本消息）
                    if download:
                        await query.edit_message_text(f"✅ [{last_part}]已推送至{device_name}！")
                    else:
                        await query.edit_message_text(f"❌ [{last_part}]推送到{device_name}失败，请检查配置或稍后再试。")
                except Exception:
                    # 如果都失败，使用answer显示结果
                    if download:
                        await query.answer(f"✅ [{last_part}]已推送至{device_name}！", show_alert=True)
                    else:
                        await query.answer(f"❌ [{last_part}]推送到{device_name}失败，请检查配置或稍后再试。", show_alert=True)
                
        except Exception as e:
            init.logger.error(f"推送到{device_name}失败: {e}")
            try:
                await query.edit_message_caption(caption=f"❌ [{last_part if 'last_part' in locals() else '文件'}]推送到{device_name}失败: {str(e)}")
            except Exception:
                try:
                    await query.edit_message_text(f"❌ [{last_part if 'last_part' in locals() else '文件'}]推送到{device_name}失败: {str(e)}")
                except Exception:
                    await query.answer(f"❌ 推送到{device_name}失败: {str(e)}", show_alert=True)


def check_download_complete(download_url, user_id, device_name, check_interval=10):
    """检查下载任务是否完成"""
    message = ""
    while True:
        download_status = check_status_by_url(download_url)
        if download_status['status'] == "not_found":
            message = f"❌ [{download_status['name']}] 没有找到下载链接！"
            break
        elif download_status['status'] == "error":
            message = f"❌ [{download_status['name']}] 下载失败！"
            break
        elif download_status['status'] == "complete":
            message = f"✅ [{download_status['name']}] 已下载到{device_name}！"
            break
        elif download_status['status'] == "paused":
            message = f"⏸️ [{download_status['name']}] 下载已暂停！"
            break
        else:
            init.logger.debug(f" [{download_status['name']}], 下载状态: {download_status['status']}, 进度: {download_status.get('progress', 'N/A')}, 速度: {download_status.get('speed', 'N/A')}")
            time.sleep(check_interval)
    message = escape_markdown(message, version=2)
    add_task_to_queue(
        user_id, 
        None, 
        message
    )


def register_aria2_handlers(application):
    aria2_handler = CallbackQueryHandler(push2aria2, pattern=r"^push2aria2_.+")
    application.add_handler(aria2_handler)
    init.logger.info("✅ Aria2处理器已注册")