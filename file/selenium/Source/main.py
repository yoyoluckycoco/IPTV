import os
import re
import requests
import time
from github import Github
import concurrent.futures
from bs4 import BeautifulSoup
from selenium import webdriver
from collections import defaultdict
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime


class ChannelProcessor:

    def __init__(self):
        self.options = webdriver.ChromeOptions()
        self.options.add_argument("--headless")
        self.options.add_argument("blink-settings=imagesEnabled=false")
        self.options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.options.add_experimental_option("useAutomationExtension", False)
        self.options.add_argument("--log-level=3")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.service = Service(log_path=os.devnull)  # 禁用日志输出
        self.session = requests.Session()
        self.driver = webdriver.Chrome(service=self.service, options=self.options)

    #获取酒店ip
    def get_channel_links(self, search_term):
        """获取酒店组播"""
        driver = webdriver.Chrome(service=self.service, options=self.options)
        url_dict = {}  # 初始化为一个空字典
        try:
            driver.get('http://www.foodieguide.com/iptvsearch/hoteliptv.php')
            driver.execute_script(f"""
                document.getElementById("search").value = "{search_term}";
                document.getElementById('form1').submit();
            """)
            channel_links = driver.find_elements(By.XPATH, '//div[@class="channel"]//a')
            url_dict = {elem.get_attribute("href").split("hotellist.html?s=")[-1]: i for i, elem in
                        enumerate(channel_links)}
            for key, value in url_dict.items():
                print(f"{key}: {value}")
        except Exception as e:
            print("获取酒店组播时发生错误:", e)
        finally:
            driver.quit()

        # 返回获取到的 url_dict
        return url_dict


    #获取直播源
    def get_channel_info_s(self, url_dict):
        driver = webdriver.Chrome(service=self.service, options=self.options)
        channels_info_dict = {}  
        with open('pz/del_ip.txt', 'r') as f:
            banned_ips = f.read().splitlines()
        for url_id in url_dict.keys():
            if url_id not in banned_ips:
                try:
                    print("访问：", url_id)
                    driver.get('http://www.foodieguide.com/iptvsearch/hotellist.html?s=' + url_id)
                    print("等待JavaScript执行完成")
                    wait = WebDriverWait(driver, 15)
                    wait.until(EC.presence_of_element_located((By.ID, "hiddenresult")))
                    result_html = driver.execute_script('return document.querySelector("#hiddenresult").innerHTML;')
                    soup = BeautifulSoup(result_html, 'html.parser')
                    result_divs = soup.find_all('div', class_='result')
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
                        channels_info_dict[channel_url] = (channel_name, channel_url, 2)

                except Exception as e:
                    print(f"Error processing url {url_id}: {e}")
                    continue  # 跳过当前的循环迭代并继续下一次循环

        driver.quit()
        channels_info = list(channels_info_dict.values())  # Convert dictionary values back to list
        if not channels_info:  # 检查 channels_info 是否为空
            print("未获取到链接")
        else:
            with open('pz/itv.txt', 'w', encoding='utf-8') as f:
                for channel_info in channels_info:  # 遍历 channels_info 列表
                    f.write(f"{channel_info[0]},{channel_info[1]}\n")  # 写入频道信息
        return channels_info

    # 直播源测速
    def download_speed_test(self, channel):
         # Use session for requests
        session = self.session
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
                    continue  # 如果没有 break，就继续下一次循环
                download_time = time.time() - start_time
                download_rate = round(size / download_time / 1024 / 1024, 4)
                break  # 如果下载成功，就跳出循环
            except requests.RequestException:
                pass  # 如果下载失败，就忽略异常并继续下一次循环
        else:  # 如果三次尝试都失败，就打印错误信息并返回
            print(f"频道：{name}, URL: {url}, 0 MB/s")
            return name, url, 0
        print(f"频道：{name}, URL: {url}, {download_rate} MB/s")
        return name, url, download_rate
 
    #过滤和修改直播源
    def filter_and_modify_sources(self, sources):
        """过滤和修改直播源"""
        filtered_sources = []
        name_dict = ['测试', '4k', '音轨', '购物', '理财', '百姓健康', '测试', '冬奥', '奥林匹克', '直播室', '导视', '睛彩',
                     'CGTN', '台球', '指南', '足球', '高网', '高尔夫', '网球', '梨园']

        for name, url, speed in sources:
            if float(speed) <= 0.5:
                continue
            if any(word.lower() in name.lower() for word in name_dict):
                print("过滤:" + name)
            else:
                name = name.replace(' ', '').replace('⁺', '+').replace('＋', '+').replace('-', '').replace('[R]', '') \
                    .replace('超高清', '').replace('[超清]', '').replace('LD', '').replace('超清', '').replace('高清', '').replace('高请', '') \
                    .replace('画中画', '').replace('BRTV北京', '北京').replace('CHC', '').replace('HD', '').replace('上海东方', '东方') \
                    .replace('IPTV', '').replace('电视台', '').replace('北京卡酷少儿', '').replace('教育卫视', '').replace('中文国际', '') \
                    .replace('BTV', '北京').replace('北京北京', '北京').replace('（备）', '').replace('CCTV少儿', 'CCTV14') \
                    .replace('CCTV音乐', 'CCTV15').replace('CCTV风云音乐', 'CCTV15').replace('戏曲', 'CCTV10').replace('CCTV农业', 'CCTV7') \
                    .replace('CCTV电视剧', 'CCTV8').replace('CCTV电影', 'CCTV6').replace('CCTV综艺', 'CCTV3').replace('CCTV新闻', 'CCTV13') \
                    .replace('CCTV4国际', 'CCTV4').replace('CCTV科教', 'CCTV9').replace('党建频道', '党建').replace('北京卡酷', '卡酷') \
                    .replace('戏曲精选', '戏曲').replace('种养新影老故事', '老故事').replace('(国际版)', '').replace('国际', '').replace('中国教育', 'CETV') \
                    .replace('体验', '').replace('空中课堂', '').replace('阿语', '阿拉伯语').replace('安徽频道', '安徽卫视').replace('央视精品', '央视文化') \
                    .replace('央视文化精品', '央视文化').replace('兵器', '兵器科技').replace('四川康巴卫视', '四川康巴').replace('世界地理', 'CCTV世界地理') \
                    .replace('兵器科技', 'CCTV兵器科技').replace('怀旧剧场', 'CCTV怀旧剧场').replace('女性时尚', 'CCTV女性时尚').replace('央视网球', 'CCTV高尔夫网球') \
                    .replace('风云足球', 'CCTV风云足球').replace('凤凰卫视中文台', '凤凰卫视').replace('凤凰卫视资讯台', '凤凰资讯').replace('纪实', '纪实人文') \
                    .replace('人文人文', '人文').replace('科技科技', '科技').replace('CCTVCCTV', 'CCTV').replace('武术', '武术世界')
                if "cctv" in name.lower() and any(char.isdigit() for char in name):
                    if "cctv4" not in name.lower():
                        name = re.sub(r'[\u4e00-\u9fff]+', '', name)
                filtered_sources.append((name, url, speed))
        return filtered_sources

    # 读取分类和排序规则文件
    def read_categories(self, filename):
        """读取分类和排序规则文件，并返回一个包含分类信息的字典"""
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

    # 读取直播源文件
    def read_file_to_list(self, filename):
        """读取文件到列表"""
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        channels = []
        for line in lines:
            if line.strip():
                parts = line.strip().split(',')
                if len(parts) == 3:
                    name, url, speed = parts
                elif len(parts) == 2:
                    name, url = parts
                    speed = '0'  # 如果没有速度信息，就默认速度为 '0'
                else:
                    continue  # 如果不是两个或三个部分，就跳过这行
                channels.append((name, url, speed))
        return channels

     #对直播源进行分类和排序
    
    # 对频道进行分类和排序
    def classify_and_sort_sources(self, sources):
        # 读取分类信息
        categories = self.read_categories('pz/sort.txt')
        # 定义分类的特定顺序
        def classify_sources(sources, categories):  
            classified = defaultdict(list)  
            for name, url, speed in sources:  
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
  
        # 对频道进行排序的关键字函数  
        def channel_key(channel_name, speed):  
            match = re.search(r'\d+', channel_name)  
            speed_int = int(speed) if speed.isdigit() else 0  
            if match:  
                return (int(match.group()), -speed_int) 
            else:  
                return (float('inf'), -speed_int) 
  
        classified_sources = classify_sources(sources, categories)  
        specific_order = ["央视频道,", "卫视频道,", "影视剧场,", "地方频道,"]  
        other_categories = [cat for cat in classified_sources if cat not in specific_order]  
        sorted_categories = specific_order + sorted(other_categories)  
        with open("itvlist.txt", "w", encoding="utf-8") as f:  
            for category in sorted_categories:  
                if category in classified_sources:  
                    f.write(f"{category}#genre#\n")  
                    source_list = classified_sources[category]  
                    source_list.sort(key=lambda x: (channel_key(x[0], x[2]), x[0]) if "cctv" in x[0].lower() else (x[0], -float(x[2])))

                    deleted_urls = set()  
                    with open('pz/deleted.txt', 'r', encoding='utf-8') as file:  
                        for line in file:  
                            deleted_urls.add(line.strip())
                    for name, url, speed in source_list:  
                        if url not in deleted_urls:  
                            f.write(f"{name},{url}\n")  
                    f.write("\n")  

    # 上传文件到GitHub
    def upload_file_to_github(self, token, repo_name, file_path, branch="main"):
        # 使用你的 GitHub token 创建一个 Github 实例
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
            repo.update_file(contents.path, current_time, content, contents.sha, branch=branch)
        else:
            repo.create_file(git_path, current_time, content, branch=branch)
        print("已同步到GitHub")    
    
    def run(self):
        url_dict = self.get_channel_links("北京")
        urls = self.get_channel_info_s(url_dict)
        with concurrent.futures.ThreadPoolExecutor() as executor:
            urls = list(executor.map(self.download_speed_test, urls))
        urls = [url for url in urls if float(url[2]) > 0]
        urls.sort(key=lambda url: float(url[2]), reverse=True)
        
        if urls:  # 如果 urls 不为空
            with open('pz/itv.txt', 'w', encoding='utf-8') as f:
                for url in urls:
                    f.write(','.join(map(str, url)) + '\n')
            urls = self.read_file_to_list('pz/itv.txt')
            sources = self.filter_and_modify_sources(urls)
            self.classify_and_sort_sources(sources)
            print("处理完成，结果已保存到 itvlist.txt 文件中。")
            self.upload_file_to_github("", "IPTV", "itvlist.txt", "main")
        else:
            print("未获取到链接，无法处理。")

if __name__ == "__main__":
    processor = ChannelProcessor()
    processor.run()