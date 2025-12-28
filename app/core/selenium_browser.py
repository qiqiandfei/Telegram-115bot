import asyncio
import re
import time
from concurrent.futures import ThreadPoolExecutor
from seleniumbase import Driver
from selenium.webdriver.common.by import By
import init

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class SeleniumBrowser:
    def __init__(self, base_url=None):
        self.base_url = base_url
        self.driver = None
        self.executor = ThreadPoolExecutor(max_workers=1)

    async def init_browser(self):
        await asyncio.get_running_loop().run_in_executor(self.executor, self._init_driver)

    def _init_driver(self):
        try:
            init.logger.info("正在初始化 SeleniumBase 浏览器...")
            # uc=True 开启 undetected-chromedriver 模式
            # headless=True 开启无头模式
            self.driver = Driver(uc=True, headless=True, agent=init.USER_AGENT)
            if self.base_url:
                if not self.base_url.startswith('http'):
                    self.base_url = f"https://{self.base_url}"
                self.driver.get(self.base_url)
            init.logger.info("SeleniumBase 浏览器初始化成功")
        except Exception as e:
            init.logger.error(f"SeleniumBase 浏览器初始化失败: {e}")

    async def close(self):
        if self.driver:
            await asyncio.get_running_loop().run_in_executor(self.executor, self._quit)

    def _quit(self):
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
            init.logger.info("SeleniumBase 浏览器已关闭")
        except Exception as e:
            init.logger.error(f"关闭 SeleniumBase 浏览器失败: {e}")

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

    async def fetch_magnet(self, url):
        return await asyncio.get_running_loop().run_in_executor(self.executor, self._fetch_magnet_sync, url)

    def _fetch_magnet_sync(self, url):
        if not self.driver:
            return ""
        
        init.logger.info(f"正在通过 SeleniumBase 获取磁力: {url}")
        try:
            self.driver.get(url)
            time.sleep(2) # 等待页面加载
            
            # Cloudflare 验证处理
            title = self.driver.title
            if "Just a moment" in title or "Cloudflare" in title:
                init.logger.info("检测到 Cloudflare 验证，尝试处理...")
                time.sleep(5) # 等待一下，有时会自动通过
                
                # 尝试查找并点击验证框
                try:
                    # 查找所有iframe
                    iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                    for iframe in iframes:
                        try:
                            self.driver.switch_to.frame(iframe)
                            # 尝试点击 checkbox
                            checkbox = self.driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
                            if checkbox:
                                checkbox[0].click()
                                init.logger.info("点击了 Cloudflare 验证框")
                                time.sleep(5)
                                break
                            # 尝试点击 text
                            body_text = self.driver.find_element(By.TAG_NAME, "body").text
                            if "Verify you are human" in body_text:
                                self.driver.find_element(By.TAG_NAME, "body").click() # 简单点击body试试
                                break
                        except:
                            pass
                        finally:
                            self.driver.switch_to.default_content()
                except Exception as e:
                    init.logger.warn(f"尝试点击验证框失败: {e}")

            # rmdown 特殊处理
            if "rmdown.com" in url:
                try:
                    # 尝试授予剪贴板权限
                    try:
                        self.driver.execute_cdp_cmd("Browser.grantPermissions", {
                            "origin": url,
                            "permissions": ["clipboardReadWrite", "clipboardSanitizedWrite"]
                        })
                    except:
                        pass

                    # 等待按钮出现并点击
                    cbtn = self.driver.find_elements(By.ID, "cbtn")
                    if cbtn:
                        cbtn[0].click()
                        time.sleep(1)
                        
                        # 尝试从剪贴板读取
                        magnet = self.driver.execute_async_script("""
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
            page_source = self.driver.page_source
            magnet_pattern = re.compile(r"magnet:\?xt=urn:btih:[a-zA-Z0-9]{32,40}", re.IGNORECASE)
            
            # 1. 检查页面源码中的文本
            match = magnet_pattern.search(page_source)
            if match:
                return match.group(0)
            
            # 2. 检查所有链接的 href
            links = self.driver.find_elements(By.TAG_NAME, "a")
            for link in links:
                try:
                    href = link.get_attribute("href")
                    if href and magnet_pattern.search(href):
                        return href
                except:
                    continue

        except Exception as e:
            init.logger.error(f"SeleniumBase 获取磁力失败: {e}")
            
        return ""
