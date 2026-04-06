import json
from app.llm.client import client


def run_alchemy(idea: str, mode: str):
    prompt = f"""
You are Alchemind, an elite AI product strategist and systems architect.

Transform the user's idea into a COMPLETE, structured, execution-ready product plan.

Idea: {idea}
Mode: {mode}

Return ONLY valid JSON with EXACTLY these fields:

- problem (string)
- solution (string)

- differentiation (array of strings)
- success_metrics (array of measurable KPIs as strings)
- monetization (array of revenue strategies)

- go_to_market (array of clear distribution and sales strategies)

- tech_stack (array of technologies)

- roadmap (array of OBJECTS with EXACT structure:
    {{
      "phase": string,
      "duration": string,
      "deliverables": array of strings
    }}
)

- architecture (string explaining system flow like:
  "User → Frontend → API → Services → DB → Response")

- risks (array of strings)

STRICT RULES:

1. DO NOT return roadmap as plain text → MUST be structured objects
2. DO NOT include markdown, explanations, or comments
3. DO NOT return nested unknown structures
4. Keep everything clean, realistic, and execution-focused
5. Use industry-aware thinking (not generic startup fluff)
6. Ensure JSON is valid and parsable

Return ONLY JSON.
"""

    response = client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )

    text = response.output_text.strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # fallback safety
        result = {
            "problem": "Failed to parse model output",
            "solution": text,
            "differentiation": [],
            "success_metrics": [],
            "monetization": [],
            "tech_stack": [],
            "roadmap": [],
            "risks": []
        }

    return result