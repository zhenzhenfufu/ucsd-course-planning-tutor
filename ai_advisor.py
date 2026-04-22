import os
import json
from google import genai
from dotenv import load_dotenv

load_dotenv()

def get_ai_advice(user_question):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "❌ **Missing API Key**: Set GEMINI_API_KEY in Secrets."

    try:
        # 初始化客户端
        client = genai.Client(api_key=api_key)
        
        # 加载本地课程数据
        with open('dsc_courses.json', 'r', encoding='utf-8') as f:
            courses = json.load(f)
        catalog_context = json.dumps(courses, ensure_ascii=False)

        # 核心修复：使用 1.5-flash-latest 或 1.5-flash
        # 注意：不要加 models/ 前缀，SDK 会自动处理
        response = client.models.generate_content(
            model="gemini-1.5-flash-latest", 
            config={
                "system_instruction": (
                    "You are the official UCSD Data Science Academic Advisor. "
                    "Use the provided JSON catalog to help students plan schedules. "
                    "Answer in English, be professional and concise."
                )
            },
            contents=f"Catalog Data: {catalog_context}\n\nStudent Inquiry: {user_question}"
        )
        
        return response.text

    except Exception as e:
        err_msg = str(e)
        # 如果最新版还是找不到，尝试降级到基础 flash 版本
        if "404" in err_msg:
            return "⚠️ **Model Mapping Error**: Please try 'gemini-1.5-flash' as the model string."
        if "429" in err_msg:
            return "⚠️ **Rate Limit**: Google's free tier is busy. Wait 15s."
        
        return f"❌ **AI Error**: {err_msg}"