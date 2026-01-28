FROM python:3.12-slim
LABEL authors="qiqiandfei"

# 1. 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# 2. 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    wget \
    gnupg \
    unzip \
    # 核心运行库 (防止 Chrome 启动静默挂起)
    libasound2 \
    libgbm1 \
    libnss3 \
    # 字体支持
    fonts-liberation \
    fonts-noto-cjk \
    && \
    # 针对 amd64 安装 Chrome
    if [ "$(dpkg --print-architecture)" = "amd64" ]; then \
        wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg && \
        echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
        apt-get update && apt-get install -y google-chrome-stable; \
    else \
        # 非 amd64 环境安装 chromium
        apt-get update && apt-get install -y chromium chromium-driver; \
    fi \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 3. 安装 Python 依赖
COPY requirements.txt /app/
RUN pip install --upgrade pip --no-cache-dir && \
    pip install -r requirements.txt --no-cache-dir && \
    # 针对 amd64 安装 Chrome driver (arm64 使用 apt 安装的 chromium-driver)
    if [ "$(dpkg --print-architecture)" = "amd64" ]; then seleniumbase install chromedriver; fi

ADD ./app .

# 4. 设置路径
ENV PYTHONPATH="/app:/app/utils:/app/core:/app/handlers:/app/.."

# 5. 启动命令
CMD ["python", "115bot.py"]