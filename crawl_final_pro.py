#!/usr/bin/env python3
"""
专业版爬虫：支持断点续爬 + 后台运行 + 命令行参数 + 实时进度日志
功能列表：
✅ 无需登录，爬取公开微博
✅ 自动展开长微博全文
✅ 断点续爬：中断后可继续，不重复爬取
✅ 后台静默运行：浏览器无窗口
✅ 支持指定uid爬任意用户
✅ 自动按uid+时间生成独立目录，不覆盖历史
✅ 批量存储，每1000条一个文件
✅ 自动过滤转发内容
✅ 实时进度日志，同时输出到控制台和文件

运行方式：
1. 普通爬取默认用户，后台运行：
   python crawl_final_pro.py

2. 爬指定用户，后台运行：
   python crawl_final_pro.py --uid 123456

3. 前台运行（可见浏览器窗口，用于调试）：
   python crawl_final_pro.py --uid 123456 --headless 0

4. 断点续爬（中断后继续，指定上次运行的输出目录）：
   python crawl_final_pro.py --resume ./data/weibos_2704548745_20250416_162030
"""
import json
import time
import hashlib
import argparse
import logging
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

def get_content_hash(content):
    """内容哈希当备用ID"""
    return hashlib.md5(content.encode('utf-8')).hexdigest()[:16]

def save_batch(weibos: list, output_dir: Path, batch_num: int):
    """保存批次文件"""
    import logging
    logger = logging.getLogger(__name__)
    file_path = output_dir / f"weibos_batch_{batch_num:03d}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(weibos, f, ensure_ascii=False, indent=2)
    logger.info(f"💾 已保存第{batch_num}批，共{len(weibos)}条到 {file_path}")
    return batch_num + 1

def load_crawled_ids(crawled_file: Path):
    """加载已爬取ID"""
    if not crawled_file.exists():
        return set()
    with open(crawled_file, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_crawled_id(crawled_file: Path, weibo_id: str):
    """追加保存已爬取ID"""
    with open(crawled_file, "a", encoding="utf-8") as f:
        f.write(f"{weibo_id}\n")

def get_next_batch_num(output_dir: Path):
    """获取下一个批次号，恢复模式下接着之前的号存"""
    batch_files = list(output_dir.glob("weibos_batch_*.json"))
    if not batch_files:
        return 1
    max_num = 0
    for f in batch_files:
        try:
            num = int(f.stem.split("_")[-1])
            if num > max_num:
                max_num = num
        except:
            pass
    return max_num + 1

def load_existing_weibos(output_dir: Path):
    """加载已有微博，恢复模式下继续累加"""
    all_file = output_dir / "weibos_all.json"
    if not all_file.exists():
        return []
    with open(all_file, "r", encoding="utf-8") as f:
        return json.load(f)

def clean_username(username):
    """清理用户名中的非法文件名字符，用于目录命名"""
    if not username:
        return "未知用户"
    # 替换系统不允许的文件名字符
    invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*', '\n', '\r', '\t']
    for c in invalid_chars:
        username = username.replace(c, '_')
    # 替换连续多个下划线为一个
    import re
    username = re.sub(r'_+', '_', username)
    # 截取前20个字符，避免目录名太长
    return username.strip('_')[:20] or "未知用户"

def handle_visitor_verification(page):
    """自动处理新浪游客验证，等待验证通过拿到有效Cookie，适配长等待时间"""
    try:
        # 先访问任意公开页面触发游客验证
        page.goto("https://m.weibo.cn/p/index", timeout=60000)
        page.wait_for_load_state("networkidle", timeout=20000)

        # 检测是否跳了游客系统
        if "visitor.passport.weibo.cn" in page.url:
            print("🤖 检测到新浪游客验证，正在自动处理（需要10-15秒）...")
            # 等待验证自动完成，跳回微博页面，最多等60秒
            page.wait_for_url("https://m.weibo.cn/**", timeout=60000)
            # 跳转后等待页面完全加载渲染
            page.wait_for_load_state("networkidle", timeout=20000)
            time.sleep(5)
            print("✅ 游客验证通过，获得访问权限")
        else:
            # 已经在微博页面，无需验证
            time.sleep(2)
        return True
    except Exception as e:
        print(f"⚠️ 游客验证处理失败: {str(e)}")
        return False

def get_username(uid):
    """访问用户主页获取用户名，自动过游客验证"""
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
                viewport={"width": 390, "height": 844},
                is_mobile=True
            )
            page = context.new_page()

            # 先处理游客验证
            if not handle_visitor_verification(page):
                browser.close()
                return ""

            # 验证通过后访问用户主页
            page.goto(f"https://m.weibo.cn/u/{uid}", timeout=60000)
            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(10)  # 给足够时间渲染用户信息，和测试版保持一致

            # 关闭弹窗
            try:
                page.click(".m-img-box-close", timeout=2000)
                time.sleep(1)
            except:
                pass

            # 优先用已知正确的选择器提取
            username = ""
            try:
                username = page.text_content(".mod-fil-name", timeout=5000).strip()
            except:
                # 备选选择器
                try:
                    username = page.text_content(".name.m-text-cut", timeout=3000).strip()
                except:
                    # 最后从标题提取
                    try:
                        title = page.title()
                        if "的微博" in title:
                            username = title.split("的微博")[0].strip()
                    except:
                        pass

            # 过滤无效值
            if not username or len(username) > 50 or "微博" in username:
                username = ""

            browser.close()
            return username
    except Exception as e:
        print(f"⚠️ 获取用户名失败，使用默认值: {str(e)}")
        return ""

