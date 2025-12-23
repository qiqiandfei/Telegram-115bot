import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import init
from telegram.helpers import escape_markdown
from app.utils.message_queue import add_task_to_queue

class HeadlessBrowser:
    def __init__(self, _base_url):
        self.playwright = None
        self.browser = None
        self.page = None
        self.context = None
        self.base_url = _base_url
        # self.init_browser() # 异步初始化需要在外部调用

    async def init_browser(self):
        """初始化全局浏览器实例"""
        init.logger.info("正在初始化浏览器...")
        
        try:
            self.playwright = await async_playwright().start()
            # 启动浏览器（无头模式）- 添加更多配置选项
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-first-run',
                    '--no-zygote',
                    '--disable-gpu'
                ]
            )
            
            self.context = await self.browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent=init.USER_AGENT
            )

            self.page = await self.context.new_page()
            
            # 设置较长的超时时间
            self.page.set_default_timeout(60000)  # 60秒
            self.page.set_default_navigation_timeout(60000)  # 60秒

            if await self.url_test(self.base_url):
                init.logger.info("浏览器初始化成功")
            else:
                init.logger.error("浏览器初始化失败，无法访问目标网站")
                await self.close()
                return
        except Exception as e:
            init.logger.error(f"初始化浏览器时发生错误: {str(e)}")
            error_msg = escape_markdown(f"⚠️ 初始化浏览器失败: {str(e)}", version=2)
            add_task_to_queue(
                init.bot_config['allowed_user'], 
                f"{init.IMAGE_PATH}/male023.png", 
                error_msg
            )
            await self.close()
 
        
    async def url_test(self, url):
        """测试URL是否可访问"""
        if not self.page:
            init.logger.error("浏览器未初始化，无法测试URL")
            return False
        try:
            # 确保URL包含协议
            test_url = f"https://{url}" if not url.startswith(('http://', 'https://')) else url
            
            init.logger.info(f"测试访问网站: {test_url}")
            response = await self.page.goto(test_url, wait_until="domcontentloaded")
            
            if response and response.status == 200:
                init.logger.info("目标网站访问正常!")
                return True
            else:
                status_code = response.status if response else "未知"
                error_msg = f"访问 {test_url} 失败，返回状态码: {status_code}"
                init.logger.warn(error_msg)
                add_task_to_queue(
                    init.bot_config['allowed_user'], 
                    f"{init.IMAGE_PATH}/male023.png", 
                    f"⚠️ 初始化浏览器失败，无法访问 {test_url}，请检查网络连接或网站状态！"
                )
                # 清理已创建的资源
                await self.close()
                return False
                
        except PlaywrightTimeoutError as e:
            error_msg = f"访问 {test_url if 'test_url' in locals() else url} 连接超时"
            init.logger.warn(error_msg)
            add_task_to_queue(
                init.bot_config['allowed_user'], 
                f"{init.IMAGE_PATH}/male023.png", 
                f"⚠️ 初始化浏览器失败，无法访问目标网站，连接超时！"
            )
            await self.close()
            return False
        
    def get_global_page(self):
        """获取全局浏览器页面实例"""
        if not self.page:
            init.logger.error("浏览器未初始化，无法获取页面实例")
            return None
        return self.page
    
    async def wait_for_page_loaded(self, expected_elements=None, timeout=60000):
        """等待页面完全加载，包括动态内容"""
        try:
            # 基本等待
            await self.page.wait_for_load_state("networkidle", timeout=timeout)
            await asyncio.sleep(2)
            
            # 如果指定了期待的元素，等待它们出现
            if expected_elements:
                for element in expected_elements:
                    try:
                        await self.page.wait_for_selector(element, timeout=30000)
                    except:
                        pass  # 某些元素可能不存在，继续
            
            # 额外等待确保内容完全加载
            await asyncio.sleep(3)
            return True
        except Exception as e:
            init.logger.warn(f"  等待页面加载时出错: {str(e)}")
            return False

    async def close(self):
        try:
            if self.page:
                await self.page.close()
                self.page = None
            if self.context:
                await self.context.close()
                self.context = None
            if self.browser:
                await self.browser.close()
                self.browser = None
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            init.logger.info("浏览器已关闭")
        except Exception as e:
            init.logger.warn(f"关闭浏览器时出错: {str(e)}")