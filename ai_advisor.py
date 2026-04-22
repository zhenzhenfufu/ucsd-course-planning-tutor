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
        client = genai.Client(api_key=api_key)
        
        with open('dsc_courses.json', 'r', encoding='utf-8') as f:
            courses = json.load(f)
        catalog_context = json.dumps(courses, ensure_ascii=False)

        # 尝试使用最底层的全名标识符
        # 在 2026 年，如果 flash 报错，通常是因为区域权限问题
        # 我们这里改用 gemini-1.5-flash (不带任何后缀)
        response = client.models.generate_content(
            model="gemini-1.5-flash", 
            config={
                "system_instruction": "You are a UCSD DSC Advisor. Use the provided JSON to answer."
            },
            contents=f"Context: {catalog_context}\n\nQuestion: {user_question}"
        )
        return response.text

    except Exception as e:
        # 如果还是找不到，极大概率是你的 API Key 没开权限
        if "404" in str(e):
            return "❌ **API Permissions Error**: Your API Key is active, but Google Cloud has not enabled 'Gemini 1.5 Flash' for this specific key. \n\n**Please go to [AI Studio](https://aistudio.google.com/), create a NEW API KEY, and update it in Streamlit Secrets.**"
        return f"❌ **Error**: {str(e)}"