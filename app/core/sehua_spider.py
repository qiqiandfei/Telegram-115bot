from bs4 import BeautifulSoup
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
from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError
from app.core.offline_task_retry import sehua_offline
from app.core.headless_browser import *

# 全局browser
browser = None

def get_base_url():
    base_url = init.bot_config.get('sehua_spider', {}).get('base_url', "www.sehuatang.net")
    if not base_url:
        base_url = "www.sehuatang.net"
    return base_url


def download_image(image_url, save_path):
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
    
    # 获取全局页面对象
    page = browser.get_global_page()
    if not page:
        return False, "无法获取浏览器页面"
    
    try:
        # 确保保存目录存在
        if not os.path.exists(save_path):
            os.makedirs(save_path, exist_ok=True)
            init.logger.debug(f"创建目录: {save_path}")
        
        init.logger.debug(f"开始下载外链图片: {image_url}")
        
        # 直接访问图片URL（最简单可靠的方法）
        try:
            init.logger.debug("尝试直接访问图片URL...")
            page.set_extra_http_headers({
                'Referer': f'https://{get_base_url()}/'
            })
            response = page.goto(image_url, wait_until="domcontentloaded", timeout=30000)
            
            if response and response.status == 200:
                # 检查Content-Type是否为图片
                content_type = response.headers.get('content-type', '').lower()
                init.logger.debug(f"Content-Type: {content_type}")
                
                if any(img_type in content_type for img_type in ['image/', 'jpeg', 'png', 'gif', 'webp']):
                    init.logger.debug("检测到图片内容，开始下载...")
                    
                    # 获取图片数据
                    image_data = response.body()

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
                status_code = response.status if response else "未知"
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
        "高清中文字幕": 103
    }
    return section_map.get(section_name, 0)


