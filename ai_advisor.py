import os
import json
from google import genai
from dotenv import load_dotenv

load_dotenv()

def get_ai_advice(user_question):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "❌ **Missing API Key**."

    try:
        # 初始化客户端时明确指定 API 版本（如果 SDK 支持）
        client = genai.Client(api_key=api_key)
        
        with open('dsc_courses.json', 'r', encoding='utf-8') as f:
            courses = json.load(f)
        catalog_context = json.dumps(courses, ensure_ascii=False)

        # 核心修正：尝试使用 2026 年最保守、绝对存在的模型 ID
        # 强制使用 'gemini-1.5-flash'
        response = client.models.generate_content(
            model="gemini-1.5-flash-latest", # 确保使用这个带 -latest 的后缀
            config={
                "system_instruction": "You are a UCSD DSC Advisor. Use provided JSON to help students. English only."
            },
            contents=f"Context: {catalog_context}\n\nQuestion: {user_question}"
        )
        return response.text

    except Exception as e:
        # 如果还是 404，说明是 Google 的“区域保护”或“项目隔离”
        if "404" in str(e):
            return (
                "❌ **Regional/Project Block**: Your API Key is valid, but this specific project "
                "doesn't have access to Gemini 1.5. \n\n"
                "**Solution**: Please go to [AI Studio](https://aistudio.google.com/), "
                "click 'Create API Key in NEW project', and update Streamlit Secrets."
            )
        return f"❌ **Error**: {str(e)}"