import os
import json
from google import genai
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 初始化新版 Client
# 注意：在 Streamlit Cloud 的 Secrets 里确保 GEMINI_API_KEY 已配置
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def get_ai_advice(user_question):
    try:
        # 读取课程数据
        with open('dsc_courses.json', 'r', encoding='utf-8') as f:
            courses = json.load(f)
        catalog_context = json.dumps(courses, ensure_ascii=False)

        # 调用 2026 稳定版模型
        # 我们把身份设定直接放入 system_instruction，这样 AI 反应更快且更守规矩
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            config={
                "system_instruction": (
                    "You are an elite Academic Advisor at UC San Diego (UCSD) for the Data Science (DSC) major. "
                    "Rule 1: Base your answers ONLY on the provided JSON data.\n"
                    "Rule 2: Format using bullet points for lists.\n"
                    "Rule 3: Answer in English.\n"
                    "Data Reference: 'id' is Course Code, 'name' is Title, 'description' is Content."
                )
            },
            contents=f"Catalog Data: {catalog_context}\n\nStudent's Question: {user_question}"
        )

        return response.text

    except Exception as e:
        # 处理频率限制 (Rate Limit)
        if "429" in str(e):
            return "⚠️ **Advisor Note**: I'm receiving too many requests right now. Please wait 30 seconds."
        return f"❌ **System Error**: {str(e)}"