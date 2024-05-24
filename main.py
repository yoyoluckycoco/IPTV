import threading
from queue import Queue
import time
import random
from bs4 import BeautifulSoup
import re
from playwright.sync_api import sync_playwright
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from datetime import datetime
from github import Github
import asyncio


def init_browser():
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    return browser, playwright

def close_browser(browser, playwright):
    browser.close()
    playwright.stop()

def intercept_requests(route):
    url = route.request.url
    # 如果请求的 URL 是广告相关的或者是统计脚本，则中止该请求
    if "googlesyndication.com" in url or "googletagmanager.com" in url or "s10.histats.com/js15_as.js" in url:
        route.abort()
    else:
        asyncio.run(route.continue_())
        
def get_hotel_multicast_search_results(search_term, page):
    url_dict = {}
    try:
        page.set_default_timeout(600000)
        page.on('route', lambda route: intercept_requests(route))
        page.goto('http://www.foodieguide.com/iptvsearch/hoteliptv.php')
        for char in search_term:
            page.type('#search', char, delay=random.uniform(0.1, 0.3))
            time.sleep(random.uniform(0.1, 0.3))
        time.sleep(random.uniform(1, 3))
        page.click('#form1 [type="submit"]')
        time.sleep(random.uniform(1, 3))
        channel_links = page.query_selector_all('.channel a')
        for i, link in enumerate(channel_links):
            href = link.get_attribute('href')
            url_dict[href.split("hotellist.html?s=")[-1]] = i
    except Exception as e:
        print("获取酒店组播时发生错误:", e)
    return url_dict

def fetch_channel_info_worker(task_queue, result_queue):
    browser, playwright = init_browser()
    page = browser.new_page()

    while True:
        url_id = task_queue.get()
        if url_id is None:
            break

        channels_info = []
        try:
            page.on('route', lambda route: intercept_requests(route))
            page.goto(f'http://www.foodieguide.com/iptvsearch/hotellist.html?s={url_id}', timeout=120000)
            time.sleep(random.uniform(5, 10))
            hidden_result = page.query_selector("#hiddenresult")
            if hidden_result:
                print("访问：", url_id, "找到 #hiddenresult")
                result_html = page.inner_html("#hiddenresult")
                soup = BeautifulSoup(result_html, 'html.parser')
                result_divs = soup.find_all('div', class_='result')

                for _ in range(3):
                    time.sleep(random.uniform(0.5, 1.5))
                    x = random.randint(100, 500)
                    y = random.randint(100, 500)
                    page.mouse.move(x, y)

                for result_div in result_divs:
                    channel_name_element = result_div.find('div', class_='channel')
                    channel_name_link = channel_name_element.find('a') if channel_name_element else None
                    if channel_name_link:
                        channel_name = channel_name_link.text.strip()
                    else:
                        continue
                    m3u8_element = result_div.find('div', class_='m3u8')
                    if m3u8_element:
                        url_td = m3u8_element.find('td', style=re.compile(r'padding-left:\s*6px;'))
                        if url_td:
                            channel_url = url_td.text.strip()
                        else:
                            continue
                    else:
                        continue
                    channels_info.append((channel_name, channel_url, 2))
            else:
                print("访问：", url_id, "未找到 #hiddenresult")

            if channels_info:
                result_queue.put((url_id, channels_info))

        except requests.Timeout as e:
            print(f"获取频道信息时发生网络超时异常: {e}")

        except Exception as e:
            print("获取频道信息时发生异常:", e)

        task_queue.task_done()

    page.close()
    close_browser(browser, playwright)

