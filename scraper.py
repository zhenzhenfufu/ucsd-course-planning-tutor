import requests
from bs4 import BeautifulSoup
import json
import re

url = "https://catalog.ucsd.edu/courses/DSC.html"
headers = {'User-Agent': 'Mozilla/5.0'}
response = requests.get(url, headers=headers)

if response.status_code == 200:
    soup = BeautifulSoup(response.text, 'html.parser')
    courses = soup.find_all('p', class_='course-name')
    descriptions = soup.find_all('p', class_='course-descriptions')
    
    course_data = []
    for i in range(len(courses)):
        full_title = courses[i].text.strip()
        desc = descriptions[i].text.strip() if i < len(descriptions) else ""
        
        # 1. 提取 ID 和 原始名称
        parts = full_title.split('.', 1)
        if len(parts) < 2: continue
        
        c_id = parts[0].strip().replace('/R', '')
        remaining = parts[1].strip()
        
        # 2. 过滤编号
        num_match = re.search(r'DSC\s+(\d+)', c_id)
        if num_match:
            num = int(num_match.group(1))
            if 90 <= num <= 99 or num >= 200: continue

        # 3. 提取学分 (Units) - 匹配末尾括号内的数字
        unit_match = re.search(r'\((\d+)\)', remaining)
        units = int(unit_match.group(1)) if unit_match else 4
        # 清理名称中的学分部分
        c_name = re.sub(r'\(\d+\)', '', remaining).strip()

        # 4. 尝试寻找非 DSC 的前置课 (如 MATH, CSE)
        # 这是一个简单的正则，匹配描述中出现的特定前置课关键词
        ext_pre = re.findall(r'(MATH\s+\d+[A-Z]*|CSE\s+\d+[A-Z]*)', desc)
        
        course_data.append({
            "id": c_id,
            "name": c_name,
            "units": units,
            "description": desc,
            "external_prereqs": list(set(ext_pre))
        })
            
    with open('dsc_courses.json', 'w', encoding='utf-8') as f:
        json.dump(course_data, f, ensure_ascii=False, indent=4)
    print(f"✅ 成功抓取 {len(course_data)} 门课，已包含学分和外部前置。")