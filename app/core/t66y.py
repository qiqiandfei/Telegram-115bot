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
from app.utils.utils import *
from datetime import datetime, timedelta, date
import yaml
import os
import re
import json
import requests
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from app.core.offline_task_retry import t66y_offline
from app.core.selenium_browser import SeleniumBrowser
from telegram.helpers import escape_markdown
import html
import asyncio
import time
from selenium.webdriver.common.by import By

def _extract_magnet_sync(driver, url):
    """
    同步执行的磁力链接提取逻辑 (运行在 executor 中)
    """
    if not driver:
        return ""
    
    init.logger.info(f"正在提取磁力链接: {url}")
    try:
        # rmdown 特殊处理
        if "rmdown.com" in url:
            try:
                # 尝试授予剪贴板权限
                try:
                    driver.execute_cdp_cmd("Browser.grantPermissions", {
                        "origin": url,
                        "permissions": ["clipboardReadWrite", "clipboardSanitizedWrite"]
                    })
                except:
                    pass

                # 等待按钮出现并点击
                cbtn = driver.find_elements(By.ID, "cbtn")
                if cbtn:
                    cbtn[0].click()
                    time.sleep(1)
                    
                    # 尝试从剪贴板读取
                    magnet = driver.execute_async_script("""
                        var callback = arguments[arguments.length - 1];
                        navigator.clipboard.readText()
                            .then(text => callback(text))
                            .catch(err => callback(''));
                    """)
                    
                    if magnet:
                        # 如果不是以magnet:开头，尝试拼接
                        if not magnet.startswith("magnet:"):
                            magnet = f"magnet:?{magnet}"
                        
                        # 清理tracker，只保留xt
                        try:
                            from urllib.parse import urlparse, parse_qs
                            parsed = urlparse(magnet)
                            params = parse_qs(parsed.query)
                            xt = params.get('xt', [])
                            if xt:
                                magnet = f"magnet:?xt={xt[0]}"
                        except:
                            pass

                        if magnet.startswith("magnet:"):
                            init.logger.info("成功从剪贴板获取磁力链接")
                            return magnet
            except Exception as e:
                init.logger.warn(f"rmdown 处理失败: {e}")
            
            # rmdown 只有剪贴板这一种获取方式，如果失败直接返回空
            return ""

        # 通用磁力链接提取
        page_source = driver.page_source
        magnet_pattern = re.compile(r"magnet:\?xt=urn:btih:[a-zA-Z0-9]{32,40}", re.IGNORECASE)
        
        # 1. 检查页面源码中的文本
        match = magnet_pattern.search(page_source)
        if match:
            return match.group(0)
        
        # 2. 检查所有链接的 href
        links = driver.find_elements(By.TAG_NAME, "a")
        for link in links:
            try:
                href = link.get_attribute("href")
                if href and magnet_pattern.search(href):
                    return href
            except:
                continue

    except Exception as e:
        init.logger.error(f"提取磁力链接失败: {e}")
        
    return ""

async def fetch_t66y_magnet(browser, url):
    """
    t66y 专用的磁力链接获取函数
    """
    # 1. 访问页面
    await browser.goto(url)
    
    # 2. 过盾检查
    await browser.pass_cloudflare_check()
    
    # 3. 提取磁力 (在 executor 中运行同步逻辑)
    return await browser.run_with_driver(_extract_magnet_sync, url)


def parse_t66y_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    
    # 1. Extract Poster (First Image)
    poster_url = ""
    img_tag = soup.find("img")
    if img_tag:
        poster_url = img_tag.get("src", "")
        
    # 2. Extract Magnet
    magnet = ""
    magnet_pattern = re.compile(r"magnet:\?xt=urn:btih:[a-zA-Z0-9]{32,40}", re.IGNORECASE)
    
    if magnet_pattern.search(html_content):
        magnet = magnet_pattern.search(html_content).group(0)

    if not magnet:
        # Use the last link
        all_links = soup.find_all("a", href=True)
        if all_links:
            last_link = all_links[-1]["href"]
            

    # 3. Extract Movie Info
    # Create a copy of soup to manipulate for text extraction
    info_soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove images
    for img in info_soup.find_all("img"):
        img.decompose()
        
    # Replace br with newline
    for br in info_soup.find_all("br"):
        br.replace_with("\n")

    return {
        "poster_url": poster_url,
        "magnet": magnet,
        "fetch_url": last_link if not magnet and 'last_link' in locals() else ""
    }

def clean_magnet(magnet_link):
    """
    Clean magnet link, remove trackers and other parameters, keep only xt.
    """
    if not magnet_link:
        return ""
    try:
        parsed = urlparse(magnet_link)
        if parsed.scheme != 'magnet':
            return magnet_link
        
        params = parse_qs(parsed.query)
        xt = params.get('xt', [])
        if xt:
            return f"magnet:?xt={xt[0]}"
    except:
        pass
    return magnet_link



def get_section_id(section_name):
    section_map = {
        "亚洲无码原创": 2,
        "亚洲有码原创": 15,
        "欧美原创": 4,
        "动漫原创": 5,
        "国产原创": 25,
        "中字原创": 26,
        "AI破解原创": 28
    }
    return section_map.get(section_name, 0)


