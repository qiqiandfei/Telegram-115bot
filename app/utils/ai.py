# -*- coding: utf-8 -*-
import requests
import sys
import os
import json
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)
sys.path.append(current_dir)
import init

def check_ai_api_available():
    url = init.bot_config.get("ai", {}).get("api_url", "")
    if not url:
        init.logger.warn("AI API URL 未定义.")
        return False
    model = init.bot_config.get("ai", {}).get("model", "")
    if not model:
        init.logger.warn("AI 模型未定义.")
        return False
    
    api_key = init.bot_config.get("ai", {}).get("api_key", "")
    if not api_key:
        init.logger.warn("AI API Key 未定义.")
        return False
    return True

def chat_completion(tip_words, max_tokens=8192, temperature=0):
    url = init.bot_config.get("ai").get("api_url")
    # 智能判断是否需要拼接 /chat/completions
    # 如果URL中不包含 chat/completions 也不包含 messages (适配Anthropic风格)，且不以 / 结尾，则尝试拼接
    if "chat/completions" not in url and "messages" not in url:
        if url.endswith("/"):
            url = url[:-1] + "/chat/completions"
        else:
            url = url + "/chat/completions"
            
    payload = {
        "model": init.bot_config.get("ai").get("model"),
        "messages": [{"role": "user", "content": tip_words}],
        "max_tokens": max_tokens,
        # 低温度减少输出随机性，降低模型自由发挥/编造的概率
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {init.bot_config.get('ai').get('api_key')}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            init.logger.warn(f"AI API请求失败: {response.text}")
            return None
            
        result = response.json()
        return result
        
    except Exception as e:
        init.logger.error(f"调用AI接口出错: {e}")
        return None

def get_movie_tmdb_name_with_ai(movie_desc):
    
    if not check_ai_api_available():
        return None
    
    tip_words = f"""你是一个专业的影视资料整理助手。用户会提供一个电影资源的原始文件名（可能包含分辨率、编码格式、来源、语言标记、发布页、发布组、扩展名等与片名无关的信息，也可能存在拼写错误或缩写），请你完成以下任务：

                1. 自行判断并忽略文件名中与片名无关的技术性信息（如分辨率、1080p/2160p、编码x264/x265/HEVC、来源WEBDL/BluRay/WEB-DL、语言标记iTA/ENG等、发布组名、文件扩展名等），提取出片名主体和可能的年份信息。
                2. 基于你已掌握的知识判断这是哪一部电影，给出该电影在TMDB(The Movie Database)上的官方中文（简体）译名；如果没有大陆官方译名，再使用最通用的中文译名。
                3. 若电影属于系列/续集，完整名称需包含系列名和序号信息，例如“侏罗纪公园2”对应完整中文名称应该是“侏罗纪公园2：失落的世界”。
                4. 重要：如果你不确定这到底是哪部电影，或无法确定官方中文译名，请直接返回空字符串，绝对不要编造或猜测一个看似合理的名字。

                请只输出JSON，不要输出任何解释性文字或markdown代码块标记，格式为：{{"name": "完整的中文电影名称"}}

                示例：
                输入: "The.Matrix.1999.1080p.BluRay.x264-GROUP.mkv"
                输出: {{"name": "黑客帝国"}}
                输入: "Jurassic.Park.2.1997.720p.WEB-DL.x265-XYZ.mp4"
                输出: {{"name": "侏罗纪公园2：失落的世界"}}

                输入: "randomfile_abc123.mkv"
                输出: {{"name": ""}}

                现在请处理："{movie_desc}"  
            """
    try:
        result = chat_completion(tip_words, temperature=0)
        init.logger.info(f"AI原始响应: {result}")
        
        # 解析返回结果
        # 针对Anthropic/SiliconFlow messages接口: {'content': [{'text': '{"name": "..."}'...} ...}
        if isinstance(result, dict) and 'content' in result and isinstance(result['content'], list) and len(result['content']) > 0:
            text_content = result['content'][0].get('text', '')
            # 清理可能存在的markdown标记
            if "```" in text_content:
                text_content = text_content.replace("```json", "").replace("```", "").strip()
            
            try:
                json_data = json.loads(text_content)
                return json_data.get('name')
            except json.JSONDecodeError:
                init.logger.warn(f"AI返回的不是有效的JSON格式: {text_content}")
                return None

        # 兼容OpenAI格式: choices[0].message.content
        if isinstance(result, dict) and 'choices' in result and len(result['choices']) > 0:
            content = result['choices'][0]['message']['content']
            if "```" in content:
                content = content.replace("```json", "").replace("```", "").strip()
            try:
                json_data = json.loads(content)
                return json_data.get('name')
            except json.JSONDecodeError:
                return None
                
        return None
        
    except Exception as e:
        init.logger.error(f"调用AI接口出错: {e}")
        return None


if __name__ == "__main__":
    init.init_log()
    init.load_yaml_config()
    test_desc = "Die My Love iTA-ENG.WEBDL.1080p.x264-Dr4gon.mkv"
    movie_name = get_movie_tmdb_name_with_ai(test_desc)
    print(f"识别到的电影名称: {movie_name}")