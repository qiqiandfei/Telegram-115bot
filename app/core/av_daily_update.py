import requests
from app.utils.sqlitelib import *
import datetime
from bs4 import BeautifulSoup
import init
import time
import re
from app.utils.message_queue import add_task_to_queue
import urllib3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from offline_task_retry import av_daily_offline
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_max_page(html_content):    
    """
    获取最新AV的最大页数
    :return: 最大页数
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    # 查找所有的页码链接
    page_links = soup.select('ul.pagination-list li a.pagination-link')
    page_numbers = []
    for link in page_links:
        href = link.get('href')
        if href and 'page=' in href:
            # 从href中提取页码数字
            page_num = int(href.split('page=')[1])
            page_numbers.append(page_num)
        elif link.text.isdigit():
            # 如果链接没有href但有数字文本
            page_numbers.append(int(link.text))
    max_page = 1
    if page_numbers:
        max_page = max(page_numbers)
    return max_page

def get_today_av():
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    url = f"https://javbee.vip/date/{date}"
    response = requests.get(url, verify=False)
    if response.status_code == 500:
        init.logger.warn(f"服务器响应错误，可能是[{date}]尚未更新。")
        return None
    if response.status_code != 200:
        init.logger.warn(f"获取[{date}]日更信息错误，HTTP Code: {response.status_code}")
        return None
    
    # 抓取磁力
    return crawl_javbee(url, response.text, date)


def get_av_by_date(date):
    url = f"https://javbee.vip/date/{date}"
    response = requests.get(url, verify=False)
    if response.status_code == 500:
        init.logger.warn(f"服务器响应错误，可能是[{date}]尚未更新。")
        return None
    if response.status_code != 200:
        init.logger.warn(f"获取[{date}]日更信息错误，HTTP Code: {response.status_code}")
        return None
    
    # 抓取磁力
    return crawl_javbee(url, response.text, date)
       
    
    
def crawl_javbee(url, html_content, publish_date):
    max_page = get_max_page(html_content)
    if not max_page:
        return None
    else:
        results = []
        for page in range(1, max_page + 1):
            page_url = f"{url}?page={page}"
            response = requests.get(page_url, verify=False)
            soup = BeautifulSoup(response.text, 'html.parser')
            cards = soup.find_all('div', class_='card mb-3')
            for card in cards:
                # 1. 提取番号+标题（从<h5>中的<a>标签）
                title_tag = card.select_one('h5.title a')
                if title_tag:
                    pub_url = title_tag['href'] if title_tag.has_attr('href') else "N/A"
                    full_text = title_tag.get_text(strip=True)  # 获取纯文本
                    parts = full_text.strip().split(' ')  # 按空格分割
                    av_number, av_title = get_avnumber_title(parts)
                else:
                    av_number, av_title, pub_url = "N/A", "N/A", "N/A"

                # 2. 提取封面（从<img>的data-src属性）
                img_tag = card.find('img', class_='image lazy')
                cover_url = img_tag['data-src'] if img_tag and img_tag.has_attr('data-src') else "N/A"
                
                # 3. 提取磁力链接（关键新增部分）
                magnet_tag = card.find('a', title="Download Magnet")
                magnet_url = magnet_tag['href'] if magnet_tag and magnet_tag.has_attr('href') else "N/A"
                magnet_url = get_minimal_magnet(magnet_url)  # 获取最小化的磁力链接
    
                if av_number == "N/A" or av_title == "N/A" or magnet_url == "N/A":
                    break
                # 保存结果
                results.append({
                    'av_number': av_number,
                    'av_title': av_title,
                    'cover_url': cover_url,
                    'magnet_url': magnet_url,
                    'publish_date': publish_date,
                    'pub_url': pub_url
                })
            time.sleep(3)  # 避免请求过快
        return results
    
    
def get_yesterday_av():
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    date = yesterday.strftime("%Y-%m-%d")
    url = f"https://javbee.vip/date/{date}"
    response = requests.get(url, verify=False)
    if response.status_code == 500:
        init.logger.warn(f"服务器响应错误，可能是[{date}]尚未更新。")
        return None
    if response.status_code != 200:
        init.logger.warn(f"获取[{date}]日更信息错误，HTTP Code: {response.status_code}")
        return None
    # 抓取磁力
    return crawl_javbee(url, response.text, date)


def check_yesterday_exists():
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    date = yesterday.strftime("%Y-%m-%d")
    with SqlLiteLib() as sqlite:
        sql = "SELECT COUNT(*) FROM av_daily_update WHERE publish_date=?"
        count = sqlite.query_one(sql, (date,))
        return count is not None and count > 0


def save_av_daily_update2db(results):
    with SqlLiteLib() as sqlite:
        for item in results:
            av_number = item['av_number']
            publish_date = item['publish_date']
            title = item['av_title']
            post_url = item['cover_url']
            magnet = item['magnet_url']
            pub_url = item['pub_url']

            if not av_number or not publish_date or not title or not magnet or not pub_url:
                init.logger.warn(f"跳过无效的AV记录，番号: {av_number}, 标题: {title}, 发布链接: {pub_url}")
                continue
            
            # 检查是否已存在相同的记录
            sql_check = "SELECT COUNT(*) FROM av_daily_update WHERE av_number=? AND publish_date=?"
            params_check = (av_number, publish_date)
            count = sqlite.query_one(sql_check, params_check)
            
            if count is not None and count > 0:
                init.logger.info(f"AV {av_number} 已存在，跳过保存。")
                continue
            
            from app.core.sehua_spider import check_magnet
            if check_magnet(result.get('magnet')) is False:
                init.logger.warn(f"磁力链接格式不正确，跳过入库: {result.get('magnet')}")
                continue
            
            # 插入新记录
            sql_insert = """
                INSERT INTO av_daily_update (av_number, publish_date, title, post_url, magnet, pub_url)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            params_insert = (av_number, publish_date, title, post_url, magnet, pub_url)
            sqlite.execute_sql(sql_insert, params_insert)
            init.logger.info(f"AV日更 {av_number} 保存成功。")   
            