def get_hotel_multicast_channel_info(url_dict):
    existing_urls = set()
    with open('log/url_log.txt', 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            existing_urls.add(line)  # 直接将整行作为 URL 添加到集合中
    task_queue = Queue()
    result_queue = Queue()

    for url_id in url_dict.keys():
        if url_id not in existing_urls:
            task_queue.put(url_id)

    worker_thread = threading.Thread(target=fetch_channel_info_worker, args=(task_queue, result_queue))
    worker_thread.start()

    task_queue.join()
    task_queue.put(None)
    worker_thread.join()

    channels_info_dict = {}
    new_url_info = {}
    while not result_queue.empty():
        url_id, channels_info = result_queue.get()
        for name, url, speed in channels_info:
            channels_info_dict[url] = (name, url, speed)
            if url_id not in existing_urls:
                if url_id not in new_url_info:
                    new_url_info[url_id] = []
                new_url_info[url_id].append((name, url, speed))

    channels_info = list(channels_info_dict.values())
    if not channels_info:
        print("未获取到链接")
    else:
        with open('log/itv.txt', 'w', encoding='utf-8') as f:
            for channel_info in channels_info:
                f.write(f"{channel_info[0]},{channel_info[1]}\n")
        # 将新记录的 URL 写入 url_log.txt
        with open('log/url_log.txt', 'a', encoding='utf-8') as f: 
            for url_id in new_url_info.keys():
                f.write(f"{url_id}\n")

    return channels_info

def download_speed_test(channel):
    session = requests.Session()
    if len(channel) == 3:
        name, url, _ = channel
    else:
        name, url = channel
    chaoshi = 5
    for _ in range(1):
        try:
            start_time = time.time()
            response = session.get(url, stream=True, timeout=5)
            response.raise_for_status()
            size = 0
            for chunk in response.iter_content(chunk_size=1024):
                size += len(chunk)
                if time.time() - start_time >= chaoshi:
                    break
            else:
                continue
            download_time = time.time() - start_time
            download_rate = round(size / download_time / 1024 / 1024, 4)
            break
        except requests.RequestException:
            pass
    else:
        print(f"频道：{name}, URL: {url}, 0 MB/s")
        return name, url, 0
    print(f"频道：{name}, URL: {url}, {download_rate} MB/s")
    return name, url, download_rate

def filter_and_modify_sources(sources):
    filtered_sources = []
    name_dict = {
        ' ': '', '⁺': '+', '＋': '+', '-': '', '[R]': '', '超高清': '', '[超清]': '', 'LD': '', '超清': '', '高清': '', '高请': '',
        '画中画': '', 'BRTV北京': '北京', 'CHC': '', 'HD': '', 'IPTV': '', '电视台': '', '北京卡酷少儿': '', '教育卫视': '', '中文国际': '',
        'BTV': '北京', '北京北京': '北京', '（备）': '', 'CCTV少儿': 'CCTV14', 'CCTV音乐': 'CCTV15', 'CCTV风云音乐': 'CCTV15', '戏曲': 'CCTV10', 
        'CCTV农业': 'CCTV7', 'CCTV电视剧': 'CCTV8', 'CCTV电影': 'CCTV6', 'CCTV综艺': 'CCTV3', 'CCTV新闻': 'CCTV13', 'CCTV4国际': 'CCTV4', 
        'CCTV科教': 'CCTV9', '党建频道': '党建', '北京卡酷': '卡酷', '戏曲精选': '戏曲', '种养新影老故事': '老故事', '(国际版)': '', '国际': '', 
        '中国教育': 'CETV', '体验': '', '空中课堂': '', '阿语': '阿拉伯语', '安徽频道': '安徽卫视', '央视精品': '央视文化', '央视文化精品': '央视文化', 
        '兵器': '兵器科技', '四川康巴卫视': '四川康巴', '世界地理': 'CCTV世界地理', '兵器科技': 'CCTV兵器科技', '怀旧剧场': 'CCTV怀旧剧场', 
        '女性时尚': 'CCTV女性时尚', '央视网球': 'CCTV高尔夫网球', '风云足球': 'CCTV风云足球', '凤凰卫视中文台': '凤凰卫视', '凤凰卫视资讯台': '凤凰资讯', 
        '纪实': '纪实人文', '人文人文': '人文', '科技科技': '科技', 'CCTVCCTV': 'CCTV', '武术': '武术世界'
    }

    for name, url, speed in sources:
        if float(speed) > 0.4:
            for key, value in name_dict.items():
                name = name.replace(key, value)
            name = re.sub(r'\(\d+\)', '', name).strip()
            filtered_sources.append((name, url, speed))
            with open('log/sort.txt', 'a', encoding='utf-8') as file:
                file.write(f"{name},{url},{speed}\n")

    return filtered_sources

def read_categories(filename):
    categories = {}
    current_category = None
    with open(filename, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.endswith('#genre#'):
                current_category = line[:-7].strip()
                categories[current_category] = []
            elif current_category:
                categories[current_category].append(line)
    return categories

def classify_and_sort_sources(sources):
    categories = read_categories('log/sort.txt')

    def classify_sources(sources, categories):  
        classified = defaultdict(list)  
        for name, url, speed in sources:  
            if float(speed) > 0.1: 
                found = False  
                for category, channel_list in categories.items():  
                    for channel in channel_list:  
                        if channel in name:  
                            classified[category].append((name, url, speed))  
                            found = True  
                            break  
                    if found:  
                        break  
                if not found:  
                    classified["其他,"].append((name, url, speed))  
        return classified  

    def channel_key(channel_name, speed):  
        match = re.search(r'\d+', channel_name) 
        speed_int = int(speed) if isinstance(speed, int) or isinstance(speed, float) else 0  
        if match:
            num = int(match.group())  
        else:
            num = float('inf') 
        return (num, -float(speed))  

    classified_sources = classify_sources(sources, categories)  
    specific_order = ["央视频道,",  "卫视频道,", "影视剧场,", "地方频道,"]  
    other_categories = [cat for cat in categories if cat not in specific_order]  

    sorted_categories = specific_order + sorted(other_categories)  

    with open("itvlist.txt", "w", encoding="utf-8") as f:  
        for category in sorted_categories:  
            if category in classified_sources:  
                f.write(f"{category}#genre#\n")  
                source_list = classified_sources[category]  
                source_list.sort(key=lambda x: (channel_key(x[0], x[2]), x[0]) if "cctv" in x[0].lower() else (x[0], -x[2]))
                for name, url, speed in source_list:  
                    f.write(f"{name},{url}\n")  
                f.write("\n")  

def read_itv_file(file_path):
    sources = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split(',')
            if len(parts) < 3:
                continue
            name = parts[0]
            url = parts[1]
            speed = float(parts[2]) 
            sources.append((name, url, speed))
    return sources

def upload_file_to_github(token, repo_name, file_path, branch="main"):
    g = Github(token)
    repo = g.get_user().get_repo(repo_name)
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    git_path = file_path.split('/')[-1]
    try:
        contents = repo.get_contents(git_path, ref=branch)
    except:
        contents = None
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if contents:
        try:
            repo.update_file(contents.path, current_time, content, contents.sha, branch=branch)
            print("文件已更新")
        except:
            print("文件更新失败")
    else:
        try:
            repo.create_file(git_path, current_time, content, branch=branch)
            print("文件已创建")
        except:
            print("文件创建失败")




if __name__ == "__main__":
    browser, playwright = init_browser()
    page = browser.new_page()
    result = get_hotel_multicast_search_results("北京",page)
    if len(result) > 0:
        sources = get_hotel_multicast_channel_info(result)
        if len(sources) > 0:
            filtered_sources = filter_and_modify_sources(sources)

            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_channel = {executor.submit(download_speed_test, source): source for source in filtered_sources}
                speed_test_results = []
                for future in as_completed(future_to_channel):
                    channel = future_to_channel[future]
                    try:
                        result = future.result()
                        speed_test_results.append(result)
                    except Exception as exc:
                        print(f"频道：{channel[0]} 测速时发生异常：{exc}")

            with open('log/itv.txt', 'w', encoding='utf-8') as file:
                for name, url, speed in speed_test_results:
                    if speed > 0:
                        file.write(f"{name},{url},{speed} MB/s\n")

            classify_and_sort_sources(speed_test_results)
            upload_file_to_github("", "IPTV", "itvlist.txt")

    # 对本地分组排序
    # file_path = 'log/itv.txt'
    # sources = read_itv_file(file_path)
    # classify_and_sort_sources(sources)
    # upload_file_to_github("", "IPTV", "itvlist.txt")