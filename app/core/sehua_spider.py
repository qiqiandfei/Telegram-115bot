from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
import sys
import os
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)
sys.path.append(current_dir)
import init
import datetime
from app.utils.sqlitelib import *
import time
import random
import os
import re
import yaml
from pathlib import Path
from urllib.parse import urlparse
from urllib.parse import urlparse
from app.core.offline_task_retry import sehua_offline
from app.core.selenium_browser import SeleniumBrowser
from app.utils.utils import get_magnet_hash, read_yaml_file, check_magnet
from app.utils.message_queue import add_task_to_queue
import asyncio
import requests

# 全局browser
browser = None

def _build_full_url(path: str):
    """根据 browser.base_url 构造完整 URL，避免重复添加协议头"""
    if not browser or not browser.base_url:
        return path
    base = browser.base_url.rstrip('/')
    if not base.startswith('http'):
        base = f"https://{base}"
    return f"{base}/{path.lstrip('/')}"

def get_base_url():
    base_url = init.bot_config.get('sehua_spider', {}).get('base_url', "www.sehuatang.net")
    if not base_url:
        base_url = "www.sehuatang.net"
    return base_url


async def download_image(image_url, save_path):
    """
    使用全局浏览器下载外链图片并保存到本地
    专门用于下载外部图片链接，使用最简单可靠的方法
    
    Args:
        image_url (str): 图片的URL
        save_path (str): 保存路径（不包含扩展名）
        
    Returns:
        bool: 下载是否成功
        str: 本地文件路径或错误信息
    """
    if not image_url:
        return False, "图片URL为空"
    
    if not browser or not browser.driver:
        return False, "无法获取浏览器页面"
    
    try:
        # 确保保存目录存在
        if not os.path.exists(save_path):
            os.makedirs(save_path, exist_ok=True)
            init.logger.debug(f"创建目录: {save_path}")
        
        init.logger.debug(f"开始下载外链图片: {image_url}")
        
        # 使用 requests 配合 selenium cookies 下载
        try:
            init.logger.debug("尝试直接访问图片URL...")
            
            cookies = await browser.get_cookies()
            session = requests.Session()
            for cookie in cookies:
                session.cookies.set(cookie['name'], cookie['value'])
            
            headers = {
                "User-Agent": init.USER_AGENT,
                "Referer": f"https://{get_base_url()}/"
            }
            
            def _download():
                return session.get(image_url, headers=headers, timeout=60)
            
            response = await asyncio.to_thread(_download)
            
            if response.status_code == 200:
                # 检查Content-Type是否为图片
                content_type = response.headers.get('content-type', '').lower()
                init.logger.debug(f"Content-Type: {content_type}")
                
                if any(img_type in content_type for img_type in ['image/', 'jpeg', 'png', 'gif', 'webp']):
                    init.logger.debug("检测到图片内容，开始下载...")
                    
                    # 获取图片数据
                    image_data = response.content

                    # 获取文件名
                    filename = get_image_name(image_url)

                    # 保存文件
                    final_save_path = os.path.join(save_path, filename)
                    init.logger.debug(f"保存到: {final_save_path}")
                    
                    with open(final_save_path, 'wb') as f:
                        f.write(image_data)
                    
                    file_size = len(image_data)
                    if os.path.exists(final_save_path) and file_size > 0:
                        init.logger.info(f"图片下载成功: {final_save_path} ({file_size} bytes)")
                        return True, final_save_path
                    else:
                        error_msg = f"图片保存失败: {final_save_path}"
                        init.logger.warn(error_msg)
                        return False, error_msg
                else:
                    error_msg = f"URL返回的不是图片内容，Content-Type: {content_type}"
                    init.logger.warn(error_msg)
                    return False, error_msg
            else:
                status_code = response.status_code
                error_msg = f"访问失败，状态码: {status_code}"
                init.logger.warn(error_msg)
                return False, error_msg
                
        except Exception as direct_error:
            error_msg = f"直接访问图片失败: {str(direct_error)}"
            init.logger.warn(error_msg)
            return False, error_msg
        
    except Exception as e:
        error_msg = f"下载图片时发生错误: {str(e)}"
        init.logger.error(error_msg)
        return False, error_msg

def get_section_id(section_name):
    section_map = {
        "国产原创": 2,
        "亚洲无码原创": 36,
        "亚洲有码原创": 37,
        "高清中文字幕": 103,
        "素人有码系列": 104,
        "4K原版": 151,
        "VR视频区": 160,
        "欧美无码": 38
    }
    return section_map.get(section_name, 0)


