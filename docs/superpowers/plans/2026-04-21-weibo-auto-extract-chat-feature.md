# 微博爬虫自动内容提取 + 豆包API聊天功能 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为现有微博爬虫添加爬取完成后自动提取纯文本内容功能，同时实现独立的交互式聊天脚本，支持基于爬取的微博内容通过豆包API进行多轮对话。

**Architecture:** 
1. 自动提取功能直接集成到现有爬虫脚本中，爬取完成后调用已有的extract_content函数生成纯文本文件，无需额外配置。
2. 聊天脚本作为独立工具实现，自动检测/提取微博内容，适配火山引擎豆包API格式，支持上下文关联的多轮对话。
3. 所有配置通过环境变量传递，避免硬编码敏感信息。

**Tech Stack:** Python 3.8+, requests, 火山引擎豆包API, 现有playwright爬虫框架

---

## 文件结构
| 操作 | 文件路径 | 功能说明 |
|------|----------|----------|
| 修改 | `crawl_final_pro.py` | 集成自动内容提取逻辑 |
| 修改 | `extract_content.py` | 保持现有功能，支持被其他模块导入 |
| 新建 | `chat_weibo.py` | 交互式聊天脚本，适配豆包API |
| 修改 | `requirements.txt` | 添加requests依赖 |

---

### Task 1: 集成自动内容提取功能到爬虫

**Files:**
- Modify: `crawl_final_pro.py`
- Modify: `extract_content.py` (no code changes, ensure importable)

- [ ] **Step 1: 添加extract_content模块导入**
在crawl_final_pro.py头部导入语句中添加：
```python
from extract_content import extract_content
```

- [ ] **Step 2: 调整weibos_all.json保存代码，添加路径变量**
找到保存全量文件的代码，修改为：
```python
# 保存最终全量文件
logger.info("💾 正在保存最终全量汇总文件...")
weibos_all_path = OUTPUT_DIR / "weibos_all.json"
with open(weibos_all_path, "w", encoding="utf-8") as f:
    json.dump(all_weibos, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 3: 添加爬取完成后的自动提取逻辑**
在保存完weibos_all.json之后，添加自动提取代码：
```python
# 自动提取纯文本内容
logger.info("📝 正在自动提取微博纯文本内容...")
try:
    content_output_path = OUTPUT_DIR / "weibos_content.txt"
    extract_success = extract_content(str(weibos_all_path), str(content_output_path))
    if extract_success:
        logger.info("✅ 纯文本内容提取完成，已保存到 weibos_content.txt")
    else:
        logger.warning("⚠️  纯文本内容提取失败，可手动运行 extract_content.py 提取")
except Exception as e:
    logger.warning(f"⚠️  自动提取内容时出错: {str(e)}，可手动运行 extract_content.py 提取")
```

- [ ] **Step 4: 验证代码可以正常运行**
Run: `python crawl_final_pro.py --help`
Expected: 正常显示帮助信息，无导入错误

- [ ] **Step 5: 提交修改**
```bash
git add crawl_final_pro.py
git commit -m "feat: add auto content extraction after crawl completes"
```

---

### Task 2: 实现豆包API交互式聊天脚本

**Files:**
- Create: `chat_weibo.py`
- Modify: `requirements.txt`

- [ ] **Step 1: 添加requests依赖到requirements.txt**
在文件末尾添加：
```txt
requests>=2.31.0
```

- [ ] **Step 2: 编写完整的聊天脚本代码**
创建chat_weibo.py，内容如下：
```python
#!/usr/bin/env python3
"""
微博内容交互式聊天脚本
基于豆包API，支持基于爬取的微博内容进行多轮对话
"""
import os
import json
import argparse
import requests
from pathlib import Path
from extract_content import extract_content

# 默认配置
DEFAULT_API_BASE = "https://ark.cn-beijing.volces.com/api/v3/responses"
DEFAULT_MODEL = "doubao-seed-2-0-mini-260215"
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

def call_ark_api(api_key, messages, model=DEFAULT_MODEL, temperature=DEFAULT_TEMPERATURE):
    """调用豆包API"""
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
        "parameters": {
            "temperature": temperature
        }
    }

    try:
        response = requests.post(
            DEFAULT_API_BASE,
            headers=headers,
            json=data,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()

        # 解析响应
        if result.get("status") == "success":
            return result["choices"][0]["message"]["content"][0]["text"]
        else:
            error_msg = result.get("error", {}).get("message", "未知错误")
            print(f"❌ API调用失败: {error_msg}")
            return None
    except Exception as e:
        print(f"❌ 请求API时出错: {str(e)}")
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
        print("   export ARK_API_KEY=\"ark-7fc4057e-e7eb-4d74-9b7a-fcfb1276c4b2-b92ef\"")
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
```

- [ ] **Step 3: 给脚本添加可执行权限**
Run: `chmod +x chat_weibo.py crawl_final_pro.py`
Expected: 无输出，权限添加成功

- [ ] **Step 4: 验证脚本可以正常运行**
Run: `python chat_weibo.py --help`
Expected: 正常显示帮助信息，无导入错误

- [ ] **Step 5: 提交修改**
```bash
git add requirements.txt chat_weibo.py
git commit -m "feat: add Doubao API interactive chat script for weibo content analysis"
```

---

### Task 3: 功能测试验证

**Files:**
- No changes, just testing

- [ ] **Step 1: 测试自动提取功能**
Run: 运行一次爬虫爬取少量内容，检查输出目录是否自动生成weibos_content.txt
Expected: 爬取完成后，输出目录下存在weibos_content.txt文件，内容为每条微博纯文本一行

- [ ] **Step 2: 测试聊天功能**
Run: 
```bash
export ARK_API_KEY="ark-7fc4057e-e7eb-4d74-9b7a-fcfb1276c4b2-b92ef"
python chat_weibo.py <your_crawl_dir>
```
Expected: 成功加载微博内容，可以正常提问并得到基于内容的回答