async def _start_t66y_rss_async():
    
    t66y = init.bot_config.get("rsshub", {}).get("t66y", None)
    if not t66y or not t66y.get("enable", False):
        init.logger.info("t66y RSS订阅未配置，跳过RSS订阅任务")
        return

    browser = None
    
    try:
        # Initialize browser
        rss_host = init.bot_config.get('rsshub', {}).get('rss_host', '')
        browser = SeleniumBrowser(rss_host)
        await browser.init_browser()
        
        if not browser.driver:
             init.logger.error("浏览器初始化失败，无法继续任务")
             return

        for section in t66y.get("sections", []):
            section_id = get_section_id(section.get("name", ""))
            if section_id == 0:
                init.logger.warning(f"未知的t66y版块名称: {section.get('name', '')}，跳过该版块的RSS订阅")
                continue
            rss_url = f"{rss_host}/t66y/{section_id}/today?format=json"
            response = requests.get(rss_url, timeout=30)
            if response.status_code != 200:
                init.logger.error(f"无法获取t66y RSS订阅，HTTP状态码: {response.status_code}")
                continue
            pares_results = []
            rss_data = response.json()
            pares_results.extend(await pares_t66y_rss(rss_data, section.get("name", ""), section.get("save_path", ""), browser))
            # Insert into database
            save2DB_t66y(pares_results)
        # 离线到115
        t66y_offline()
    except Exception as e:
        init.logger.error(f"处理t66y RSS订阅时出错: {e}")
    finally:
        if browser:
            await browser.close()
        init.RSS_T66Y_STATUS = 0

def start_t66y_rss():
    asyncio.run(_start_t66y_rss_async())

async def pares_t66y_rss(rss_data, section_name, save_path, browser):
    items = rss_data.get("items", [])
    pares_results = []
    for item in items:
        try:
            content_html = item.get("content_html", "")
            # 多部影片一起发的直接跳过
            if content_html.count("【影片名称】") > 1 \
                or content_html.count("【影片名稱】") > 1 \
                or content_html.count("【影片标题】") > 1 \
                or content_html.count("【影片標題】") > 1:
                continue
            parsed_data = parse_t66y_html(content_html)
            title = item.get("title", "")
            pub_url = item.get("url", "")
            # 转换发布时间为北京时间
            date_published = date_convert2BJT(item.get("date_published", ""))
            poster_url = parsed_data.get("poster_url", "")
            magnet = parsed_data.get("magnet", "")
            fetch_url = parsed_data.get("fetch_url", "")
            
            # 点击连接获取磁力
            if not magnet and fetch_url:
                magnet = await fetch_t66y_magnet(browser, fetch_url)
                
            if not magnet:
                # invalid_resource = json.dumps(result)
                init.logger.warn(f"跳过无效的t66y资源...")
                continue
            
            magnet = clean_magnet(magnet)
            
            safe_title = escape_markdown(title, version=2)
            safe_date = escape_markdown(str(date_published), version=2)
            safe_magnet = escape_markdown(magnet, version=2)
            safe_pub_url = escape_markdown(pub_url, version=2)

            movie_info = f"""
                            **t66y订阅通知**
                            
                            **标题：**    {safe_title}
                            **发布日期：**    {safe_date}
                            **下载链接：**    `{safe_magnet}`
                            **发布链接：**    [点击查看详情]({safe_pub_url})
                           """
            
            result = {
                        "section_name": section_name,
                        "save_path": save_path,
                        "title": title,
                        "movie_info": movie_info,
                        "poster_url": poster_url,
                        "magnet": magnet,
                        "publish_date": date_published,
                        "pub_url": pub_url
                    }
            
            is_match, specify_save_path = match_strategy(result)
            if is_match:
                result['save_path'] = specify_save_path
                init.logger.info(f"成功解析t66y资源: {json.dumps(result)}")
                pares_results.append(result)
        except Exception as e:
            init.logger.error(f"解析t66y资源失败: {e}, title: {item.get('title', 'unknown')}")
    return pares_results

def save2DB_t66y(results):
    if not results:
        return
    insert_count = 0
    section_name = ""
    with SqlLiteLib() as sqlite:
        try:
            for result in results:
                title = result.get("title", "")
                pub_url = result.get("pub_url", "")
                publish_date = result.get("publish_date", "")
                movie_info = result.get("movie_info", "")
                poster_url = result.get("poster_url", "")
                magnet = result.get("magnet", "")
                section_name = result.get("section_name", "")
                save_path = result.get("save_path", "")
                
                # Check if exists
                magnet_hash = get_magnet_hash(magnet)
                if magnet_hash:
                    # 如果能提取到hash，使用模糊匹配查询
                    sql_check = "select count(*) from t66y where magnet LIKE ?"
                    params_check = (f'%{magnet_hash}%', )
                else:
                    # 提取不到hash，回退到完全匹配
                    sql_check = "select count(*) from t66y where magnet = ?"
                    params_check = (magnet, )

                count = sqlite.query_one(sql_check, params_check)
                if count > 0:
                    init.logger.info(f"[{title}]检测到相同磁力链接(Hash: {magnet_hash})已存在，跳过入库！")
                    continue  # 已存在，跳过
                
                insert_sql = """
                    INSERT INTO t66y (section_name, title, movie_info, poster_url, magnet, publish_date, pub_url, save_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """
                sqlite.execute_sql(insert_sql, (section_name, title, movie_info, poster_url, magnet, publish_date, pub_url, save_path))
                insert_count += 1
            init.logger.info(f"[{section_name}]板块新增入库 {insert_count} 条！")
        except Exception as e:
            init.logger.error(f"保存t66y资源到数据库失败: {e}, title: {result.get('title', 'unknown')}")
        
    
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
        return False, ""
        
    # 空的配置等同于无效策略，默认全部通过
    return True, result.get('save_path')


        

if __name__ == "__main__":
    init.init_log()
    init.load_yaml_config()
    start_t66y_rss()