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
        
        # 加载本地课程 JSON
        with open('dsc_courses.json', 'r', encoding='utf-8') as f:
            courses = json.load(f)
        catalog_context = json.dumps(courses, ensure_ascii=False)

        # 2026 终极兼容名称：使用 "gemini-1.5-flash"
        # 绝不加 "models/" 前缀，绝不加其它后缀
        response = client.models.generate_content(
            model="gemini-1.5-flash", 
            config={
                "system_instruction": (
                    "You are the official UCSD Data Science Academic Advisor. "
                    "Provide helpful, concise course planning advice based on the JSON catalog provided. "
                    "Always respond in English."
                )
            },
            contents=f"Context: {catalog_context}\n\nStudent Inquiry: {user_question}"
        )
        
        return response.text

    except Exception as e:
        err_msg = str(e)
        # 深度清理 404 逻辑：如果是找不到模型，尝试提示最原始的版本
        if "404" in err_msg:
            return f"❌ **Model Discovery Error**: Google is not recognizing the model name. Current attempt: 'gemini-1.5-flash'. Technical detail: {err_msg[:100]}"
        
        # 针对 429 频率限制
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            return "⚠️ **Rate Limit**: The free tier is exhausted. Please wait 30-60 seconds."
        
        return f"❌ **AI Error**: {err_msg}"