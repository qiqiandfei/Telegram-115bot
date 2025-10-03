import time
from playwright.sync_api import sync_playwright
from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError
import init
from app.utils.message_queue import add_task_to_queue

class HeadlessBrowser:
    def __init__(self, _base_url):
        self.playwright = None
        self.browser = None
        self.page = None
        self.context = None
        self.base_url = _base_url
        self.init_browser()

    def init_browser(self):
        """初始化全局浏览器实例"""
        init.logger.info("正在初始化浏览器...")
        
        try:
            self.playwright = sync_playwright().start()
            # 启动浏览器（无头模式）- 添加更多配置选项
            self.browser = self.playwright.chromium.launch(
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
            
            self.context = self.browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent=init.USER_AGENT
            )

            self.page = self.context.new_page()
            
            # 设置较长的超时时间
            self.page.set_default_timeout(60000)  # 60秒
            self.page.set_default_navigation_timeout(60000)  # 60秒

            if self.url_test(self.base_url):
                init.logger.info("浏览器初始化成功")
            else:
                init.logger.error("浏览器初始化失败，无法访问目标网站")
                self.close()
                return
        except Exception as e:
            init.logger.error(f"初始化浏览器时发生错误: {str(e)}")
            add_task_to_queue(
                init.get_primary_user(),
                f"{init.IMAGE_PATH}/male023.png",
                f"⚠️ 初始化浏览器失败: {str(e)}"
            )
            self.close()
 
        
    def url_test(self, url):
        """测试URL是否可访问"""
        if not self.page:
            init.logger.error("浏览器未初始化，无法测试URL")
            return False
        try:
            # 确保URL包含协议
            test_url = f"https://{url}" if not url.startswith(('http://', 'https://')) else url
            
            init.logger.info(f"测试访问网站: {test_url}")
            response = self.page.goto(test_url, wait_until="domcontentloaded")
            
            if response and response.status == 200:
                init.logger.info("目标网站访问正常!")
                return True
            else:
                status_code = response.status if response else "未知"
                error_msg = f"访问 {test_url} 失败，返回状态码: {status_code}"
                init.logger.warn(error_msg)
                add_task_to_queue(
                    init.get_primary_user(),
                    f"{init.IMAGE_PATH}/male023.png",
                    f"⚠️ 初始化浏览器失败，无法访问 {test_url}，请检查网络连接或网站状态！"
                )
                # 清理已创建的资源
                self.close()
                return False
                
        except PlaywrightTimeoutError as e:
            error_msg = f"访问 {test_url if 'test_url' in locals() else url} 连接超时"
            init.logger.warn(error_msg)
            add_task_to_queue(
                init.get_primary_user(),
                f"{init.IMAGE_PATH}/male023.png",
                f"⚠️ 初始化浏览器失败，无法访问目标网站，连接超时！"
            )
            self.close()
            return False
        
    def get_global_page(self):
        """获取全局浏览器页面实例"""
        if not self.page:
            init.logger.error("浏览器未初始化，无法获取页面实例")
            return None
        return self.page
    
    def wait_for_page_loaded(self, expected_elements=None, timeout=30000):
        """等待页面完全加载，包括动态内容"""
        try:
            # 基本等待
            self.page.wait_for_load_state("networkidle", timeout=timeout)
            time.sleep(2)
            
            # 如果指定了期待的元素，等待它们出现
            if expected_elements:
                for element in expected_elements:
                    try:
                        self.page.wait_for_selector(element, timeout=10000)
                    except:
                        pass  # 某些元素可能不存在，继续
            
            # 额外等待确保内容完全加载
            time.sleep(3)
            return True
        except Exception as e:
            init.logger.warn(f"  等待页面加载时出错: {str(e)}")
            return False

    def close(self):
        try:
            if self.page:
                self.page.close()
                self.page = None
            if self.context:
                self.context.close()
                self.context = None
            if self.browser:
                self.browser.close()
                self.browser = None
            if self.playwright:
                self.playwright.stop()
                self.playwright = None
            init.logger.info("浏览器已关闭")
        except Exception as e:
            init.logger.warn(f"关闭浏览器时出错: {str(e)}")