def av_daily_update():
    # 检查配置是否启用AV日更
    if not init.bot_config.get('av_daily_update', {}).get('enable', False):
        init.logger.info("AV日更功能未启用，跳过更新。")
        return
    
    # 如果昨天漏更了，再次尝试获取昨天的更新
    yesterday_results = []
    if not check_yesterday_exists():
        init.logger.info("昨天的AV更新记录不存在，尝试获取昨天的AV更新...")
        yesterday_results = get_yesterday_av()

    # 获取今天的AV更新
    today_results = []
    init.logger.info("开始获取今天的AV更新...")
    today_results = get_today_av()
    
    results = []
    # 合并昨天和今天的结果
    if yesterday_results:
        results.extend(yesterday_results)
    if today_results:
        results.extend(today_results)

    if results:
        # 保存到数据库
        save_av_daily_update2db(results)
        init.logger.info("AV日更数据保存成功。")
        # 离线到115
        av_daily_offline()
    else:
        init.logger.info("没有找到最新的AV更新。")  
        
        
def crawl_javbee_by_date(date):
    init.logger.info(f"开始获取{date}的AV更新...")
    results = get_av_by_date(date)
    if results:
        # 保存到数据库
        save_av_daily_update2db(results)
        init.logger.info(f"{date}日AV数据保存成功。")
        # 离线到115
        av_daily_offline()
    else:
        init.logger.info(f"{date}没有找到AV更新。")  
    init.CRAWL_JAV_STATUS = 0
    
    
def repair_leak():
    if not init.bot_config.get('av_daily_update', {}).get('enable', False):
        return
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    need_update = False
    with SqlLiteLib() as sqlite:
        sql = "select COUNT(*) from av_daily_update where publish_date=?"
        count = sqlite.query_one(sql, (date,))
        if count is not None and count == 0:
            need_update = True
    if need_update:
        av_daily_update()
        
        
def get_minimal_magnet(magnet_link):
    return re.sub(r"(&dn=.*|&tr=.*)", "", magnet_link)

def has_cjk_chars(text):
    """检查字符串是否包含中文或日文字符"""
    pattern = re.compile(
        r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\u31f0-\u31ff\uff65-\uff9f]'
    )
    return bool(pattern.search(text))

def is_pure_number(s):
    """检查是否为纯数字"""
    return bool(re.fullmatch(r'^\d+$', s)) 

def has_letters_and_digits(s):
    """检查是否同时包含英文和数字（允许-和_）"""
    return bool(re.fullmatch(r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d\-_]+$', s))

def get_avnumber_title(parts):
    longest = 0
    longest_index = -1
    av_number = "N/A"
    av_title = "N/A"
    for i, part in enumerate(parts):
        if len(part) > longest and has_cjk_chars(part):
            longest = len(part)
            longest_index = i
        if longest_index != -1:
            av_title = parts[longest_index] 
        if (is_pure_number(part) or has_letters_and_digits(part)) and i != len(parts) - 1:
            av_number = part
    return av_number, av_title


if __name__ == "__main__":
    # tmp = " FC2-PPV-4747086 モ無/フェラ/□り/ 18歳ユウカちゃん・ふとした瞬間に大胆になる普段は大人しい□りの欲求不満爆発サイン ".strip()
    # parts = tmp.split(' ')
    # av_number, av_title = get_avnumber_title(parts)
    # print(f"番号: {av_number}, 标题: {av_title}")
    # tmp = " [FHD] ABF-260 神テクたったの10分間我慢することが出来れば…ご褒美なま中出し 八掛うみ【限定特典映像35分付き】".strip()
    # parts = tmp.split(' ')
    # av_number, av_title = get_avnumber_title(parts)
    # print(f"番号: {av_number}, 标题: {av_title}")
    # tmp = " FC2-PPV-4739066 【素人・玲】 ".strip()
    # parts = tmp.split(' ')
    # av_number, av_title = get_avnumber_title(parts)
    # print(f"番号: {av_number}, 标题: {av_title}")
    # tmp = " FC2-PPV-4735332 撮影に協*してくれた小柄な新卒OLをおもちゃ責めしちゃいました IMEDAMAFC2 ".strip()
    # parts = tmp.split(' ')
    # av_number, av_title = get_avnumber_title(parts)
    # print(f"番号: {av_number}, 标题: {av_title}")
    # date = datetime.datetime.now() - datetime.timedelta(days=1)
    # print(f"昨天日期: {date.strftime('%Y-%m-%d')}")
    url = f"https://javbee.vip/date/2025-08-26"
    response = requests.get(url, verify=False)
    result = crawl_javbee(url, response.text, '2025-08-26')
    for item in result:
        print(item['av_number'], item['av_title'], item['magnet_url'])