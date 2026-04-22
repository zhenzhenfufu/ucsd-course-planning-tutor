import os
import json
from google import genai
from dotenv import load_dotenv

load_dotenv()

def get_ai_advice(user_question):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "❌ **Missing API Key**: Please set GEMINI_API_KEY in Streamlit Secrets."

    try:
        # 初始化客户端
        client = genai.Client(api_key=api_key)
        
        # 加载数据
        with open('dsc_courses.json', 'r', encoding='utf-8') as f:
            courses = json.load(f)
        catalog_context = json.dumps(courses, ensure_ascii=False)

        # 调用 Gemini 2.0
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            config={
                "system_instruction": "You are a UCSD DSC Academic Advisor. Use the provided JSON to answer in English. Be concise."
            },
            contents=f"Catalog Data: {catalog_context}\n\nStudent Question: {user_question}"
        )
        return response.text
    except Exception as e:
        return f"❌ **AI Error**: {str(e)}"