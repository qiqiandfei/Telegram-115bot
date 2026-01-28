import os
import sys
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)
sys.path.append(current_dir)
import requests
from bs4 import BeautifulSoup
from telegram.helpers import escape_markdown
import init
import asyncio
import json
import re
from app.core.offline_task_retry import javbus_offline
from app.utils.sqlitelib import *
from concurrent.futures import ThreadPoolExecutor
from app.utils.utils import check_magnet, clean_magnet

# 全局信号量，限制并发数为 5
sem = asyncio.Semaphore(5)
# 全局线程池
executor = ThreadPoolExecutor(max_workers=10)

# 最大订阅数量
max_subscribe = init.bot_config.get("rsshub", {}).get("javbus", {}).get("max_subscribe", 0)

async def rss_javbus(sub_category, rss_url, user_input):
    page = 1
    tasks = []
    total_success_count = 0
    while True:
        if page == 1:
            url = f"{rss_url}?format=json"
        else:
            url = f"{rss_url}/{page}?format=json"
        
        if sub_category == "最新":
            if "page/1" in rss_url:
                url = f"{rss_url}?format=json"
            else:
                url = f"{rss_url}/page/{page}?format=json"
        
        # 提取本页内容
        content = await get_content_from_rssurl(url)
        
        if not content:
            break
            
        try:
            data = json.loads(content)
            items = data.get('items', [])
            init.logger.info(f"第 {page} 页获取到 {len(items)} 条数据")
            
            if not items:
                init.logger.info(f"RSS抓取完毕，第 {page} 页无数据。")
                break
                
            # 异步解析本页内容并入库
            limit = 0
            if max_subscribe > 0:
                limit = max_subscribe - total_success_count
                if limit <= 0:
                    break
                
                # 串行等待，以便控制数量
                count = await parse_items(sub_category, items, page, user_input, limit)
                total_success_count += count
                if total_success_count >= max_subscribe:
                    init.logger.info(f"已达到最大订阅数量 {max_subscribe}，停止抓取。")
                    break
            else:
                # 不阻塞下一页的抓取
                task = asyncio.create_task(parse_items(sub_category, items, page, user_input, 0))
                tasks.append(task)
            
            if sub_category == "最新":
                break  
            page += 1
            
        except json.JSONDecodeError:
            init.logger.error(f"JSON解析失败，跳过该页: {url}")
            break
            
    # 等待所有后台任务完成
    if tasks:
        init.logger.info("等待后台解析任务完成...")
        results = await asyncio.gather(*tasks)
        for i, res in enumerate(results):
            init.logger.info(f"[{sub_category}]第 {i+1} 页解析成功: {res} 条")
        total_count = sum(results)
        init.logger.info(f"所有任务已完成。共解析成功 {total_count} 条资源。")
    elif max_subscribe > 0:
        init.logger.info(f"所有任务已完成。共解析成功 {total_success_count} 条资源。")
        
    # 离线到115
    init.logger.info("开始JavBus离线任务...")
    javbus_offline()

async def get_content_from_rssurl(rss_url):
    try:
        loop = asyncio.get_running_loop()
        # 使用 run_in_executor 将同步的 requests 调用转换为异步
        response = await loop.run_in_executor(
            executor, 
            lambda: requests.get(rss_url, timeout=init.bot_config.get("rsshub", {}).get("timeout", 60))
        )
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        init.logger.error(f"获取RSS内容失败: {e}, RSS链接: {rss_url}")
        return None
    except Exception as e:
        init.logger.error(f"获取RSS内容发生未知错误: {e}")
        return None
    
async def download_image(url, referer=None, save_dir="/tmp/javbus"):
    """异步下载图片"""
    if not url:
        return None
    
    try:
        if not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)
            
        filename = url.split('/')[-1]
        save_path = os.path.join(save_dir, filename)
        
        # 如果文件已存在，直接返回路径
        if os.path.exists(save_path):
            return save_path

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": referer if referer else "https://www.javbus.com/"
        }

        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            executor, 
            lambda: requests.get(url, headers=headers, timeout=30)
        )
        
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(response.content)
            return save_path
        else:
            init.logger.warn(f"下载图片失败: {url}, 状态码: {response.status_code}")
            return None
            
    except Exception as e:
        init.logger.error(f"下载图片出错: {e}, URL: {url}")
        return None