def sehua_spider_start():
    """完整的爬虫启动函数，包含浏览器生命周期管理"""
    global browser
    if not init.bot_config.get('sehua_spider', {}).get('enable', False):
        return
    # 初始化全局浏览器
    browser = HeadlessBrowser(get_base_url())
    
    if not browser.page:
        return
    try:
        yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
        date = yesterday.strftime("%Y-%m-%d")
        sections = init.bot_config['sehua_spider'].get('sections', [])
        for section in sections:
            section_name = section.get('name')
            init.logger.info(f"开始爬取 {section_name} 分区...")
            section_spider(section_name, date)
            init.logger.info(f"{section_name} 分区爬取完成")
            delay = random.uniform(30, 60)
            time.sleep(delay)
        # 离线到115
        init.logger.info("开始执行涩花离线任务...")
        sehua_offline()
    except Exception as e:
        init.logger.warn(f"爬取 {section_name} 分区时发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # 关闭全局浏览器
        browser.close()
        
        
def sehua_spider_by_date(date):
    """完整的爬虫启动函数，包含浏览器生命周期管理"""
    global browser
    browser = HeadlessBrowser(get_base_url())
    # 初始化全局浏览器
    if not browser.page:
        return
    try:
        sections = init.bot_config['sehua_spider'].get('sections', [])
        for section in sections:
            section_name = section.get('name')
            init.logger.info(f"开始爬取 {section_name} 分区...")
            section_spider(section_name, date)
            init.logger.info(f"{section_name} 分区爬取完成")
            delay = random.uniform(30, 60)
            time.sleep(delay)
        # 离线到115
        init.logger.info("开始执行涩花离线任务...")
        sehua_offline()
    except Exception as e:
        init.logger.warn(f"爬取 {section_name} 分区时发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # 关闭全局浏览器
        browser.close()
        init.CRAWL_SEHUA_STATUS = 0
    
    
def section_spider(section_name, date):
    
    update_list = get_section_update(section_name, date)
    
    if not update_list:
        init.logger.info(f"没有找到 {section_name} 在 {date} 的更新内容")
        return
    
    # 使用全局页面对象
    page = browser.get_global_page()
    
    successful_count = 0
    failed_count = 0
    
    results = []

    try:
        for i, topic in enumerate(update_list):
            url = f"https://{browser.base_url}/{topic}"
            init.logger.debug(f"正在处理第 {i+1}/{len(update_list)} 个话题: {url}")
            
            success = False
            max_retries = 3
            
            for retry in range(max_retries):
                try:
                    # 添加随机延迟避免被反爬虫
                    if i > 0:  # 第一个请求不延迟
                        delay = random.uniform(2, 5)
                        init.logger.debug(f"等待 {delay:.1f} 秒...")
                        time.sleep(delay)
                    
                    # 尝试访问页面
                    init.logger.debug(f"  尝试访问 (第 {retry+1} 次)...")
                    page.goto(url, wait_until="domcontentloaded")
                    
                    # 检查年龄验证
                    age_check(page)
                    
                    # 等待页面完全加载
                    page.wait_for_load_state("networkidle", timeout=30000)
                    
                    html = page.content()
                    if html and len(html) > 1000:  # 确保获取到完整页面
                        result = parse_topic(section_name, html, url, date)
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

                except PlaywrightTimeoutError as e:
                    init.logger.warn(f"第 {retry+1} 次尝试超时: {str(e)}")
                    if retry < max_retries - 1:
                        wait_time = (retry + 1) * 10  # 递增等待时间
                        init.logger.debug(f"  等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                except Exception as e:
                    init.logger.warn(f"第 {retry+1} 次尝试出错: {str(e)}")
                    if retry < max_retries - 1:
                        time.sleep(5)
            
            if not success:
                init.logger.warn(f"所有重试都失败，跳过此链接")
                failed_count += 1
                
            # 每处理5个页面后增加额外延迟
            if (i + 1) % 5 == 0:
                extra_delay = random.uniform(10, 20)
                init.logger.info(f"已处理 {i+1} 个页面，休息 {extra_delay:.1f} 秒...")
                time.sleep(extra_delay)
        
        # 写入数据库
        if results:
            save_sehua2db(results)   
            results.clear()
       
    except Exception as e:
        init.logger.warn(f"爬虫过程中发生严重错误: {str(e)}")
    finally:
        init.logger.info(f"本次爬取结束 - 成功: {successful_count}, 失败: {failed_count}")
        # 注意：这里不关闭浏览器，保持cookie
            
def parse_topic(section_name, html, url, date):
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    result['section_name'] = section_name
    result['publish_date'] = date
    result['pub_url'] = url
    result['save_path'] = get_sehua_save_path(section_name)
    title = soup.find('span', {'id': 'thread_subject'}).text
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
            success, local_path = download_image(result['post_url'], f"{init.TEMP}/sehua")
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


def get_section_update(section_name, date):
    all_data_today = []
    section_id = get_section_id(section_name)
    if section_id == 0:
        return all_data_today
    
    
    # 使用全局页面对象
    page = browser.get_global_page()
    
    try:
        for page_num in range(1, 10):
            url = f"https://{browser.base_url}/forum.php?mod=forumdisplay&fid={section_id}&page={page_num}"
            init.logger.info(f"正在获取 {section_name} 第 {page_num} 页...")
            
            success = False
            max_retries = 10
            
            for retry in range(max_retries):
                try:
                    if page_num > 1 or retry > 0:  # 第一个请求不延迟
                        delay = random.uniform(5, 10)
                        time.sleep(delay)
                    
                    # 访问目标页面
                    page.goto(url, wait_until="domcontentloaded")
                    age_check(page)
                    
                    # 等待页面完全加载
                    browser.wait_for_page_loaded(expected_elements=["tbody[id^='normalthread_']"])

                    # 获取页面 HTML
                    html = page.content()
                    if html and len(html) > 1000:
                        # 验证页面是否包含预期的内容结构
                        if 'normalthread_' in html or 'postlist' in html:
                            topics = parse_section_page(html, date, page_num)
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
                    else:
                        init.logger.warn(f"  页面内容过短，可能加载失败")
                        
                except PlaywrightTimeoutError as e:
                    init.logger.warn(f"第 {retry+1} 次尝试超时: {str(e)}")
                    if retry < max_retries - 1:
                        time.sleep((retry + 1) * 10)
                except Exception as e:
                    init.logger.warn(f"第 {retry+1} 次尝试出错: {str(e)}")
                    if retry < max_retries - 1:
                        time.sleep(5)
            
            if not success:
                init.logger.warn(f"第 {page_num} 页获取失败，跳过")
                break
                
    except Exception as e:
        init.logger.warn(f"获取列表页面时发生错误: {str(e)}")
    init.logger.info(f"总共找到 {len(all_data_today)} 个今日话题")
    return all_data_today


def parse_section_page(html_content, date, page_num):
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


def age_check(page):
    try:
        # 等待页面基本加载
        browser.wait_for_page_loaded(timeout=15000)
        
        content = page.content()
        init.logger.debug(f"  当前页面URL: {page.url}")
        init.logger.debug(f"  页面内容长度: {len(content)}")
        
        if "满18岁，请点此进入" in content:
            init.logger.info("  检测到年龄验证页面，正在点击进入...")
            try:
                page.click("text=满18岁，请点此进入", timeout=10000)
                
                # 等待页面跳转并完全加载
                init.logger.debug("  等待页面跳转和加载...")
                browser.wait_for_page_loaded(expected_elements=["tbody[id^='normalthread_']", ".t_f"])
                
                # 验证页面是否成功跳转
                new_content = page.content()
                if len(new_content) > len(content):
                    init.logger.info(f"  年龄验证通过，页面已加载 (内容长度: {len(new_content)})")
                else:
                    init.logger.warn("  页面内容似乎没有变化，可能验证失败")
                    
            except Exception as click_error:
                init.logger.warn(f"  点击年龄验证按钮失败: {str(click_error)}")
                # 尝试其他方式
                try:
                    page.get_by_text("满18岁，请点此进入").click(timeout=10000)
                    browser.wait_for_page_loaded(expected_elements=["tbody[id^='normalthread_']"])
                    init.logger.debug("  使用备用方式通过年龄验证")
                except Exception as backup_error:
                    init.logger.warn(f"  备用年龄验证方式也失败: {str(backup_error)}")
        else:
            # 即使没有年龄验证，也要等待页面完全加载
            browser.wait_for_page_loaded(expected_elements=["tbody[id^='normalthread_']"])
            
    except Exception as e:
        init.logger.warn(f"  年龄验证处理出错: {str(e)}")
        # 继续执行，不因为年龄验证失败而中断

    
        
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
                # 检查是否已存在（通过标题和发布日期判断）
                sql_check = "select count(*) from sehua_data where title = ?"
                params_check = (result.get('title'), )
                count = sqlite.query_one(sql_check, params_check)
                if count > 0:
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
        
        
def match_strategy(result):
    yaml_path = init.STRATEGY_FILE
    strategy_config = None
    # 获取yaml文件名称
    try:
        # 获取yaml文件路径
        if os.path.exists(yaml_path):
            with open(yaml_path, 'r', encoding='utf-8') as f:
                cfg = f.read()
                f.close()
            strategy_config = yaml.load(cfg, Loader=yaml.FullLoader)
        else:
           return True, result.get('save_path')
    except Exception as e:
        init.logger.warn(f"配置文件[{yaml_path}]格式有误，请检查!")
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
        
        # 有配置规则但都不匹配，放弃入库
        init.logger.info(f"标题[{result.get('title', '')}]未匹配到[{current_section}]板块的任何规则，自动放弃入库!")
        # 删除图片
        if result.get('image_path') and os.path.exists(result.get('image_path')):
            try:
                os.remove(result.get('image_path'))
                init.logger.debug(f"已删除图片: {result.get('image_path')}")
            except Exception as e:
                init.logger.warn(f"删除图片失败: {str(e)}")
        return False, ""
        
    # 空的配置等同于无效策略，默认全部通过
    return True, result.get('save_path')


def get_sehua_save_path(_section_name):
    sections = init.bot_config.get('sehua_spider', {}).get('sections', [])
    for section in sections:
        section_name = section.get('name', '')
        if section_name == _section_name:
            return section.get('save_path', f'/AV/涩花/{section_name}')
    return f'/AV/涩花/{_section_name}'

def check_magnet(magnet):
    pattern = r"^magnet:\?xt=urn:btih:([a-fA-F0-9]{40}|[a-zA-Z2-7]{32})(?:&.*)?$"
    if not isinstance(magnet, str) or not magnet.startswith('magnet:'):
        return False
    return re.fullmatch(pattern, magnet) is not None



if __name__ == "__main__":
    init.load_yaml_config()
    init.create_logger()
    init.init_db()
    sehua_spider_by_date("2025-09-25")