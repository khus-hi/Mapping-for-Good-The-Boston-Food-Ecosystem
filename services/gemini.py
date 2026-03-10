import json
import os
import re

try:
    import google.generativeai as genai
except ImportError:
    genai = None

_model = None

VALID_PLACE_TYPES = {"farmers_market", "restaurant", "grocery_store", "food_pantry"}


def _get_model():
    global _model
    if _model is None:
        if genai is None:
            raise RuntimeError("google-generativeai is not installed")
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        genai.configure(api_key=api_key)
        _model = genai.GenerativeModel("gemini-2.5-flash")
    return _model


def ask(prompt: str) -> str:
    model = _get_model()
    response = model.generate_content(prompt)
    return response.text


def parse_search_query(query: str) -> dict:
    prompt = f"""You are a search parser for a Boston food access map.
Extract structured search intent from the user's query.

Respond with ONLY a valid JSON object — no explanation, no markdown, no extra text.

JSON fields:
- "place_type": one of "farmers_market", "restaurant", "grocery_store", "food_pantry", or null
- "neighborhood": a Boston neighborhood name string, or null
- "address": a specific street address if mentioned, or null

User query: {query}

JSON:"""
    raw = ask(prompt).strip()
    # Strip markdown code fences if Gemini wraps the response
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    raw = raw.strip()
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"place_type": None, "neighborhood": None, "address": None}
    place_type = result.get("place_type")
    if place_type not in VALID_PLACE_TYPES:
        place_type = None
    return {
        "place_type": place_type,
        "neighborhood": result.get("neighborhood") or None,
        "address": result.get("address") or None,
    }


def ask_about_neighborhood(neighborhood: str, context: dict) -> str:
    prompt = f"""
You are an assistant helping users understand food access and income inequality in Boston neighborhoods.

Neighborhood: {neighborhood}
Income Inequality (Gini Index): {context.get('gini', 'unknown')}
Nearby Farmers Markets: {context.get('markets', [])}

Give a brief, helpful 2-3 sentence summary about food equity in this neighborhood based on the data above.
"""
    return ask(prompt)
