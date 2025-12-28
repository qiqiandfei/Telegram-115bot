FROM python:3.12-slim
LABEL authors="qiqiandfei"

# Install system dependencies and Google Chrome
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    wget \
    gnupg \
    unzip \
    curl \
    xvfb \
    libxi6 \
    # Fonts for Chinese support
    fonts-liberation \
    fonts-noto-cjk \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip --no-cache-dir && \
    pip install -r requirements.txt --no-cache-dir && \
    seleniumbase install chromedriver

# Copy app files
ADD ./app .

# Set PYTHONPATH
ENV PYTHONPATH="/app:/app/utils:/app/core:/app/handlers:/app/.."

# Start command
CMD ["python", "115bot.py"]

