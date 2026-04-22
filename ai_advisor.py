import os
import json
# 放弃 from google import genai，改用这种直接路径
try:
    from google.genai import Client
except ImportError:
    # 兼容某些环境下的特殊路径
    import google.genai as genai
    Client = genai.Client

from dotenv import load_dotenv

load_dotenv()

# 初始化 Client
client = Client(api_key=os.getenv("GEMINI_API_KEY"))

def get_ai_advice(user_question):
    try:
        with open('dsc_courses.json', 'r', encoding='utf-8') as f:
            courses = json.load(f)
        catalog_context = json.dumps(courses, ensure_ascii=False)

        # 逻辑保持不变
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            config={
                "system_instruction": "You are a UCSD Data Science Academic Advisor. Answer in English based on the catalog."
            },
            contents=f"Catalog Data: {catalog_context}\n\nStudent Question: {user_question}"
        )
        return response.text
    except Exception as e:
        return f"❌ AI Error: {str(e)}"