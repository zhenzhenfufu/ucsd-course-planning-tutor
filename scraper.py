import requests
from bs4 import BeautifulSoup
import json # 引入处理 JSON 数据的工具

# 目标网址：UCSD 数据科学 (DSC) 课程目录
url = "https://catalog.ucsd.edu/courses/DSC.html"

print(f"🚀 正在获取并结构化 UCSD DSC 课程数据...")

headers = {'User-Agent': 'Mozilla/5.0'}
response = requests.get(url, headers=headers)

if response.status_code == 200:
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 同时获取课程名字和课程描述
    courses = soup.find_all('p', class_='course-name')
    descriptions = soup.find_all('p', class_='course-descriptions')
    
    # 创建一个空列表，用来装我们整理好的数据
    course_data = []
    
    # 抓取前 15 门课作为我们的 MVP 测试数据库
    for i in range(min(15, len(courses))):
        full_title = courses[i].text.strip()
        # 匹配对应的课程描述
        desc = descriptions[i].text.strip() if i < len(descriptions) else "无描述"
        
        # 将 "DSC 10. Principles of Data Science (4)" 从第一个句号拆开
        parts = full_title.split('.', 1)
        
        if len(parts) == 2:
            course_id = parts[0].strip()   # 提取出 "DSC 10"
            course_name = parts[1].strip() # 提取出 "Principles of Data Science (4)"
            
            # 以字典结构保存每一门课
            course_data.append({
                "id": course_id,
                "name": course_name,
                "description": desc
            })
            
    # 将整理好的数据写入 JSON 文件
    with open('dsc_courses.json', 'w', encoding='utf-8') as f:
        json.dump(course_data, f, ensure_ascii=False, indent=4)
        
    print("✅ 数据已成功提取，并在左侧文件夹生成了 dsc_courses.json！")
else:
    print(f"❌ 访问失败，状态码: {response.status_code}")