async def sehua_spider_start_async():
    """完整的爬虫启动函数，包含浏览器生命周期管理"""
    global browser
    if not init.bot_config.get('sehua_spider', {}).get('enable', False):
        return
    # 初始化全局浏览器
    browser = SeleniumBrowser(get_base_url())
    
    try:
        await browser.init_browser()
        
        if not browser.driver:
            add_task_to_queue(init.bot_config['allowed_user'], None, f"❌ 浏览器初始化失败！")
            return
            
        # 尝试通过 Cloudflare 验证
        await browser.pass_cloudflare_check()
        yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
        date = yesterday.strftime("%Y-%m-%d")
        sections = init.bot_config['sehua_spider'].get('sections', [])
        for section in sections:
            section_name = section.get('name')
            init.logger.info(f"开始爬取 {section_name} 分区...")
            await section_spider(section_name, date)
            init.logger.info(f"{section_name} 分区爬取完成")
            delay = random.uniform(5, 10)
            await asyncio.sleep(delay)
    except Exception as e:
        init.logger.warn(f"爬取 {section_name} 分区时发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # 关闭全局浏览器
        await browser.close()
        
    # 离线到115 (Sync)
    init.logger.info("开始执行涩花离线任务...")
    sehua_offline()

def sehua_spider_start():
    try:
        asyncio.run(sehua_spider_start_async())
    except Exception as e:
        init.logger.error(f"涩花爬虫启动失败: {e}")
        
        
async def sehua_spider_by_date_async(date):
    """完整的爬虫启动函数，包含浏览器生命周期管理"""
    global browser
    browser = SeleniumBrowser(get_base_url())
    
    try:
        await browser.init_browser()
        # 初始化全局浏览器
        if not browser.driver:
            add_task_to_queue(init.bot_config['allowed_user'], None, f"❌ 浏览器初始化失败！")
            init.CRAWL_SEHUA_STATUS = 0
            return
            
        # 尝试通过 Cloudflare 验证
        await browser.pass_cloudflare_check()
        sections = init.bot_config['sehua_spider'].get('sections', [])
        for section in sections:
            section_name = section.get('name')
            init.logger.info(f"开始爬取 {section_name} 分区...")
            await section_spider(section_name, date)
            init.logger.info(f"{section_name} 分区爬取完成")
            delay = random.uniform(5, 10)
            await asyncio.sleep(delay)
    except Exception as e:
        init.logger.warn(f"爬取 {section_name} 分区时发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # 关闭全局浏览器
        await browser.close()
    # 离线到115 (Sync)
    init.logger.info("开始执行涩花离线任务...")
    sehua_offline()
    init.CRAWL_SEHUA_STATUS = 0

def sehua_spider_by_date(date):
    try:
        asyncio.run(sehua_spider_by_date_async(date))
    except Exception as e:
        init.logger.error(f"涩花爬虫(按日期)启动失败: {e}")
        init.CRAWL_SEHUA_STATUS = 0
    
    
async def section_spider(section_name, date):
    
    update_list = await get_section_update(section_name, date)
    
    if not update_list:
        init.logger.info(f"没有找到 {section_name} 在 {date} 的更新内容")
        return
    
    successful_count = 0
    failed_count = 0
    
    results = []

    try:
        for i, topic in enumerate(update_list):
            url = _build_full_url(topic)
            init.logger.debug(f"正在处理第 {i+1}/{len(update_list)} 个话题: {url}")
            
            success = False
            max_retries = 3
            
            for retry in range(max_retries):
                try:
                    # 添加随机延迟避免被反爬虫
                    if i > 0:  # 第一个请求不延迟
                        delay = random.uniform(2, 5)
                        init.logger.debug(f"等待 {delay:.1f} 秒...")
                        await asyncio.sleep(delay)
                    
                    # 尝试访问页面
                    init.logger.debug(f"  尝试访问 (第 {retry+1} 次)...")
                    await browser.goto(url)
                    
                    # 检查 Cloudflare
                    await browser.pass_cloudflare_check()
                    
                    # 检查 safeid
                    await safeid_check()

                    # 检查年龄验证
                    await age_check()
                    
                    # 等待页面完全加载
                    # await page.wait_for_load_state("networkidle", timeout=60000)
                    
                    html = await browser.get_page_source()
                    if html and len(html) > 1000:  # 确保获取到完整页面
                        result = await parse_topic(section_name, html, url, date)
                        if result and result.get('title'):
                            init.logger.debug(f"成功解析: {result.get('title', 'Unknown')}")
                            results.append(result)
                            successful_count += 1
                        else:
                            init.logger.debug(f"解析失败，内容为空")
                        success = True
                        break
                    else:
                        init.logger.warn(f"页面内容过短，可能加载失败")

                except Exception as e:
                    init.logger.warn(f"第 {retry+1} 次尝试出错: {str(e)}")
                    if retry < max_retries - 1:
                        await asyncio.sleep(5)
            
            if not success:
                init.logger.warn(f"所有重试都失败，跳过此链接")
                failed_count += 1
                
            # 每处理5个页面后增加额外延迟
            if (i + 1) % 5 == 0:
                extra_delay = random.uniform(5, 10)
                init.logger.info(f"已处理 {i+1} 个页面，休息 {extra_delay:.1f} 秒...")
                await asyncio.sleep(extra_delay)
        
        # 写入数据库
        if results:
            save_sehua2db(results)   
            results.clear()
       
    except Exception as e:
        init.logger.warn(f"爬虫过程中发生严重错误: {str(e)}")
    finally:
        init.logger.info(f"本次爬取结束 - 成功: {successful_count}, 失败: {failed_count}")
        # 注意：这里不关闭浏览器，保持cookie
            
async def parse_topic(section_name, html, url, date):
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    result['section_name'] = section_name
    result['publish_date'] = date
    result['pub_url'] = url
    result['save_path'] = get_sehua_save_path(section_name)
    title_tag = soup.find('span', {'id': 'thread_subject'})
    title = title_tag.text if title_tag else None
    if title:
        result['title'] = title
        if section_name == '国产原创':
            result['av_number'] = 'N/A'
        else:
            result['av_number'] = get_av_number_from_title(title)
    
    # 查找主要内容区域 - 使用更精确的选择器
    postmessage = soup.find('td', {'id': lambda x: x and x.startswith('postmessage_')})
    
    if not postmessage:
        # 备用方案：查找包含class="t_f"的td
        postmessage = soup.find('td', class_='t_f')
    
    if postmessage:
        # 获取HTML内容
        content_html = str(postmessage)
        
        # 提取影片容量
        size_match = None
        if '【影片容量】：' in content_html:
            import re
            size_pattern = r'【影片容量】：(.*?)(?:<br[^>]*>|【(?:出演女优|影片名称|是否有码|种子期限|下载工具|影片预览)】)'
            size_search = re.search(size_pattern, content_html)
            if size_search:
                size_match = size_search.group(1).strip()
                size_match = re.sub(r'<[^>]+>', '', size_match).strip()
                size_match = re.sub(r'\s+', ' ', size_match).strip()
        result['size'] = size_match
        
        # 提取是否有码
        type_match = None
        if '【是否有码】：' in content_html:
            import re
            type_pattern = r'【是否有码】：(.*?)(?:<br[^>]*>|【(?:出演女优|影片容量|影片名称|种子期限|下载工具|影片预览)】)'
            type_search = re.search(type_pattern, content_html)
            if type_search:
                type_match = type_search.group(1).strip()
                type_match = re.sub(r'<[^>]+>', '', type_match).strip()
                type_match = re.sub(r'\s+', ' ', type_match).strip()
        result['movie_type'] = type_match
        
        # 提取封面图片URL（从img标签的zoomfile属性）
        img_tag = postmessage.find('img', {'zoomfile': True})
        result['post_url'] = img_tag['zoomfile'] if img_tag else None
        
        # 下载图片到本地保存到tmp
        if result['post_url']:
            success, local_path = await download_image(result['post_url'], f"{init.TEMP}/sehua")
            if success:
                init.logger.debug(f"图片已下载到: {local_path}")
                result['image_path'] = local_path


        # 提取磁力链接（从blockcode div内的li标签）
        blockcode = postmessage.find('div', class_='blockcode')
        magnet = None
        if blockcode:
            li_tag = blockcode.find('li')
            if li_tag:
                magnet_text = li_tag.get_text().strip()
                # 确保是完整的magnet链接
                if magnet_text.startswith('magnet:'):
                    magnet = magnet_text
        result['magnet'] = magnet
    
    else:
        # 如果找不到主要内容区域，设置默认值
        result = {
            'title': None,
            'size': None,
            'movie_type': None,
            'post_url': None,
            'magnet': None
        }
    
    init.logger.info(f"解析结果: {result}")
    return result


async def get_section_update(section_name, date):
    all_data_today = []
    section_id = get_section_id(section_name)
    if section_id == 0:
        return all_data_today
    
    try:
        for page_num in range(1, 10):
            url = _build_full_url(f"forum.php?mod=forumdisplay&fid={section_id}&page={page_num}")
            init.logger.info(f"正在获取 {section_name} 第 {page_num} 页...")
            
            success = False
            max_retries = 3
            
            for retry in range(max_retries):
                try:
                    if page_num > 1 or retry > 0:  # 第一个请求不延迟
                        delay = random.uniform(5, 10)
                        await asyncio.sleep(delay)
                    
                    # 访问目标页面
                    await browser.goto(url)
                    await browser.pass_cloudflare_check()
                    await safeid_check()
                    await age_check()
                    
                    # 等待页面完全加载
                    await browser.wait_for_element("tbody[id^='normalthread_']")

                    # 获取页面 HTML
                    html = await browser.get_page_source()
                    if html and len(html) > 1000:
                        # 验证页面是否包含预期的内容结构
                        if 'normalthread_' in html or 'postlist' in html:
                            topics = parse_section_page(html, date, page_num, section_name)
                            if topics:
                                init.logger.info(f"其中 {len(topics)} 个今日话题")
                                all_data_today.extend(topics)
                                success = True
                                break
                            else:
                                init.logger.info(f"  第 {page_num} 页没有今日更新，停止翻页")
                                return all_data_today
                        else:
                            init.logger.warn(f"  页面结构异常，可能仍在加载中")
                            await browser.pass_cloudflare_check()
                    else:
                        init.logger.warn(f"  页面内容过短，可能加载失败")
                        
                except Exception as e:
                    init.logger.warn(f"第 {retry+1} 次尝试出错: {str(e)}")
                    if retry < max_retries - 1:
                        await asyncio.sleep(5)
            
            if not success:
                init.logger.warn(f"第 {page_num} 页获取失败，跳过")
                if page_num == 1:
                     init.logger.error(f"❌ [{section_name}] 分区第1页获取失败，停止当前分区爬取")
                     return []
                break
                
    except Exception as e:
        init.logger.warn(f"获取列表页面时发生错误: {str(e)}")
    init.logger.info(f"总共找到 {len(all_data_today)} 个今日话题")
    return all_data_today


def parse_section_page(html_content, date, page_num, section_name):
    topics = []
    soup = BeautifulSoup(html_content, "html.parser")
    
    # 调试信息
    init.logger.debug(f"正在解析日期为 {date} 的帖子...")
    
    # 查找所有线程
    threads = soup.find_all('tbody', id=lambda x: x and x.startswith('normalthread_'))
    init.logger.info(f"第 {page_num} 页，找到 {len(threads)} 个帖子")

    found_dates = []  # 用于调试，收集找到的所有日期
    
    for i, thread in enumerate(threads):
        # 提取日期（从td.by下的em内的span的title属性）
        date_td = thread.find('td', class_='by')
        topic_date = None
        
        if date_td:
            # 在td.by内查找em标签，然后在em内查找有title属性的span
            em_tag = date_td.find('em')
            if em_tag:
                # 查找有title属性的span（不限制class）
                date_span = em_tag.find('span', title=True)
                if date_span:
                    topic_date = date_span.get('title')
                    found_dates.append(topic_date)
        
        # 提取标题用于调试
        title_link = thread.find('a', class_='s xst')
        title = title_link.text.strip() if title_link else "无标题"
        
        if not topic_date or topic_date != date:
            continue  # 跳过非当日的帖子
            
        # 提前过滤标题
        if not is_title_allowed(section_name, title):
            init.logger.debug(f"标题[{title}]不满足[{section_name}]板块的规则，跳过!")
            continue
              
        # 提取链接（从标题的a标签的href属性）
        link = title_link['href'].replace('&amp;', '&') if title_link else ""
        if '-' in link:
            topic_id = link.split('-')[1]
            topic_link = f"forum.php?mod=viewthread&tid={topic_id}&extra=page%3D1"
            topics.append(topic_link)
            init.logger.info(f"找到今日帖子: {title}...")
    
    # 调试信息：显示找到的所有唯一日期
    unique_dates = list(set(found_dates))
    init.logger.debug(f"  页面中找到的日期: {unique_dates}")
    init.logger.debug(f"  目标日期: {date}")
    init.logger.debug(f"  匹配的今日帖子数量: {len(topics)}")
    
    return topics


async def age_check():
    try:
        # 等待页面基本加载
        # await browser.wait_for_page_loaded(timeout=30000)
        
        content = await browser.get_page_source()
        init.logger.debug(f"  页面内容长度: {len(content)}")
        # 检测多种可能的年龄验证提示文本
        age_indicators = ["满18岁，请点此进入", "满18岁,请点此进入", "点此进入", "进入论坛", "进入"]
        if any(ind in content for ind in age_indicators):
            init.logger.info("  检测到年龄验证页面，尝试通过多种方式进入...")
            initial_url = await browser.get_current_url()
            passed = False

            # 尝试多次点击不同文本的按钮
            click_texts = ["满18岁，请点此进入", "点此进入", "进入论坛", "进入"]
            for attempt in range(3):
                for txt in click_texts:
                    try:
                        await browser.click_text(txt)
                        await asyncio.sleep(1)
                    except Exception:
                        pass

                # 等待页面发生变化或期望元素出现（最长等待 15s）
                for _ in range(15):
                    await asyncio.sleep(1)
                    new_content = await browser.get_page_source()
                    current_url = await browser.get_current_url()
                    if current_url and current_url != initial_url:
                        passed = True
                        break
                    if len(new_content) > len(content) + 200:
                        passed = True
                        break
                    if 'tbody id=' in new_content or 'postlist' in new_content or 'normalthread_' in new_content or 'class="t_f"' in new_content:
                        passed = True
                        break
                if passed:
                    init.logger.info("  年龄验证通过，页面已加载")
                    break

            if not passed:
                init.logger.warn("  页面内容似乎没有变化，可能验证失败")
        else:
            # 即使没有年龄验证，也要等待页面完全加载
            await browser.wait_for_element("tbody[id^='normalthread_']")
            
    except Exception as e:
        init.logger.warn(f"  年龄验证处理出错: {str(e)}")
        # 继续执行，不因为年龄验证失败而中断


async def safeid_check():
    """检查并处理 safeid 验证"""
    try:
        content = await browser.get_page_source()
        if "var safeid" in content:
            init.logger.info("检测到 safeid 变量，尝试提取并添加 Cookie...")
            safeid = extract_safeid(content)
            if safeid:
                init.logger.info(f"提取到 safeid: {safeid}")
                
                # 添加 cookie
                cookie_dict = {
                    'name': '_safe',
                    'value': safeid,
                    'path': '/',
                }
                
                # 在 driver 线程中执行 cookie 添加操作
                await browser.run_with_driver(lambda d: d.add_cookie(cookie_dict))
                
                init.logger.info("safeid cookie 添加成功，刷新页面...")
                await browser.run_with_driver(lambda d: d.refresh())
                await asyncio.sleep(3) # 等待刷新完成
                
                # 再次等待元素加载
                await browser.wait_for_element("tbody[id^='normalthread_']")
            else:
                init.logger.warn("未提取到 valid safeid")
    except Exception as e:
        init.logger.warn(f"safeid 处理出错: {e}")

def extract_safeid(html):
    """提取 safeid"""
    try:
        pattern = r"var\s+safeid\s*=\s*['\"]([^'\"]+)['\"]"
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None

    
        
def get_av_number_from_title(title):
    av_number = ""
    if ' ' in title:
        parts = title.split(' ')
        tmp = parts[0].strip()
        if tmp.endswith('-'):
            tmp = tmp[:-1]
        av_number = tmp.upper()
    return av_number

def get_image_name(image_url):
    parsed = urlparse(image_url)
    filename = Path(parsed.path).name
    return filename


def save_sehua2db(results):
    insert_count = 0
    try:
        with SqlLiteLib() as sqlite:
            for result in results:
                # 检查是否满足爬取策略
                match_strategyed, specify_path = match_strategy(result)
                if not match_strategyed:
                    continue
                # 检查是否已存在（通过磁力链接Hash判断，忽略tracker等参数差异）
                magnet_hash = get_magnet_hash(result.get('magnet'))
                if magnet_hash:
                    # 如果能提取到hash，使用模糊匹配查询
                    sql_check = "select count(*) from sehua_data where magnet LIKE ?"
                    params_check = (f'%{magnet_hash}%', )
                else:
                    # 提取不到hash，回退到完全匹配
                    sql_check = "select count(*) from sehua_data where magnet = ?"
                    params_check = (result.get('magnet'), )

                count = sqlite.query_one(sql_check, params_check)
                if count > 0:
                    init.logger.info(f"[{result.get('title')}]检测到相同磁力链接(Hash: {magnet_hash})已存在，跳过入库！")
                    continue  # 已存在，跳过
                
                # 判断数据完整性
                if not result.get('section_name') or \
                    not result.get('av_number') or \
                    not result.get('title') or \
                    not result.get('magnet') or \
                    not result.get('size') or \
                    not result.get('movie_type') or \
                    not result.get('post_url') or \
                    not result.get('publish_date') or \
                    not result.get('pub_url') or \
                    not specify_path or \
                    not result.get('image_path'):
                    init.logger.warn(f"数据不完整，跳过入库: {result}")
                    continue
                
                if check_magnet(result.get('magnet')) is False:
                    init.logger.warn(f"[{result.get('magnet')}]磁力链接格式不正确，跳过入库!")
                    continue
                
                # 插入数据
                insert_query = '''
                INSERT INTO sehua_data (section_name, av_number, title, movie_type, size, magnet, post_url, publish_date, pub_url, image_path, save_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                '''
                params_insert = (
                        result.get('section_name'),
                        result.get('av_number'),
                        result.get('title'),
                        result.get('movie_type'),
                        result.get('size'),
                        result.get('magnet'),
                        result.get('post_url'),
                        result.get('publish_date'),
                        result.get('pub_url'),
                        result.get('image_path'),
                        specify_path
                    )
                sqlite.execute_sql(insert_query, params_insert)
                insert_count += 1
                
            init.logger.info(f"涩花[{results[0].get('section_name')}]版块，[{results[0].get('publish_date')}]日，[{insert_count}]条数据入库成功!")
    except Exception as e:
        init.logger.error(f"保存涩花数据到数据库时出错: {str(e)}")
        
        
def is_title_allowed(section_name, title):
    yaml_path = init.STRATEGY_FILE
    strategy_config = read_yaml_file(yaml_path)
    if not strategy_config:
        return True
    
    if strategy_config:
        title_regular = strategy_config.get('title_regular', [])
        if not title_regular:
            return True
        
        section_has_rules = False
        for item in title_regular:
            if item.get('section_name', '') == section_name:
                section_has_rules = True
                break
        
        if not section_has_rules:
            return True
        
        for item in title_regular:
            if item.get('section_name', '') == section_name:
                pattern = item.get('pattern', '')
                if not pattern:
                    continue
                if re.search(pattern, title, re.IGNORECASE):
                    return True
        
        return False
        
    return True


def match_strategy(result):
    yaml_path = init.STRATEGY_FILE
    strategy_config = read_yaml_file(yaml_path)
    if not strategy_config:
        return True, result.get('save_path')
    
    if strategy_config:
        title_regular = strategy_config.get('title_regular', [])
        if not title_regular:
            return True, result.get('save_path')
        
        current_section = result.get('section_name', '')
        section_has_rules = False
        
        # 检查当前section是否有配置规则
        for item in title_regular:
            if item.get('section_name', '') == current_section:
                section_has_rules = True
                break
        
        # 如果当前section没有配置规则，默认全部通过
        if not section_has_rules:
            return True, result.get('save_path')
        
        # 有配置规则的section，需要匹配正则
        for item in title_regular:
            if item.get('section_name', '') == current_section:
                pattern = item.get('pattern', '')
                if not pattern:
                    continue
                if re.search(pattern, result.get('title', ''), re.IGNORECASE):
                    strategy_name = item.get('strategy_name', item.get('name', '未知策略'))
                    init.logger.info(f"标题[{result.get('title', '')}]匹配正则[{strategy_name}]成功!")
                    # 正确处理空值：如果specify_save_path为空值，使用默认路径
                    specify_path = item.get('specify_save_path') or result.get('save_path')
                    return True, specify_path
        
        # 有配置规则但都不匹配（理论上不应发生，因为已提前过滤），回退到默认路径
        return True, result.get('save_path')
        
    # 空的配置等同于无效策略，默认全部通过
    return True, result.get('save_path')


def get_sehua_save_path(_section_name):
    sections = init.bot_config.get('sehua_spider', {}).get('sections', [])
    for section in sections:
        section_name = section.get('name', '')
        if section_name == _section_name:
            return section.get('save_path', f'/AV/涩花/{section_name}')
    return f'/AV/涩花/{_section_name}'


if __name__ == "__main__":
    init.load_yaml_config()
    init.create_logger()
    init.init_db()
    sehua_spider_by_date("2025-09-25")