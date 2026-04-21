#!/usr/bin/env python3
"""
微博内容交互式聊天脚本
基于豆包API，支持基于爬取的微博内容进行多轮对话
"""
import os
import json
import argparse
import requests
import time
from pathlib import Path
from extract_content import extract_content

# 默认配置
DEFAULT_API_BASE = "https://ark.cn-beijing.volces.com/api/v3/responses"
DEFAULT_MODEL = "doubao-seed-2-0-mini-260215"
DEFAULT_MODEL = "doubao-seed-2-0-lite-260215"
DEFAULT_TEMPERATURE = 0.7
MAX_CONTEXT_TOKENS = 120000  # 留出部分token给对话和响应

def count_tokens(text):
    """粗略估算token数，中文按1字符=0.5token，英文按1字符=0.25token"""
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 0.5 + other_chars * 0.25)

def load_weibo_content(crawl_dir):
    """加载微博内容，自动提取如果不存在"""
    crawl_dir = Path(crawl_dir)
    if not crawl_dir.exists():
        print(f"❌ 目录不存在: {crawl_dir}")
        return None

    content_path = crawl_dir / "weibos_content.txt"
    if not content_path.exists():
        print(f"⚠️  未找到已提取的内容文件，正在自动提取...")
        weibos_all_path = crawl_dir / "weibos_all.json"
        if not weibos_all_path.exists():
            print(f"❌ 未找到微博数据文件: {weibos_all_path}")
            return None
        success = extract_content(str(weibos_all_path), str(content_path))
        if not success:
            print(f"❌ 内容提取失败")
            return None

    print(f"📖 正在加载微博内容...")
    with open(content_path, "r", encoding="utf-8") as f:
        content_lines = [line.strip() for line in f if line.strip()]

    full_content = "\n".join(content_lines)
    token_count = count_tokens(full_content)
    print(f"✅ 共加载 {len(content_lines)} 条微博，估算 {token_count} tokens")

    if token_count > MAX_CONTEXT_TOKENS:
        print(f"⚠️  内容超过上下文窗口限制（{MAX_CONTEXT_TOKENS} tokens），将自动截断前半部分")
        # 简单截断，保留最新的微博（假设文件按时间倒序排列）
        while count_tokens(full_content) > MAX_CONTEXT_TOKENS:
            full_content = full_content[full_content.find("\n") + 1:]

    return full_content

def call_ark_api(api_key, messages, model=DEFAULT_MODEL, temperature=DEFAULT_TEMPERATURE, max_retries=2, retry_delay=3):
    """调用豆包API，支持失败重试"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构造请求格式
    input_messages = []
    for msg in messages:
        input_messages.append({
            "role": msg["role"],
            "content": [
                {
                    "type": "input_text",
                    "text": msg["content"]
                }
            ]
        })

    data = {
        "model": model,
        "input": input_messages,
        "temperature": temperature
    }

    for attempt in range(max_retries + 1):
        try:
            response = requests.post(
                DEFAULT_API_BASE,
                headers=headers,
                json=data,
                timeout=60
            )

            # 处理可重试的HTTP错误
            if response.status_code >= 500 or response.status_code == 429:
                if attempt < max_retries:
                    print(f"⚠️  请求失败 (状态码: {response.status_code})，正在进行第{attempt + 1}次重试...")
                    time.sleep(retry_delay)
                    continue
                else:
                    error_msg = f"API返回错误状态码: {response.status_code}"
                    print(f"❌ {error_msg}，已达到最大重试次数")
                    return None

            response.raise_for_status()
            result = response.json()

            # 解析响应
            if result.get("status") == "completed":
                # 查找type为message的输出项
                for output_item in result.get("output", []):
                    if output_item.get("type") == "message":
                        return output_item["content"][0]["text"]
                # 如果没找到，返回第一个输出的内容
                return result["output"][0]["content"][0]["text"]
            else:
                error_msg = result.get("error", {}).get("message", "未知错误")
                print(f"❌ API调用失败: {error_msg}")
                return None

        except requests.exceptions.RequestException as e:
            # 网络错误、超时等请求异常
            if attempt < max_retries:
                print(f"⚠️  请求异常: {str(e)}，正在进行第{attempt + 1}次重试...")
                time.sleep(retry_delay)
            else:
                print(f"❌ 请求失败: {str(e)}，已达到最大重试次数")
                return None

def main():
    parser = argparse.ArgumentParser(description='基于微博内容的交互式聊天工具')
    parser.add_argument('crawl_dir', type=str, help='爬取结果目录路径，例如 ./data/weibos_2704548745_20260421_162030')
    parser.add_argument('--model', type=str, default=DEFAULT_MODEL, help=f'模型名称，默认 {DEFAULT_MODEL}')
    parser.add_argument('--temperature', type=float, default=DEFAULT_TEMPERATURE, help=f'生成温度，默认 {DEFAULT_TEMPERATURE}')
    args = parser.parse_args()

    # 读取API密钥
    api_key = os.getenv("ARK_API_KEY")
    if not api_key:
        print("❌ 请先设置 ARK_API_KEY 环境变量：")
        print("   export ARK_API_KEY=\"your-ark-api-key-here\"")
        return

    # 加载微博内容
    weibo_content = load_weibo_content(args.crawl_dir)
    if not weibo_content:
        return

    # 初始化对话历史
    messages = [
        {
            "role": "system",
            "content": f"你是一个微博内容分析助手，以下是用户的所有微博内容，你需要基于这些内容回答用户的问题。如果问题超出了提供的微博内容范围，请坦诚告知你不知道。\n\n微博内容：\n{weibo_content}"
        }
    ]

    print("\n🎉 微博内容已加载完成，可以开始提问了！")
    print("💡 输入 exit/quit 或按 Ctrl+C 退出聊天\n")

    try:
        while True:
            user_input = input("👤 你: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "退出"]:
                print("👋 再见！")
                break

            # 添加用户消息到历史
            messages.append({
                "role": "user",
                "content": user_input
            })

            # 调用API
            print("🤖 豆包: 思考中...", end="\r")
            response = call_ark_api(
                api_key,
                messages,
                model=args.model,
                temperature=args.temperature
            )

            if response:
                print(f"🤖 豆包: {response}\n")
                # 添加助手响应到历史
                messages.append({
                    "role": "assistant",
                    "content": response
                })
            else:
                print("🤖 豆包: 抱歉，我暂时无法回答这个问题，请稍后再试。\n")
                # 移除失败的用户消息，避免历史累积错误
                messages.pop()

    except KeyboardInterrupt:
        print("\n👋 再见！")
        return

if __name__ == "__main__":
    main()
