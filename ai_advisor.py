import os
import json
# 关键修复：直接从 google.genai 导入 Client，避开 google 命名空间的冲突
try:
    from google.genai import Client
except ImportError:
    # 针对某些特定 Python 环境的兼容方案
    import google.genai as genai
    Client = genai.Client

from dotenv import load_dotenv

# 1. 加载环境变量 (本地 .env 或云端 Secrets)
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# 2. 初始化 AI 客户端
# 如果 key 丢失，这里会记录错误但不会让整个程序在启动时崩溃
if not api_key:
    client = None
else:
    client = Client(api_key=api_key)

def get_ai_advice(user_question):
    """
    充当 UCSD 数据科学系的学术顾问。
    """
    if client is None:
        return "❌ **Configuration Error**: Missing GEMINI_API_KEY. Please set it in your Secrets or .env file."

    try:
        # 3. 加载本地课程 JSON 数据库
        with open('dsc_courses.json', 'r', encoding='utf-8') as f:
            courses = json.load(f)
        
        # 将数据转换为 AI 可读的字符串格式
        catalog_context = json.dumps(courses, ensure_ascii=False)

        # 4. 调用 2026 稳定版模型 (Gemini 2.0 Flash)
        # 使用新版 SDK 架构：client.models.generate_content
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            config={
                "system_instruction": (
                    "You are a professional Academic Advisor for the Data Science Department at UC San Diego (UCSD). "
                    "Your goal is to help students plan their course schedule based on the provided JSON catalog data. "
                    "Instruction 1: ONLY use the provided catalog data for specific course details. "
                    "Instruction 2: If a course is not in the data, state that it's not currently in the DSC catalog. "
                    "Instruction 3: Format your response using clear bullet points and a professional, encouraging tone. "
                    "Instruction 4: Respond entirely in English."
                )
            },
            contents=f"Course Catalog Data: {catalog_context}\n\nStudent's Inquiry: {user_question}"
        )

        # 返回 AI 生成的文本
        return response.text

    except Exception as e:
        # 优雅处理频率限制 (Rate Limit)
        if "429" in str(e):
            return "⚠️ **Advisor's Note**: I'm currently helping a lot of students! Please wait about 30 seconds and ask again."
        # 其他系统错误的友好提示
        return f"❌ **System Error**: {str(e)}"