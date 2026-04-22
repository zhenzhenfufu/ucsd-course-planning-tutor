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
        # 初始化 2026 标准客户端
        client = genai.Client(api_key=api_key)
        
        # 加载数据
        with open('dsc_courses.json', 'r', encoding='utf-8') as f:
            courses = json.load(f)
        catalog_context = json.dumps(courses, ensure_ascii=False)

        # 强制切换到 2.0-flash，这是 2026 年新项目权限最高的模型
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            config={
                "system_instruction": "You are a UCSD DSC Advisor. Answer concisely based on JSON."
            },
            contents=f"Data: {catalog_context}\n\nUser Question: {user_question}"
        )
        return response.text

    except Exception as e:
        err_msg = str(e)
        # 如果 2.0 还是 Block，说明是 API Key 本身的激活状态问题
        if "404" in err_msg or "Regional" in err_msg:
            return (
                "❌ **Terminal Error**: Google is still blocking this Project/Key. \n\n"
                "**FINAL FIX**: Please go to [AI Studio](https://aistudio.google.com/), "
                "1. Click the **'Settings' (Gear icon)** at the bottom left. \n"
                "2. Ensure **'Generative Language API'** is toggled ON. \n"
                "3. Try one last time with a NEW key after this."
            )
        return f"❌ **Error**: {err_msg}"