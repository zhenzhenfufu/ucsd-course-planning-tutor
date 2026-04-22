import os
import json
from google.genai import Client  # 2026版标准导入
from dotenv import load_dotenv

load_dotenv()

# 初始化客户端
api_key = os.getenv("GEMINI_API_KEY")
client = Client(api_key=api_key) if api_key else None

def get_ai_advice(user_question):
    if not client:
        return "❌ **Missing API Key**: Check your Streamlit Secrets."

    try:
        with open('dsc_courses.json', 'r', encoding='utf-8') as f:
            courses = json.load(f)
        catalog_context = json.dumps(courses, ensure_ascii=False)

        # 使用 gemini-2.0-flash，速度最快
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            config={
                "system_instruction": "You are a UCSD Data Science Advisor. Answer concisely in English using the provided JSON."
            },
            contents=f"Catalog: {catalog_context}\n\nQuestion: {user_question}"
        )
        return response.text
    except Exception as e:
        if "429" in str(e):
            return "⚠️ **Busy**: Too many requests, please try in 30s."
        return f"❌ **AI Error**: {str(e)}"