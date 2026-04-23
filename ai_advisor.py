import os
import json
from google import genai
from dotenv import load_dotenv

load_dotenv()

def get_ai_advice(user_question):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "❌ **Missing API Key in .env file**."

    try:
        # 1. 初始化客户端
        client = genai.Client(api_key=api_key)
        
        # 2. 读取并定义 catalog_context (之前可能漏了这一步)
        with open('dsc_courses.json', 'r', encoding='utf-8') as f:
            courses = json.load(f)
        catalog_context = json.dumps(courses, ensure_ascii=False)

        # 3. 调用模型 (使用我们验证过的 flash 模型名)
        response = client.models.generate_content(
            model="gemini-flash-latest", # 如果还报 404，就试着改成 "gemini-flash-latest"
            config={
                "system_instruction": "You are a UCSD DSC Advisor. Use the provided course data to answer student questions accurately and concisely."
            },
            contents=f"Course Data: {catalog_context}\n\nStudent Question: {user_question}"
        )
        return response.text

    except Exception as e:
        # 打印到终端方便排查
        print(f"DEBUG: {str(e)}")
        return f"❌ **AI Error**: {str(e)}"