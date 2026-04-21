import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

# Load API Key
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

def get_ai_advice(user_question):
    try:
        # Load the latest catalog
        with open('dsc_courses.json', 'r', encoding='utf-8') as f:
            courses = json.load(f)
        catalog_context = json.dumps(courses, ensure_ascii=False)

        # Using your specific model version
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        
        # Professional Advisor Persona
        prompt = f"""
        You are an elite Academic Advisor at UC San Diego (UCSD) for the Data Science (DSC) major.
        
        Your Instructions:
        1. Base your answers ONLY on the provided JSON data.
        2. Format: Use bullet points for course lists.
        3. Tone: Professional, helpful, and concise.
        4. Language: English.
        5. Data Reference:
           - 'id': Course Code
           - 'name': Full Title
           - 'description': Content & Prerequisites

        Context Catalog Data:
        {catalog_context}
        
        Student's Question:
        {user_question}
        """

        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        if "429" in str(e):
            return "⚠️ **Rate Limit Reached**: The AI needs a 30-second break. Please retry shortly."
        return f"❌ **System Error**: {str(e)}"