#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试文件夹名提取功能"""

import sys
sys.path.insert(0, '/root/Telegram-115bot/app')

from enum import Enum
import re

class DownloadUrlType(Enum):
    ED2K = "ED2K"
    THUNDER = "thunder"
    MAGNET = "magnet"
    UNKNOWN = "unknown"

def is_valid_link(link: str) -> DownloadUrlType:
    patterns = {
        DownloadUrlType.MAGNET: r'^magnet:\?xt=urn:[a-z0-9]+:[a-zA-Z0-9]{32,40}',
        DownloadUrlType.ED2K: r'^ed2k://\|file\|.+\|[0-9]+\|[a-fA-F0-9]{32}\|',
        DownloadUrlType.THUNDER: r'^thunder://[a-zA-Z0-9=]+'
    }
    for url_type, pattern in patterns.items():
        if re.match(pattern, link):
            return url_type
    return DownloadUrlType.UNKNOWN

def sanitize_folder_name(text: str) -> str:
    if not text:
        return ""
    text = text.replace(":", "")
    invalid_chars = ['/', '\\', '?', '*', '"', '<', '>', '|']
    for char in invalid_chars:
        text = text.replace(char, "-")
    return text.strip()

def extract_folder_name_from_text(message_text: str) -> str:
    lines = message_text.strip().split('\n')
    non_link_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        contains_link = False
        for fragment in line.split():
            if is_valid_link(fragment.strip()) != DownloadUrlType.UNKNOWN:
                contains_link = True
                break
        if not contains_link:
            non_link_lines.append(line)
        else:
            text_parts = []
            for fragment in line.split():
                fragment = fragment.strip()
                if fragment and is_valid_link(fragment) == DownloadUrlType.UNKNOWN:
                    text_parts.append(fragment)
            if text_parts:
                non_link_lines.append(' '.join(text_parts))
    if not non_link_lines:
        return ""
    if len(non_link_lines) == 1:
        folder_name = non_link_lines[0]
    else:
        folder_name = non_link_lines[0] + non_link_lines[-1]
    return sanitize_folder_name(folder_name)

# 测试用例
test_text = """miru(坂道みる/坂道美琉)原档合集:
ed2k://|file|www.98T.la@SONE-882.mp4|6458233593|97469A8B0C902283D99E6026E28843A3|/
ed2k://|file|www.98T.la@SONE-830.mp4|6467401273|5294F6CB34EA43DA9016A1FCD21B0DD0|/
20251007
"""

print("=" * 60)
print("测试文本:")
print(test_text)
print("=" * 60)

result = extract_folder_name_from_text(test_text)
expected = "miru(坂道みる-坂道美琉)原档合集20251007"

print(f"提取的文件夹名: [{result}]")
print(f"预期结果: [{expected}]")
print(f"测试通过: {result == expected}")
print("=" * 60)
