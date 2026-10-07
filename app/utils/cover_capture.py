# -*- coding: utf-8 -*-
import os
import sys
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)
sys.path.append(current_dir)
import requests
from bs4 import BeautifulSoup
import init
import asyncio
import time
from typing import TypedDict
from app.core.selenium_browser import SeleniumBrowser


class MovieInfo(TypedDict):
    movie_name: str
    year: int | None
    brief: str
    post_url: str


def get_movie_cover_by_api(query: str, year: int | None = None) -> MovieInfo:
    """
    通过TMDB API获取电影名称、上映年份、简介和封面URL
    API Key读取顺序: config.yaml 的 tmdb_api_key，其次环境变量 TMDB_API_KEY
    同时支持 v3 API Key 和 v4 Read Access Token(Bearer)
    :param query: 电影名称
    :param year: 可选，上映年份
    :return: 电影信息字典；请求失败或无结果时字段使用默认值
    """
    movie_info = {
        "movie_name": query,
        "year": year,
        "brief": "",
        "post_url": "",
    }
    api_key = str(init.bot_config.get('tmdb_api_key', '')).strip()
    if not api_key or api_key.lower() == "your_tmdb_api_key":
        init.logger.warning("未配置TMDB API Key(tmdb_api_key)")
        return movie_info
    headers = {"accept": "application/json", "user-agent": init.USER_AGENT}
    params = {"query": query, "language": "zh-CN", "include_adult": "false", "page": 1}
    if year:
        params["year"] = year
    # v4 token 是JWT(以eyJ开头)，用Bearer；否则作为v3 api_key
    if api_key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        params["api_key"] = api_key
    try:
        response = requests.get("https://api.themoviedb.org/3/search/movie",
                                headers=headers, params=params, timeout=15)
        if response.status_code != 200:
            init.logger.warn(f"TMDB API请求失败: {response.status_code}")
            return movie_info
        results = response.json().get("results", [])
        if not results:
            init.logger.info(f"TMDB未找到匹配电影: {query}")
        # 优先标题完全匹配且有海报的结果，否则取第一个有海报的结果
        with_poster = [r for r in results if r.get("poster_path")]
        candidates = with_poster or results
        if not candidates:
            return movie_info
        matched = next((r for r in candidates
                        if query in (r.get("title"), r.get("original_title"))), candidates[0])
        release_date = matched.get("release_date") or ""
        if isinstance(release_date, str) and release_date[:4].isdigit():
            movie_info["year"] = int(release_date[:4])
        movie_info["movie_name"] = matched.get("title") or matched.get("original_title") or query
        movie_info["brief"] = matched.get("overview") or ""
        if matched.get("poster_path"):
            movie_info["post_url"] = f"https://image.tmdb.org/t/p/w500{matched['poster_path']}"
        return movie_info
    except Exception as e:
        init.logger.error(f"TMDB API获取封面失败: {e}")
        return movie_info


def get_av_cover(query):
    title = f"[{query}]已下好，但源没抓到~"
    cover_url = f"{init.IMAGE_PATH}/no_image.png"
    
    async def _async_get_av_cover():
        nonlocal title, cover_url
        browser = SeleniumBrowser("https://avmoo.website/cn")
        
        try:
            await browser.init_browser()
            if not browser.driver:
                return

            search_url = f"https://avmoo.website/cn/search/{query}"
            await browser.goto(search_url)
            html = await browser.get_page_source()
            soup = BeautifulSoup(html, 'html.parser')
            # 找到class为"item"的div
            item_div = soup.find('div', class_='item')
            if not item_div:
                return
            # 在item_div中找到a标签，class为"movie-box"
            movie_link = item_div.find('a', class_='movie-box')
            if not movie_link:
                return
            link = movie_link['href']  # 获取href属性
            if link and link.startswith('//'):
                link = f"https:{link}"
            img_tag = movie_link.find('img')
            if img_tag:
                title = img_tag['title']
            
            await browser.goto(link)
            html = await browser.get_page_source()
            soup = BeautifulSoup(html, 'html.parser')
            screencap_div = soup.find('div', class_='screencap')
            if screencap_div:
                big_image_link = screencap_div.find('a', class_='bigImage')
                if big_image_link:
                    cover_url = big_image_link['href'] 
        except Exception as e:
            init.logger.error(f"获取AV封面内部错误: {e}")
        finally:
            await browser.close()

    try:
        asyncio.run(_async_get_av_cover())
    except Exception as e:
        init.logger.error(f"获取AV封面失败: {e}")
        
    return cover_url, title

def is_av_exist(div_list):
    """
    判断搜索结果是否存在
    :param div_list:
    :return:
    """
    is_found = True
    # 倒序遍历提高效率
    for div in reversed(div_list):
        if 'class' in div.attrs:
            if div['class'][0] == 'empty-message':
                is_found = False
                break
    return is_found


if __name__ == '__main__':
    # init.create_logger()
    init.load_yaml_config()
    # tmdb_id = get_tmdb_id("死人", 20)
    # print(f"TMDB ID: {tmdb_id}")
    movie_info = get_movie_cover_by_api("沙漠战士")
    print(f"电影信息: {movie_info}")
    # init.load_yaml_config()
    # init.create_logger()
    # cover_url, title = get_av_cover("ipz-466")
    # print(f"封面URL: {cover_url}")
    # print(f"标题: {title}")