import os
import json
from google import genai
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# 初始化 2026 新版客户端
# 即使 key 没配置好，也不会导致整个 app 崩溃
client = genai.Client(api_key=api_key) if api_key else None

def get_ai_advice(user_question):
    if client is None:
        return "❌ **API Key Missing**: Please configure GEMINI_API_KEY in Streamlit Secrets."

    try:
        # 读取课程 JSON
        with open('dsc_courses.json', 'r', encoding='utf-8') as f:
            courses = json.load(f)
        catalog_context = json.dumps(courses, ensure_ascii=False)

        # 使用 2.0-flash 模型，它是 2026 年反应最快的选择
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            config={
                "system_instruction": (
                    "You are the official UCSD DSC Academic Advisor. "
                    "Rule 1: Use ONLY the provided JSON data for course info. "
                    "Rule 2: Respond concisely with bullet points in English."
                )
            },
            contents=f"Catalog Data: {catalog_context}\n\nUser Inquiry: {user_question}"
        )
        return response.text

    except Exception as e:
        if "429" in str(e):
            return "⚠️ **Rate Limit**: The advisor is busy. Please wait 30 seconds."
        return f"❌ **Error**: {str(e)}"