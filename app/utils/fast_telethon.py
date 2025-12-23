import asyncio
import os
import logging
from telethon import TelegramClient, utils
from telethon.tl.functions.upload import GetFileRequest
from telethon.tl.types import InputFileLocation, InputDocumentFileLocation

logger = logging.getLogger(__name__)

async def download_file_parallel(client: TelegramClient, message, file_path, progress_callback=None, threads=4):
    """
    使用多线程分片下载 Telegram 文件
    """
    try:
        media = message.media
        document = getattr(media, 'document', None)
        
        # 如果不是文档类型，或者文件太小（小于10MB），使用默认下载
        if not document or document.size < 10 * 1024 * 1024:
            return await client.download_media(message, file=file_path, progress_callback=progress_callback)
            
        file_size = document.size
        
        # 检查 DC ID，如果文件在不同 DC，回退到默认下载（处理跨 DC 比较复杂）
        if hasattr(document, 'dc_id') and document.dc_id != client.session.dc_id:
            logger.info(f"文件在 DC {document.dc_id}，当前在 DC {client.session.dc_id}，回退到单线程下载")
            return await client.download_media(message, file=file_path, progress_callback=progress_callback)

        # 获取 input_location，明确传入 document
        input_location = utils.get_input_location(document)
        
        # 确保 input_location 是有效的 TLObject
        if not input_location:
            logger.warning("无法获取有效的 input_location，回退到单线程下载")
            return await client.download_media(message, file=file_path, progress_callback=progress_callback)

        # 分片大小 512KB
        part_size = 512 * 1024 
        
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        # 初始化文件（预分配空间）
        with open(file_path, 'wb') as f:
            f.truncate(file_size)

        downloaded = 0
        progress_lock = asyncio.Lock()
        sem = asyncio.Semaphore(threads)
        
        # 错误标记，如果任何一个分片失败，停止所有任务
        failed = False

        async def download_chunk(offset):
            nonlocal downloaded, failed
            if failed: return

            retries = 5
            while retries > 0 and not failed:
                try:
                    async with sem:
                        current_part_size = part_size
                        if offset + current_part_size > file_size:
                            current_part_size = file_size - offset
                            
                        result = await client(GetFileRequest(
                            location=input_location,
                            offset=offset,
                            limit=current_part_size
                        ))
                        
                        chunk_data = result.bytes
                        
                        with open(file_path, 'r+b') as f:
                            f.seek(offset)
                            f.write(chunk_data)
                        
                        async with progress_lock:
                            downloaded += len(chunk_data)
                            if progress_callback:
                                if asyncio.iscoroutinefunction(progress_callback):
                                    await progress_callback(downloaded, file_size)
                                else:
                                    progress_callback(downloaded, file_size)
                        return
                except Exception as e:
                    retries -= 1
                    if retries == 0:
                        logger.error(f"分片下载失败 offset={offset}: {e}")
                        failed = True
                        raise e
                    await asyncio.sleep(1)

        tasks = []
        for offset in range(0, file_size, part_size):
            tasks.append(asyncio.create_task(download_chunk(offset)))

        await asyncio.gather(*tasks)
        
        if failed:
            raise Exception("多线程下载中有分片失败")
            
        return file_path

    except Exception as e:
        logger.error(f"多线程下载遇到错误: {e}，正在回退到单线程下载...")
        # 如果多线程下载失败，回退到原生下载
        # 确保文件被重置或覆盖
        return await client.download_media(message, file=file_path, progress_callback=progress_callback)
