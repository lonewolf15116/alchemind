import json
from app.llm.client import client


def run_alchemy(idea, mode):

    prompt = f"""
Return ONLY valid JSON in this format:

{{
  "idea": "{idea}",
  "mode": "{mode}",
  "intent": "build",
  "problem": "short explanation",
  "solution": "short explanation",
  "tech_stack": ["tool1", "tool2", "tool3"],
  "roadmap": ["step1", "step2", "step3"],
  "risks": ["risk1", "risk2"]
}}
"""

    response = client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )

    text = response.output_text.strip()

    try:
        return json.loads(text)
    except:
        return {
            "idea": idea,
            "mode": mode,
            "intent": "build",
            "problem": "AI formatting failed",
            "solution": "Retry request",
            "tech_stack": ["FastAPI", "OpenAI"],
            "roadmap": ["Retry"],
            "risks": ["Formatting error"]
        }