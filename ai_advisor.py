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
        # 初始化 2026 最新版客户端
        client = genai.Client(api_key=api_key)
        
        # 加载本地课程数据
        with open('dsc_courses.json', 'r', encoding='utf-8') as f:
            courses = json.load(f)
        catalog_context = json.dumps(courses, ensure_ascii=False)

        # 核心修复点：在 2026 版 SDK 中，直接使用字符串名称
        # 如果 1.5-flash 报错，请尝试使用 "gemini-1.5-flash-latest"
        response = client.models.generate_content(
            model="gemini-1.5-flash", 
            config={
                "system_instruction": "You are a UCSD DSC Advisor. Use JSON data to help students. Answer in English."
            },
            contents=f"Catalog: {catalog_context}\n\nQuestion: {user_question}"
        )
        
        return response.text

    except Exception as e:
        err_msg = str(e)
        # 针对 404 错误的特殊友好提示
        if "404" in err_msg:
            return "⚠️ **Model Version Error**: The AI studio version and SDK version are slightly out of sync. Please try changing the model string to 'gemini-1.5-flash-latest'."
        # 针对 429 频率限制的提示
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            return "⚠️ **Rate Limit**: Too many requests. Please wait 15 seconds."
        
        return f"❌ **AI Error**: {err_msg}"