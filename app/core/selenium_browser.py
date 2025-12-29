import asyncio
import re
import time
import os
import requests
import json
from concurrent.futures import ThreadPoolExecutor
from selenium.webdriver.common.by import By
import init
from seleniumbase import SB
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Flaresolverr 配置
# 优先读取环境变量，默认使用 docker-compose 内部服务名
FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL", "http://flaresolverr:8191/v1")

class SeleniumBrowser:
    def __init__(self, base_url=None):
        self.base_url = base_url
        self.driver = None
        self.sb_context = None
        self.executor = ThreadPoolExecutor(max_workers=1)

    async def init_browser(self):
        await asyncio.get_running_loop().run_in_executor(self.executor, self._init_driver)

    def _init_driver(self):
        # 定义启动参数
        sb_config = {
            "uc": True,
            "agent": init.USER_AGENT,
            "chromium_arg": "--no-sandbox --disable-gpu --disable-dev-shm-usage --disable-blink-features=AutomationControlled --disable-infobars"
        }

        # 尝试列表: 先尝试 headless2=True (新版无头), 失败则尝试 headless=True (标准无头)
        modes = [
            {"headless2": True, "name": "headless2"},
            {"headless": True, "name": "headless"}
        ]

        for mode in modes:
            try:
                mode_name = mode.pop("name")
                init.logger.info(f"正在初始化 SeleniumBase 浏览器 (模式: {mode_name})...")
                
                # 合并配置
                config = sb_config.copy()
                config.update(mode)
                
                self.sb_context = SB(**config)
                self.sb = self.sb_context.__enter__()
                self.driver = self.sb.driver 
                
                # 额外的反检测脚本
                try:
                    self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                        "source": """
                            Object.defineProperty(navigator, 'webdriver', {
                                get: () => undefined
                            });
                        """
                    })
                except:
                    pass

                if self.base_url:
                    if not self.base_url.startswith('http'):
                        self.base_url = f"https://{self.base_url}"
                    self.driver.get(self.base_url)
                
                init.logger.info(f"SeleniumBase 浏览器初始化成功 (模式: {mode_name})")
                return # 初始化成功，直接返回

            except Exception as e:
                init.logger.warn(f"SeleniumBase 初始化失败 (模式: {mode_name}): {e}")
                # 清理可能部分初始化的资源
                try:
                    if self.sb_context:
                        self.sb_context.__exit__(None, None, None)
                except:
                    pass
                self.sb_context = None
                self.driver = None
                # 继续下一次循环尝试

        init.logger.error("SeleniumBase 浏览器所有模式初始化均失败")

    async def close(self):
        try:
            if self.sb_context:
                init.logger.info("正在关闭 SeleniumBase 浏览器并清理环境...")
                # 使用 run_in_executor 包装同步的 __exit__ 操作
                await asyncio.get_running_loop().run_in_executor(
                    self.executor, 
                    self.sb_context.__exit__, 
                    None, None, None
                )
                init.logger.info("浏览器清理完成")
        except Exception as e:
            init.logger.error(f"关闭浏览器时发生错误: {e}")
        finally:
            # 确保引用被重置，防止重入
            self.driver = None
            self.sb_context = None

    async def goto(self, url):
        await asyncio.get_running_loop().run_in_executor(self.executor, self._goto_sync, url)

    def _goto_sync(self, url):
        if self.driver:
            try:
                self.driver.get(url)
                time.sleep(2)
            except Exception as e:
                init.logger.warn(f"Selenium导航失败: {e}")

    async def get_page_source(self):
        return await asyncio.get_running_loop().run_in_executor(self.executor, lambda: self.driver.page_source if self.driver else "")

    async def get_cookies(self):
        return await asyncio.get_running_loop().run_in_executor(self.executor, lambda: self.driver.get_cookies() if self.driver else [])

    async def get_current_url(self):
        return await asyncio.get_running_loop().run_in_executor(self.executor, lambda: self.driver.current_url if self.driver else "")

    async def execute_script(self, script, *args):
        return await asyncio.get_running_loop().run_in_executor(self.executor, lambda: self.driver.execute_script(script, *args) if self.driver else None)

    async def execute_async_script(self, script, *args):
        return await asyncio.get_running_loop().run_in_executor(self.executor, lambda: self.driver.execute_async_script(script, *args) if self.driver else None)

    async def click_text(self, text):
        await asyncio.get_running_loop().run_in_executor(self.executor, self._click_text_sync, text)

    def _click_text_sync(self, text):
        if not self.driver: return
        try:
            # Try xpath
            elem = self.driver.find_element(By.XPATH, f"//*[contains(text(), '{text}')]")
            elem.click()
            time.sleep(2)
        except Exception as e:
            init.logger.debug(f"点击文本 '{text}' 失败: {e}")

    async def wait_for_element(self, selector, by=By.CSS_SELECTOR, timeout=30):
        await asyncio.get_running_loop().run_in_executor(self.executor, self._wait_for_element_sync, selector, by, timeout)

    def _wait_for_element_sync(self, selector, by, timeout):
        if not self.driver: return
        try:
            WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located((by, selector)))
        except: pass

    async def pass_cloudflare_check(self):
        await asyncio.get_running_loop().run_in_executor(self.executor, self._pass_cloudflare_check_sync)

    def _pass_cloudflare_check_sync(self):
        if not self.driver:
            return

        try:
            # 1. 检查是否是 Cloudflare 页面
            title = self.driver.title
            if not title or not any(x in title for x in ["Just a moment", "Cloudflare", "请稍候", "安全检查"]):
                return

            init.logger.info(f"检测到 Cloudflare 验证 ({title})，尝试使用 Flaresolverr 处理...")
            
            # 获取当前URL
            current_url = self.driver.current_url
            if not current_url:
                return

            # 2. 调用 Flaresolverr
            payload = {
                "cmd": "request.get",
                "url": current_url,
                "maxTimeout": 60000
            }
            headers = {"Content-Type": "application/json"}
            
            init.logger.info(f"请求 Flaresolverr: {FLARESOLVERR_URL}")
            response = requests.post(FLARESOLVERR_URL, json=payload, headers=headers, timeout=65)
            resp_data = response.json()
            
            if resp_data.get("status") == "ok":
                init.logger.info("Flaresolverr 验证成功，正在同步 Cookies...")
                solution = resp_data.get("solution", {})
                cookies = solution.get("cookies", [])
                user_agent = solution.get("userAgent")

                # 3. 同步 User-Agent (关键)
                if user_agent:
                    init.logger.info(f"同步 Flaresolverr User-Agent: {user_agent[:50]}...")
                    try:
                        self.driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": user_agent})
                    except Exception as e:
                        init.logger.warn(f"设置 User-Agent 失败: {e}")
                
                # 4. 同步 Cookies
                if cookies:
                    self.driver.delete_all_cookies()
                    for cookie in cookies:
                        cookie_dict = {
                            'name': cookie['name'],
                            'value': cookie['value'],
                            'domain': cookie['domain'],
                            'path': cookie['path']
                        }
                        if 'expiry' in cookie: cookie_dict['expiry'] = int(cookie['expiry'])
                        if 'secure' in cookie: cookie_dict['secure'] = cookie['secure']
                        if 'httpOnly' in cookie: cookie_dict['httpOnly'] = cookie['httpOnly']
                        if 'sameSite' in cookie: cookie_dict['sameSite'] = cookie['sameSite']
                            
                        try:
                            self.driver.add_cookie(cookie_dict)
                        except Exception as e:
                            pass # 忽略个别 cookie 错误
                    
                    init.logger.info(f"成功同步 {len(cookies)} 个 Cookies，刷新页面...")
                    self.driver.refresh()
                    time.sleep(5)
                    
                    # 再次检查
                    title = self.driver.title
                    if any(x in title for x in ["Just a moment", "Cloudflare", "请稍候", "安全检查"]):
                        init.logger.warn("同步 Cookie 后依然显示 Cloudflare 验证页")
                    else:
                        init.logger.info("Cloudflare 验证已通过")
            else:
                init.logger.error(f"Flaresolverr 返回错误: {resp_data}")

        except Exception as e:
            init.logger.warn(f"Cloudflare 验证处理出错: {e}")

    async def run_with_driver(self, func, *args):
        """在 executor 中运行同步函数，并将 driver 作为第一个参数传入"""
        return await asyncio.get_running_loop().run_in_executor(self.executor, func, self.driver, *args)