async def parse_items(sub_category, items, page_num, user_input, limit=0):
    tasks = []
    init.logger.info(f"开始解析第 {page_num} 页，共 {len(items)} 个任务")
    for item in items:
        tasks.append(asyncio.create_task(process_single_item(sub_category, item, user_input)))
    
    if tasks:
        results = await asyncio.gather(*tasks)
        # 过滤掉 None 的结果
        valid_items = [res for res in results if res]
        
        # 如果有 limit 且超过了 limit，截断
        if limit > 0 and len(valid_items) > limit:
             valid_items = valid_items[:limit]
             
        success_count = len(valid_items)
        
        if valid_items:
            # 批量入库
            await save_items_to_db(valid_items)
            
        init.logger.info(f"第 {page_num} 页解析完成，成功 {success_count}/{len(items)}")
        return success_count
    return 0

async def save_items_to_db(items):
    """批量保存数据到数据库"""
    if not items:
        return
    try:
        # 使用 run_in_executor 将同步的数据库操作放到线程池执行，避免阻塞 asyncio 事件循环
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(executor, _batch_insert_sync, items)
        init.logger.info(f"批量入库成功: {len(items)} 条")
    except Exception as e:
        init.logger.error(f"批量入库失败: {e}")

def _batch_insert_sync(items):
    """同步的批量插入逻辑"""
    # 实际的 SQL 插入逻辑，根据你的表结构调整
    # 这里使用上下文管理器，确保连接正确关闭
    insert_count = 0
    with init.SqlLiteLib() as sqlite:
        for data in items:
            # 判断数据有效性 (只检查核心字段，防止因非关键字段缺失导致丢弃)
            if  not data.get("magnet") or \
                not data.get("av_number") or \
                not data.get("title"):
                init.logger.info(f"跳过无效数据(缺失核心字段): {json.dumps(data)}")
                continue
            
            # 判断是否是重复数据
            sql = "SELECT COUNT(*) FROM javbus WHERE magnet = ? or av_number = ?"
            params = (data["magnet"], data["av_number"])
            count = sqlite.query_one(sql, params)
            if count and count > 0:
                init.logger.info(f"跳过重复数据: {data['av_number']}")
                continue
            
            # 准备数据，处理可能的空值
            title = data.get("title", "")
            av_number = data.get("av_number", "")
            actress = data.get("actress", "")
            save_path = data.get("save_path", "")
            publish_date = data.get("publish_date", "")
            sub_category = data.get("sub_category", "")
            
            # 转义 Markdown
            safe_title = escape_markdown(title, version=2)
            safe_av_number = escape_markdown(av_number, version=2)
            safe_actress = escape_markdown(actress, version=2)
            safe_save_path = escape_markdown(save_path, version=2)
            safe_publish_date = escape_markdown(publish_date, version=2)
            safe_sub_category = escape_markdown(sub_category, version=2)
            
            movie_info = f"""
JAvBus订阅通知：

**订阅类别：**  {safe_sub_category}
**番号：**  {safe_av_number}
**标题：**  {safe_title}
**女优：**  {safe_actress}
**发布日期：**  {safe_publish_date}
**磁力链接：**  `{data.get('magnet', '')}`
**发布地址：**  [点击查看详情]({data.get('pub_url', '')})
**保存路径：**  `{safe_save_path}`
"""
            insert_sql = """
                INSERT INTO javbus (sub_category, av_number, title, publish_date, actress, magnet, poster_url, pub_url, save_path, movie_info)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            # 注意：SqlLiteLib 的方法名是 execute_sql
            sqlite.execute_sql(insert_sql, (
                sub_category,
                av_number,
                title,
                publish_date,
                actress,
                data.get("magnet"),
                data.get("poster_url"),
                data.get("pub_url"),
                save_path,
                movie_info
            ))
            insert_count += 1
        init.logger.info(f"本次批量插入完成，共插入 {insert_count} 条新数据。")

async def process_single_item(sub_category, item, user_input):
    async with sem:
        try:
            # 1. 提取标题
            title = item.get('title', '')
            if title:
                title = title.split(' ')[1].strip()
            
            # 2. 提取番号 (从ID或标题中提取)
            av_number = item.get('id', '')
            if not av_number and title:
                # 尝试从标题提取番号，通常是第一部分
                av_number = title.split(' ')[0]
            
            # 3. 提取发布地址
            pub_url = item.get('url', '')
            if not pub_url:
                pub_url = item.get('link', '')
                
            # 4. 提取发布日期 (从HTML中解析更准确，或者使用date_published)
            publish_date = ""
            # 优先尝试从date_published获取
            date_published = item.get('date_published', '')
            if date_published:
                try:
                    # 处理 ISO 格式日期 2025-12-17T16:00:00.000Z
                    publish_date = date_published.split('T')[0]
                except:
                    pass
            
            # 5. 提取演员
            actress = ""
            authors = item.get('authors', [])
            if authors:
                actress = ",".join([author.get('name') for author in authors])
            
            description = item.get('content_html', '')
            if not description:
                description = item.get('description', '')
                
            magnet = None
            cover_url = None
            
            if description:
                soup = BeautifulSoup(description, 'html.parser')
                
                # 补充提取发布日期 (如果前面没获取到)
                if not publish_date:
                    date_span = soup.find('span', string="發行日期:")
                    if date_span and date_span.parent:
                        publish_date = date_span.parent.get_text().replace("發行日期:", "").strip()

                # 补充提取演员 (如果前面没获取到)
                if not actress:
                    star_box = soup.find_all('div', class_='star-name')
                    stars = []
                    for box in star_box:
                        stars.append(box.get_text(strip=True))
                    if stars:
                        actress = ",".join(stars)

                # 6. 提取磁力链接 (取第一个)
                # 优先查找表格中的磁力链接
                magnet_table = soup.find('table')
                if magnet_table:
                    first_magnet_link = magnet_table.find('a', href=re.compile(r'^magnet:\?'))
                    if first_magnet_link:
                        magnet = first_magnet_link['href']
                        magnet = clean_magnet(magnet)
                        
                
                # 如果表格中没找到，尝试查找所有链接
                if not magnet:
                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        if check_magnet(href):
                            magnet = href
                            break
                
                # 7. 提取封面图片URL
                # 优先找 bigImage
                big_image = soup.find('a', class_='bigImage')
                if big_image and big_image.get('href'):
                    cover_url = big_image['href']
                else:
                    # 其次找第一个图片
                    img = soup.find('img', src=True)
                    if img:
                        cover_url = img['src']

            if magnet and av_number:
                # 8. 异步下载封面图片
                poster_path = None
                if cover_url:
                    poster_path = await download_image(cover_url, referer=pub_url)
                
                # 打印日志或后续处理
                init.logger.info(f"RSS解析成功: {av_number} {title}")
                
                # 返回解析后的数据字典，供上层批量入库
                save_path = get_save_path(sub_category, user_input)
                return {
                    "sub_category": sub_category,
                    "av_number": av_number,
                    "title": title,
                    "publish_date": publish_date,
                    "actress": actress,
                    "magnet": magnet,
                    "poster_url": poster_path,
                    "pub_url": pub_url,
                    "user_input": user_input,
                    "save_path": save_path
                }
            else:
                init.logger.warn(f"跳过无效资源: {title} (Magnet: {bool(magnet)}, AV: {bool(av_number)})")
                return 0
            
        except Exception as e:
            init.logger.error(f"解析RSS内容时发生错误: {e}")
            return 0
    
def get_save_path(sub_category, user_input):
    category_list= init.bot_config.get("rsshub", {}).get("javbus", {}).get("category", [])
    save_path = ""
    for category in category_list:
        if category.get("name") == sub_category:
            save_path = category.get("save_path", f"/AV/JavBus/{sub_category}")
            if sub_category != "最新" and user_input:
                safe_input = re.sub(r'[\\/*?:"<>|]', "_", user_input)
                return os.path.join(save_path, safe_input)
            else:
                return save_path
            
if __name__ == "__main__":
    init.init_log()
    init.load_yaml_config()
    try:
        asyncio.run(rss_javbus("女优", "https://rss.yhfw.fun/javbus/search/河北彩花", "河北彩花"))
    finally:
        executor.shutdown(wait=True)