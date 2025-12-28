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

def chat_completion(tip_words, max_tokens=8192):
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
        "max_tokens": max_tokens
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
    
    tip_words = f"'{movie_desc}' 请根据这个字符串，推断出可能的电影名称，然后根据电影名称，去TMDB网站(https://www.themoviedb.org)找到电影的TMDB ID，最后根据TMDB ID找到其对应的完整中文名称。注意：1. 优先匹配年份和英文原名。2. 如果有多个中文译名，请优先选择TMDB上的官方中文译名或最通用的译名。3. 有些系列电影可能会包含序号，比如：“侏罗纪公园2” 对应完整的中文名称应该是“侏罗纪公园2：失落的世界”。请返回json格式{{\"name\": \"完整的中文电影名称\"}} 。不要包含任何多余文字，如果找不到对应的中文名称请返回 {{\"name\": \"\"}}"
    try:
        result = chat_completion(tip_words)
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
    test_desc = "Die My Love (2025) iTA-ENG.WEBDL.1080p.x264-Dr4gon.mkv"
    movie_name = get_movie_tmdb_name_with_ai(test_desc)
    print(f"识别到的电影名称: {movie_name}")