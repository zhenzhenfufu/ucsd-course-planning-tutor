import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

# 1. 加载配置
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

def get_ai_advice(user_question):
    with open('dsc_courses.json', 'r', encoding='utf-8') as f:
        courses = json.load(f)
    catalog_context = json.dumps(courses, ensure_ascii=False)

    # 强制匹配你账号里的 2.5 版本
    model = genai.GenerativeModel('models/gemini-2.5-flash')
    
    prompt = f"你是 UCSD 辅导员，基于数据回答问题：\n数据：{catalog_context}\n问题：{user_question}"

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        if "429" in str(e):
            return "⚠️ **辅导员提示**：哎呀，问得太快了！请等 30 秒再试一次。"
        return f"❌ **系统错误**：{str(e)}"