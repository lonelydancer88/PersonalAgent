#!/usr/bin/env python3
"""
提取微博JSON文件中的content内容，每个微博输出一行，自动处理换行符
"""
import json
import argparse
from pathlib import Path

def extract_content(input_path, output_path=None):
    # 处理输出路径，默认和输入同目录下的weibos_content.txt
    if not output_path:
        input_path = Path(input_path)
        output_path = input_path.parent / "weibos_content.txt"

    print(f"🔍 正在读取文件: {input_path}")
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            weibos = json.load(f)
    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        return False

    print(f"📊 共读取到 {len(weibos)} 条微博")

    print(f"💾 正在提取内容写入: {output_path}")
    count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for weibo in weibos:
            content = weibo.get("content", "").strip()
            if not content:
                continue
            # 替换内容中的换行符和回车符，避免一行变多行
            content = content.replace("\n", " ").replace("\r", " ")
            # 连续多个空格替换成一个
            while "  " in content:
                content = content.replace("  ", " ")
            f.write(content + "\n")
            count += 1

    print(f"✅ 提取完成！共写入 {count} 条有效微博内容")
    print(f"📂 输出文件: {output_path}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='提取微博JSON中的content内容，每行一条')
    parser.add_argument('--input', type=str, default="/Users/hpl/vibecoding/memory/data/weibos_2014433131_20260420_103652/weibos_all.json", help='输入的weibos_all.json路径')
    parser.add_argument('--output', type=str, default="", help='输出的txt文件路径（可选）')
    args = parser.parse_args()

    extract_content(args.input, args.output)