def get_full_content(page, weibo_id):
    """获取全文内容"""
    import logging
    logger = logging.getLogger(__name__)
    detail_url = f"https://m.weibo.cn/status/{weibo_id}"
    detail_page = page.context.new_page()
    try:
        detail_page.goto(detail_url, timeout=20000)
        time.sleep(1.5)
        content_elem = detail_page.query_selector(".weibo-text")
        content = content_elem.text_content().strip() if content_elem else ""
        time_elem = detail_page.query_selector(".time")
        time_str = time_elem.text_content().strip() if time_elem else ""
        return content, time_str
    except Exception as e:
        logger.error(f"⚠️  微博ID {weibo_id} 详情页获取失败: {str(e)}")
        return "", ""
    finally:
        detail_page.close()

def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='微博专业版爬虫')
    parser.add_argument('--uid', type=str, default="2704548745", help='要爬取的微博用户ID')
    parser.add_argument('--resume', type=str, default="", help='断点续爬：指定上次运行的输出目录路径')
    parser.add_argument('--headless', type=int, default=1, help='是否后台运行：1=后台无头，0=前台可见')
    parser.add_argument('--batch_size', type=int, default=1000, help='每批存储条数，默认1000')
    parser.add_argument('--max_empty_scroll', type=int, default=5, help='连续多少次无新增自动停止，默认5')
    parser.add_argument('--log_interval', type=int, default=10, help='每爬N条输出一次进度，默认10')
    parser.add_argument('--show_duplicate_samples', action='store_true', help='是否打印重复ID示例，用于验证')
    args = parser.parse_args()

    # 处理恢复模式
    if args.resume:
        OUTPUT_DIR = Path(args.resume)
        if not OUTPUT_DIR.exists():
            print(f"❌ 恢复目录不存在：{args.resume}")
            return
        # 从目录名提取uid
        dir_name = OUTPUT_DIR.name
        TARGET_USER_ID = dir_name.split("_")[1] if "_" in dir_name else args.uid
        print(f"🔄 进入断点续爬模式，恢复目录：{OUTPUT_DIR}")
        print(f"👤 当前爬取用户ID：{TARGET_USER_ID}")
    else:
        # 普通模式，生成新目录
        TARGET_USER_ID = args.uid
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        OUTPUT_DIR = Path(__file__).parent / "data" / f"weibos_{TARGET_USER_ID}_{current_time}"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        print(f"🚀 启动新爬取任务，输出目录：{OUTPUT_DIR}")

    # 配置日志：同时输出到控制台和文件
    LOG_FILE = OUTPUT_DIR / "crawl.log"
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    logger.info(f"日志已初始化，日志文件：{LOG_FILE}")

    # 路径配置
    TARGET_USER_URL = f"https://m.weibo.cn/u/{TARGET_USER_ID}"
    CRAWLED_ID_FILE = OUTPUT_DIR / "crawled_ids.txt"
    BATCH_SIZE = args.batch_size
    MAX_EMPTY_SCROLL = args.max_empty_scroll
    LOG_INTERVAL = args.log_interval

    # 加载已爬数据
    crawled_ids = load_crawled_ids(CRAWLED_ID_FILE)
    all_weibos = load_existing_weibos(OUTPUT_DIR)
    current_batch = []
    batch_num = get_next_batch_num(OUTPUT_DIR)

    logger.info(f"📊 已加载历史数据：已爬取 {len(crawled_ids)} 条，已有原创微博 {len(all_weibos)} 条，下一批次号：{batch_num}")

    # 启动浏览器
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=bool(args.headless),
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844},
            is_mobile=True
        )
        page = context.new_page()

        try:
            # 先处理游客验证，拿到访问权限
            print("🔑 正在处理游客验证...")
            handle_visitor_verification(page)

            print("🌐 访问用户主页...")
            page.goto(TARGET_USER_URL, timeout=60000)
            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(4)  # 适配慢网络

            # 关闭弹窗
            try:
                page.click(".m-img-box-close", timeout=2000)
                logger.info("🪟 关闭广告弹窗")
            except:
                pass

            # 保存用户信息
            user_name = "未知用户"
            user_desc = ""
            try:
                # 优先用新版选择器
                if page.query_selector(".mod-fil-name", timeout=3000):
                    user_name = page.text_content(".mod-fil-name").strip()
                elif page.query_selector(".name", timeout=2000):
                    user_name = page.text_content(".name").strip()
                # 提取简介
                if page.query_selector(".mod-fil-desc, .desc", timeout=2000):
                    user_desc = page.text_content(".mod-fil-desc, .desc").strip()
            except Exception as e:
                logger.debug(f"提取用户信息失败: {str(e)}")
            logger.info(f"👤 爬取用户: {user_name} (ID: {TARGET_USER_ID})")
            logger.info(f"📝 用户简介: {user_desc[:100]}..." if len(user_desc) > 100 else f"📝 用户简介: {user_desc}")

            with open(OUTPUT_DIR / "user_info.json", "w", encoding="utf-8") as f:
                json.dump({
                    "user_id": TARGET_USER_ID,
                    "user_name": user_name,
                    "user_desc": user_desc,
                    "crawl_start_time": datetime.now().isoformat(),
                    "resume_mode": bool(args.resume)
                }, f, ensure_ascii=False, indent=2)

            empty_scroll_count = 0  # 连续滚动到底部次数
            no_new_count = 0        # 连续无新增内容次数
            scroll_count = 0
            last_log_count = len(all_weibos)

            while empty_scroll_count < MAX_EMPTY_SCROLL and no_new_count < MAX_EMPTY_SCROLL:
                scroll_count += 1
                # 只选择有内容的有效微博卡片，适配新版页面class
                weibo_cards = page.query_selector_all("div.card, div.m-panel, div[class*='card9']:has(.weibo-text), div.weibo-card:has(.weibo-text)")
                logger.info(f"[滚动第{scroll_count}次] 📄 当前有效卡片数: {len(weibo_cards)} | 累计已爬原创微博: {len(all_weibos)} 条")

                if not weibo_cards:
                    logger.warning("⚠️  无有效卡片，等待2秒后重试")
                    time.sleep(2)
                    empty_scroll_count +=1
                    continue

                new_count = 0
                repost_count = 0
                duplicate_count = 0
                empty_content_count = 0
                duplicate_samples = []

                for idx, card in enumerate(weibo_cards):
                    try:
                        # 提取内容
                        content_elem = card.query_selector(".weibo-text")
                        content = content_elem.text_content().strip() if content_elem else ""
                        if not content:
                            empty_content_count +=1
                            logger.debug(f"⚠️  第{idx+1}张卡片跳过：内容为空")
                            continue

                        # 提取ID：优先从卡片属性找，再找链接
                        weibo_id = None
                        # 尝试从卡片的mid属性提取（更准确）
                        if card.get_attribute("mid"):
                            weibo_id = card.get_attribute("mid")
                        else:
                            # 遍历所有链接找status
                            links = card.query_selector_all("a[href*='/status/']")
                            for link in links:
                                href = link.get_attribute("href")
                                if "/status/" in href:
                                    weibo_id = href.split("/status/")[-1].split("?")[0]
                                    break

                        if not weibo_id:
                            # 兜底用内容哈希
                            weibo_id = "hash_" + get_content_hash(content)
                            logger.debug(f"⚠️  第{idx+1}张卡片未找到ID，使用哈希ID: {weibo_id}")

                        if weibo_id in crawled_ids:
                            duplicate_count +=1
                            if args.show_duplicate_samples and len(duplicate_samples) < 5:
                                duplicate_samples.append(weibo_id)
                            logger.debug(f"⚠️  第{idx+1}张卡片跳过：ID {weibo_id} 已爬过")
                            continue

                        # 提取时间
                        time_elem = card.query_selector(".time")
                        time_str = time_elem.text_content().strip() if time_elem else ""

                        # 处理全文
                        has_full_text = card.query_selector("a:has-text('全文')") is not None
                        if has_full_text and len(content) < 150:
                            logger.info(f"🔍 微博ID {weibo_id} 有全文，正在获取完整内容...")
                            content_before_len = len(content)
                            full_content, _ = get_full_content(page, weibo_id)
                            if full_content:
                                content = full_content
                                logger.info(f"✅ 全文获取成功，原长度: {content_before_len} -> 新长度: {len(full_content)}")

                        # 过滤转发：增加更宽松的判断，避免误杀
                        is_repost = False
                        has_retweet_elem = card.query_selector(".retweet") is not None or card.query_selector(".weibo-retweet") is not None
                        has_retweet_text = content.startswith("//@") or content.startswith("转发微博") or content.startswith("转发了") or content.startswith("Repost")
                        if has_retweet_elem or has_retweet_text:
                            is_repost = True
                            repost_count +=1
                            logger.debug(f"⚠️  第{idx+1}张卡片跳过：转发内容，ID {weibo_id}")
                            # 转发也记录ID，避免重复处理
                            crawled_ids.add(weibo_id)
                            save_crawled_id(CRAWLED_ID_FILE, weibo_id)
                            continue

                        # 保存原创
                        weibo_data = {
                            "id": weibo_id,
                            "content": content,
                            "publish_time": time_str,
                            "crawl_time": datetime.now().isoformat(),
                            "url": f"https://m.weibo.cn/status/{weibo_id}" if not weibo_id.startswith("hash_") else "",
                            "is_full_text": has_full_text
                        }
                        all_weibos.append(weibo_data)
                        current_batch.append(weibo_data)
                        crawled_ids.add(weibo_id)
                        save_crawled_id(CRAWLED_ID_FILE, weibo_id)
                        new_count +=1

                        logger.debug(f"✅ 第{idx+1}张卡片保存成功：ID {weibo_id}，内容长度 {len(content)}")

                        # 定期输出进度
                        if len(all_weibos) - last_log_count >= LOG_INTERVAL:
                            logger.info(f"⏳ 进度更新：已爬取 {len(all_weibos)} 条原创微博，本次滚动已新增 {new_count} 条")
                            last_log_count = len(all_weibos)

                        # 达到批次大小保存
                        if len(current_batch) >= BATCH_SIZE:
                            logger.info(f"📦 达到批次大小 {BATCH_SIZE}，正在保存第 {batch_num} 批...")
                            batch_num = save_batch(current_batch, OUTPUT_DIR, batch_num)
                            current_batch = []
                            # 实时更新全量文件
                            with open(OUTPUT_DIR / "weibos_all.json", "w", encoding="utf-8") as f:
                                json.dump(all_weibos, f, ensure_ascii=False, indent=2)
                            logger.info(f"✅ 批次保存完成，全量文件已更新")

                    except Exception as e:
                        logger.error(f"⚠️  第{idx+1}张卡片处理失败: {str(e)}")
                        continue

                # 统计
                logger.info(f"📊 [滚动第{scroll_count}次] 处理完成：新增原创 {new_count} 条，重复 {duplicate_count} 条，转发 {repost_count} 条，空内容 {empty_content_count} 条")
                # 打印重复示例
                if args.show_duplicate_samples and duplicate_samples:
                    logger.info(f"🔍 重复ID示例: {', '.join(duplicate_samples)}")
                # 高重复率提示
                if duplicate_count > new_count * 10 and new_count > 0:
                    logger.info(f"💡 提示：高重复率是微博正常特性，滚动时返回大量旧内容，无需担心")

                # 无新增计数，连续多次无新增自动退出
                if new_count == 0:
                    no_new_count +=1
                    if no_new_count >= MAX_EMPTY_SCROLL:
                        logger.info(f"⏹️  连续 {no_new_count} 次滚动无新增原创内容，已爬取到所有可见内容，自动停止爬取")
                        break
                else:
                    no_new_count = 0
                    last_log_count = len(all_weibos)

                # 滚动加载
                logger.info("⬇️  正在滚动加载更多内容...")
                old_height = page.evaluate("document.body.scrollHeight")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2.5)
                new_height = page.evaluate("document.body.scrollHeight")

                if new_height == old_height:
                    empty_scroll_count +=1
                    logger.info(f"📜 已到页面最底部，连续 {empty_scroll_count}/{MAX_EMPTY_SCROLL} 次滚动无高度变化，剩余 {MAX_EMPTY_SCROLL - empty_scroll_count} 次后自动停止")

            # 保存剩余批次
            if current_batch:
                logger.info(f"📦 保存最后一批剩余 {len(current_batch)} 条微博...")
                batch_num = save_batch(current_batch, OUTPUT_DIR, batch_num)

            # 保存最终全量文件
            logger.info("💾 正在保存最终全量汇总文件...")
            with open(OUTPUT_DIR / "weibos_all.json", "w", encoding="utf-8") as f:
                json.dump(all_weibos, f, ensure_ascii=False, indent=2)

            # 保存完成标记
            with open(OUTPUT_DIR / "crawl_complete.json", "w", encoding="utf-8") as f:
                json.dump({
                    "complete_time": datetime.now().isoformat(),
                    "total_weibos": len(all_weibos),
                    "total_batches": batch_num -1
                }, f, ensure_ascii=False, indent=2)

            # 结果统计
            logger.info("🎉 ==============================================")
            logger.info(f"✅ 爬取全部完成！总原创微博数: {len(all_weibos)} 条")
            logger.info(f"📂 所有文件已保存到: {OUTPUT_DIR}/")
            logger.info(f"   - 用户信息文件: user_info.json")
            logger.info(f"   - 完整汇总文件: weibos_all.json")
            if (batch_num -1) > 0:
                logger.info(f"   - 批次文件: weibos_batch_001.json ~ weibos_batch_{(batch_num-1):03d}.json")
            logger.info(f"   - 进度记录文件: crawled_ids.txt（用于断点续爬）")
            logger.info(f"   - 运行日志文件: crawl.log")

            if all_weibos:
                logger.info("\n📋 最新10条微博预览：")
                for i, w in enumerate(all_weibos[-10:]):
                    content = w['content'].replace("\n", " ")[:120]
                    logger.info(f"{i+1}. [{w['publish_time']}] {'[全文]' if w['is_full_text'] else ''} {content}{'...' if len(w['content'])>120 else ''}")

        except KeyboardInterrupt:
            logger.warning("\n⚠️  用户手动中断，正在保存当前进度...")
            # 中断时保存剩余内容
            if current_batch:
                save_batch(current_batch, OUTPUT_DIR, batch_num)
            with open(OUTPUT_DIR / "weibos_all.json", "w", encoding="utf-8") as f:
                json.dump(all_weibos, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ 进度已完整保存到：{OUTPUT_DIR}")
            logger.info("💡 下次运行时加上 --resume 参数即可从中断处继续爬取，无需重复爬取")
        except Exception as e:
            logger.error(f"❌ 爬取发生错误: {str(e)}")
            import traceback
            traceback.print_exc()
            logger.error("💡 错误信息已记录到日志文件，可查看 crawl.log 排查问题")
        finally:
            browser.close()
            logger.info("👋 爬虫已退出，感谢使用")

if __name__ == "__main__":
    main()
