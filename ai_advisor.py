import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from prereq_graph import build as build_graph
from retrieval import context_for, get_index

load_dotenv(Path(__file__).with_name(".env"))

# Built once per process: parsing the catalog and loading the cached vectors
# is cheap, but not per-keystroke cheap.
_CG = None
_INDEX = None


def _resources():
    global _CG, _INDEX
    if _CG is None:
        _CG = build_graph()
        _INDEX = get_index(_CG)
    return _CG, _INDEX

SYSTEM_PROMPT = """You are an expert UCSD Data Science (DSC) academic advisor with deep knowledge of the program's curriculum, prerequisites, and course difficulty.

Your role is to help students:
- Plan their academic path through the DSC major
- Understand prerequisites and course sequencing
- Assess workload using the stats data (Hours/Week, Assignment Load, Content Difficulty)
- Make informed decisions about course selection based on their goals
- Understand GPA trends and exam difficulty

When giving advice:
- Be direct and specific, referencing course codes (e.g., DSC 40A, DSC 100)
- Flag when a planned schedule looks heavy (>16 units or high total weekly hours)
- Recommend prerequisite courses when students seem underprepared
- Only cite prerequisites that appear in the RELEVANT COURSES rows; if a course
  you want to mention is not listed there, say you would need to look it up
  rather than guessing its prerequisites
- Keep responses concise but complete
- Use markdown formatting: **bold** for course names, bullet points for lists"""

# Try models from most to least quota-generous on the free tier
MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
]


def get_ai_advice(conversation_history, selected_courses=None, courses_data=None):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "❌ **Missing API Key** — add `GEMINI_API_KEY` to your `.env` file."
    if not conversation_history:
        return "❌ No message to respond to."

    cg, index = _resources()
    # Retrieve rows for the live question instead of pasting the whole
    # catalog; graph expansion then guarantees the prerequisites of anything
    # retrieved are present, which is what the model actually gets wrong.
    question = conversation_history[-1]["content"]
    catalog_json = context_for(question, index, k=10,
                               extra=list(selected_courses or []), cg=cg, hops=1)
    plan_str = (
        f"Student's current planned courses: {selected_courses}"
        if selected_courses else "No courses selected yet."
    )

    contents = []
    for i, msg in enumerate(conversation_history):
        role = "user" if msg["role"] == "user" else "model"
        content = msg["content"]
        if role == "user":
            if i == 0:
                content = (
                    f"[RELEVANT COURSES]:\n{catalog_json}\n\n"
                    f"[{plan_str}]\n\n"
                    f"[STUDENT QUESTION]: {content}"
                )
            elif i == len(conversation_history) - 1:
                content = (f"[RELEVANT COURSES]:\n{catalog_json}\n\n"
                           f"[{plan_str}]\n\n{content}")
            else:
                content = f"[{plan_str}]\n\n{content}"
        contents.append({"role": role, "parts": [{"text": content}]})

    client = genai.Client(api_key=api_key)
    last_error = ""

    for model in MODELS:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    config={
                        "system_instruction": SYSTEM_PROMPT,
                        "temperature": 0.5,
                        "max_output_tokens": 800,
                    },
                    contents=contents,
                )
                return response.text
            except Exception as e:
                last_error = str(e)
                if "429" in last_error or "RESOURCE_EXHAUSTED" in last_error:
                    if attempt == 0:
                        time.sleep(15)
                        continue
                    break  # try next model
                # non-quota error — don't retry
                print(f"DEBUG AI Error ({model}): {last_error}")
                return f"❌ **AI Error**: {last_error}"

    return (
        "⏳ **Daily quota reached** — All Gemini free-tier models are at their limit. "
        "This resets at midnight Pacific Time. Try again later, or ask your question directly in the catalog."
    )
