FROM python:3.12-slim
LABEL authors="qiqiandfei"

# 安装系统依赖和Playwright所需的库
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    # Playwright Chromium依赖（最小化安装）
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libxss1 \
    libasound2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    # 字体支持（可选，用于渲染中文等）
    fonts-liberation \
    # 清理缓存
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 设置Playwright环境变量
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0

# 复制requirements.txt并安装Python依赖
COPY requirements.txt /app/
RUN pip install --upgrade pip --no-cache-dir && \
    pip install -r requirements.txt --no-cache-dir

# 安装Playwright浏览器（只安装Chromium，并清理缓存）
RUN playwright install chromium --with-deps && \
    # 清理Playwright缓存
    find /ms-playwright -name "*.log" -delete && \
    find /ms-playwright -name "*.tmp" -delete

# 复制app下所有文件到/app
ADD ./app .

# 设置Python模块搜索路径，包含所有需要的目录
ENV PYTHONPATH="/app:/app/utils:/app/core:/app/handlers:/app/.."

CMD ["python", "115bot.py"]

