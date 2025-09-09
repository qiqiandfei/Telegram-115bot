<div align="center">
    <h1>115Bot - Telegram 机器人</h1>
    <p>简体中文 | <a href="./README_EN.md">[English]</a> </p>
</div>

一个基于 Python 的 Telegram 机器人，用于管理和控制 115 网盘，支持离线下载、视频上传、目录同步等功能。

## Tg讨论群

使用问题 & Bug反馈

[加入](https://t.me/+FTPNla_7SCc3ZWVl)

## 更新日志
v3.2.0
- 增加涩花爬虫功能，每天凌晨爬取指定版块的前一天数据并离线到115，可在配置文件中按需开启或关闭
- 优化“/dl”，“/av”命令交互体验，升级为异步模式，提交离线下载时不再阻塞，最大下载队列均为5
- 优化“/dl”命令交互流程，下载失败，添加到重试列表时需要制定TMDB名称，重试成功时将不再询问
- 添加“/reload”重载配置功能
- 配置文件检查，如果配置文件不存在，自动生成配置模板
- 添加日志文件，默认保存在"/config/115bot.log"，重启容器会覆盖日志
- 代码优化，bug修复

v3.1.0
- 删除AV订阅功能，添加AV日更功能，每日定时更新最新资源并离线到115，可在配置文件中开启或关闭。针对离线失败的任务，每6个小时自动重试，直到成功为止。
- 添加通过输入番号直接离线功能，例如：输入 'av ipz-266'自动离线到115，省去搜索磁力的步骤
- 当离线下载超时时，可以选择添加到重试列表，添加到重试列表后机器人会定期自动尝试离线，当你不需要它的时候也可以随时清空。
- 添加机器人菜单，方便查阅命令
- 代码优化，bug修复

v3.0.0
- 重构底层接口，所有115请求全部对接开放平台，更快速更稳定！
- 优化视频文件上传，支持大视频上传
- 暂时关闭AV订阅功能，找到稳定可靠的接口后再更新

v2.3.7
- 修复手动下载订阅电影后，订阅没有自动取消的bug

v2.3.6
- 修复订阅电影有可能下载失败的错误
- 由于触发JAVDB的反爬机制，导致爬取失败，暂时关闭AV订阅功能，后续会更新稳定的方案

v2.3.5
- 修复离线下载超时告警消息MarkdownV2格式转义错误的问题
- 优化电影订阅下载逻辑

v2.3.4
- bug修复

v2.3.3
- bug修复

v2.3.2
- bug修复

v2.3.1
- 女优订阅离线失败时，自动更换磁力

v2.3.0
- 增加电影订阅功能
- 修复了部分bug

v2.2.0
- 修复了部分bug

## 项目背景
本项目源于个人日常观影体验的优化需求。作为一个影视爱好者，我采用 115网盘 + CloudDrive2 + Emby 的组合方案来管理和观看媒体内容。

想象这样一个场景：

在通勤路上刷到一部令人心动的电影，只需将找到的磁力链接随手发给 TG 机器人，它就会：
- 自动将影片离线下载到 115 网盘的指定分类目录
- 智能清理各类广告文件
- 自动创建 STRM 文件并通知 Emby 进行媒体库刮削

当你结束一天的工作回到家，只需准备好零食饮品，打开 Emby 就能享受精心整理好的观影体验。让一部好电影为你洗去一天的疲惫，享受属于自己的放松时光。

## 已知缺陷
- 目前对剧集的支持度非常有限，如果直接离线剧集资源可能会发生意想不到的问题
- 同步目录会清空整个文件夹，包括元数据，相当粗暴

如果你乐意帮助改进这个项目欢迎[加入](https://t.me/qiqiandfei)！

## 功能特性

- 🔑 **115 账号管理**
  - 基于 115 开放平台
  - 使用官方接口，确保稳定可靠

- ⬇️ **离线下载**
  - 支持多种下载协议：磁力链接、迅雷、ed2k、FTP、HTTPS
  - 智能自动分类存储
  - 广告文件自动清理
  - STRM 文件自动创建

- 🎬 **番号下载**
  - 输入番号即可自动离线下载
  - 智能广告文件清理

- 🎭 **电影订阅**
  - 支持电影资源自动订阅
  - 有新资源自动离线下载
  - 智能广告文件清理
  - STRM 文件自动创建

- 🔄 **目录同步**
  - 自动创建本地软链接
  - STRM 文件批量生成
  - 无缝集成 Emby 媒体库

- 📱 **视频处理**
  - 支持视频文件自动上传至 115 网盘（注意：会消耗机场/VPS流量，请谨慎使用）

## 快速开始

### 环境要求

- Docker 环境
- Python 3.12+
- 稳定的 Telegram 网络连接

### 安装部署

1. **克隆项目**
   ```bash
   git clone https://github.com/qiqiandfei/Telegram-115bot.git
   cd 115bot
   ```

2. **配置文件设置**
   - 复制配置文件模板
     ```bash
     cp config/config.yaml.example config/config.yaml
     ```
   - 编辑 `config.yaml`，填入必要配置：
     - Telegram Bot Token
     - Telegram授权使用用户
     - 115 相关配置
     - 目录映射设置

3. **Docker 部署**
   
   **本地构建**
   ```bash
   # 构建基础镜像
   docker build -t 115bot:base -f Dockerfile.base .
   
   # 构建应用镜像
   docker build -t 115bot:latest .
   
   # 运行容器
   docker run -d \
     --name tg-bot-115 \
     --restart unless-stopped \
     -e TZ=Asia/Shanghai \
     -v /path/to/config:/config \
     -v /path/to/tmp:/tmp \
     -v /path/to/media:/media \
     -v /path/to/CloudNAS:/CloudNAS:rslave \
     115bot:latest
   ```
   
   **Docker Compose（推荐）**
   ```yaml
   version: '3.8'
   services:
    115-bot:
      container_name: tg-bot-115
      environment:
        TZ: Asia/Shanghai
      image: qiqiandfei/115-bot:latest
      # privileged: True
      restart: unless-stopped
      volumes:
        - /path/to/config:/config # 配置目录
        - /path/to/tmp:/tmp       # 临时目录
        - /path/to/media:/media   # Emby媒体库目录（软链目录）
        - /path/to/CloudNAS:/CloudNAS:rslave # CloudDrive2挂载目录
   ```

## 配置说明

请参考 `config/config.yaml.example` 文件中的详细注释进行配置。

### 目录结构
```
.
├── app
│   ├── 115bot.py                 # 程序入口脚本
│   ├── config.yaml.example       # 配置文件模板
│   ├── core                      # 核心功能
│   ├── handlers                  # Telegram handlers
│   ├── images                    # 图片
│   ├── init.py                   # 初始化脚本
│   └── utils                     # 有用的工具
├── build.sh                      # 本地构建脚本
├── config                        # 配置目录
├── create_tg_session_file.py     # 创建tg_session脚本
├── docker-compose.yaml           # docker-compose
├── Dockerfile                    
├── Dockerfile.base
├── legacy                        # 历史遗留
├── LICENSE
├── README_EN.md
├── README.md
├── requirements.txt              # 项目依赖
```

## 使用指南

### 基本命令

- `/start`   - 显示帮助信息
- `/auth`    - 115 授权设置
- `reload`   - 重载配置
- `/dl`      - 添加离线下载
- `/rl`      - 重试列表
- `/av`      - 番号下载
- `/sm`      - 订阅电影
- `/sync`    - 同步目录并创建软链
- `/q`       - 取消当前会话

### 115 开放平台申请

**强烈建议申请 115 开放平台以获得更好的使用体验！**
- 申请地址：[115开放平台](https://open.115.com/)
- 审核通过后将 `115_app_id` 填入配置文件中

如不想使用 115 开放平台，请使用之前的镜像版本 `qiqiandfei/115-bot:v2.3.7`

### 视频下载配置

由于 Telegram Bot API 限制，无法下载超过 20MB 的视频文件。如需下载大视频，请配置 Telegram 客户端：

#### 配置方法
Telegram API申请地址：[Telegram Development Platform](https://my.telegram.org/auth)

申请成功后可以获取到tg_api_id和tg_api_hash

确保配置文件中以下三个参数配置正确：
```
# bot_name
bot_name: "@yourbotname"

# telegram 的api信息
tg_api_id: 1122334
tg_api_hash: 1yh3j4k9dsk0fj3jdufnwrhf62j1k33f
```
**生成 user_session的方法**
1. 修改create_tg_session_file.py中的 API_ID 和 API_HASH
2. 运行脚本：python create_tg_session_file.py
3. 按照提示输入手机号和验证码
4. 将生成的 user_session.session 文件放到 config 目录

> **注意**：如果不配置此步骤，机器人仍可正常运行，只是无法处理超过 20MB 的视频文件。

### 重要提醒

⚠️ **同步功能警告**：`/sync` 命令会**删除目标目录下的所有文件**，包括元数据。大规模同步操作可能触发 115 网盘风控机制，请谨慎使用！

## 许可证
```
MIT License

Copyright (c) 2025 qiqiandfei

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 免责声明
本项目仅供学习和研究使用，请遵守相关法律法规，不得用于商业用途。使用者需自行承担使用风险！

如果这个项目对您有帮助，请献上一个⭐！

## Buy me a coffee~
![请我喝咖啡](https://alist.qiqiandfei.fun:8843/d/Syncthing/yufei/%E4%B8%AA%E4%BA%BA/%E8%B5%9E%E8%B5%8F.png)