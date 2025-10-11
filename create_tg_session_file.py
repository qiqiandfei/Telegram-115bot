#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import asyncio
import warnings

# 过滤 Telethon 的异步会话实验性功能警告
warnings.filterwarnings("ignore", message="Using async sessions support is an experimental feature")

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

"""
独立的Telegram Session文件创建脚本
使用方法：
1. 修改下面的 API_ID 和 API_HASH
2. 运行脚本：python create_tg_session_file.py
3. 按照提示输入手机号和验证码
4. 将生成的 user_session.session 文件放到 config 目录
"""

# 请在这里填入你的API配置
# 获取地址：https://my.telegram.org/auth
API_ID = 'your_api_id'  # 替换为你的API ID
API_HASH = 'your_api_hash'  # 替换为你的API Hash

async def create_telegram_session():
    client = TelegramClient('user_session', API_ID, API_HASH)
    
    print("正在连接Telegram...")
    await client.connect()
    
    # 检查是否已经认证
    if not await client.is_user_authorized():
        print("未检测到有效session，开始认证流程...")
        
        # 获取手机号
        phone = input("请输入您的手机号（国际格式，如:+8613812345678）: ")
        
        # 发送验证码请求
        await client.send_code_request(phone)
        print("验证码已发送到您的Telegram账号")
        
        # 获取验证码
        code = input("请输入收到的验证码: ")
        
        try:
            # 登录
            await client.sign_in(phone=phone, code=code)
            print("登录成功！")
            
        except SessionPasswordNeededError:
            # 如果需要两步验证密码
            password = input("请输入两步验证密码: ")
            await client.sign_in(password=password)
            print("两步验证通过！登录成功！")
            
    else:
        print("使用现有session登录成功！")
    
    # 验证登录状态
    me = await client.get_me()
    print(f"当前登录账号: {me.first_name} (@{me.username})")
    
    # 断开连接（session文件已保存）
    await client.disconnect()
    print(f"Session文件已保存至: {os.path.abspath('user_session.session')}")

async def test_session():
    """测试session文件是否有效"""
    if os.path.exists('user_session.session'):
        client = TelegramClient('user_session', API_ID, API_HASH)
        await client.start()
        me = await client.get_me()
        print(f"Session测试成功！当前用户: {me.first_name}")
        await client.disconnect()
    else:
        print("未找到session文件")

if __name__ == '__main__':
    # 检查session文件是否存在
    if os.path.exists('user_session.session'):
        choice = input("检测到已存在session文件，是否重新创建？(y/n): ")
        if choice.lower() == 'y':
            # 删除旧session文件
            os.remove('user_session.session')
            print("旧session文件已删除，开始创建新session...")
            asyncio.run(create_telegram_session())
        else:
            # 测试现有session
            asyncio.run(test_session())
    else:
        # 创建新session
        asyncio.run(create_telegram_session())