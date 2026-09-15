import requests
from bs4 import BeautifulSoup
import json
import re

url = "https://catalog.ucsd.edu/courses/DSC.html"
headers = {'User-Agent': 'Mozilla/5.0'}
response = requests.get(url, headers=headers)

def get_stats(course_id):
    """
    Mock data for the 6-dimension stats. 
    In a real scenario, you could scrape CAPE or Seascape.
    Dimensions: [Popularity, Content, Exam, Assignment, Avg GPA, Weekly Hours]
    """
    # Just a logic to generate different stats for different course levels
    num = int(re.search(r'\d+', course_id).group())
    if num < 30: # Intro courses
        return [80, 40, 50, 60, 3.5, 8]
    elif num < 100: # Core lower div
        return [90, 70, 75, 85, 3.1, 15]
    else: # Upper div
        return [70, 90, 85, 95, 2.9, 20]

if response.status_code == 200:
    soup = BeautifulSoup(response.text, 'html.parser')
    courses = soup.find_all('p', class_='course-name')
    descriptions = soup.find_all('p', class_='course-descriptions')
    
    course_data = []
    for i in range(len(courses)):
        full_title = courses[i].text.strip()
        desc = descriptions[i].text.strip() if i < len(descriptions) else ""
        
        parts = full_title.split('.', 1)
        if len(parts) < 2: continue
        
        c_id = parts[0].strip().replace('/R', '')
        remaining = parts[1].strip()
        
        # Filtering: No 90-99 or 200+
        num_match = re.search(r'DSC\s+(\d+)', c_id)
        if num_match:
            num = int(num_match.group(1))
            if 90 <= num <= 99 or num >= 200: continue

        unit_match = re.search(r'\((\d+)\)', remaining)
        units = int(unit_match.group(1)) if unit_match else 4
        c_name = re.sub(r'\(\d+\)', '', remaining).strip()

        stats = get_stats(c_id)
        
        course_data.append({
            "id": c_id,
            "name": c_name,
            "units": units,
            "description": desc,
            "stats": {
                "Popularity": stats[0],
                "Content Difficulty": stats[1],
                "Exam Difficulty": stats[2],
                "Assignment Load": stats[3],
                "Average GPA": stats[4],
                "Hours/Week": stats[5]
            }
        })
            
    with open('dsc_courses.json', 'w', encoding='utf-8') as f:
        json.dump(course_data, f, ensure_ascii=False, indent=4)
    print(f"✅ Success: Scraped {len(course_data)} courses with 6D stats.")