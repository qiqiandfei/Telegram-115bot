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

def get_movie_tmdb_name_with_ai(movie_desc):
    if not check_ai_api_available():
        return None
    url = init.bot_config.get("ai").get("api_url")
    payload = {
        "model": init.bot_config.get("ai").get("model"),
        "messages": [
            {
                "role": "user",
                "content": f"'{movie_desc}' 请根据这个描述帮我从TMDB找出这个电影的中文名称，返回格式：{{'name': '电影中文名称'}}，只返回json内容，注意不要有多余的文字。如果找不到，请返回{{'name': ''}}"
            }
        ],
        "max_tokens": 8192
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
        init.logger.info(f"AI原始响应: {result}")
        
        # 解析返回结果
        # 针对用户提供的结构: {'content': [{'text': '{"name": "..."}'...} ...}
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
        elif isinstance(result, dict) and 'choices' in result and len(result['choices']) > 0:
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
    test_desc = "梦幻天堂·龙网(www.321n.net).惊天魔盗团3.非常盗3.出神入化3"
    movie_name = get_movie_tmdb_name_with_ai(test_desc)
    print(f"识别到的电影名称: {movie_name}")