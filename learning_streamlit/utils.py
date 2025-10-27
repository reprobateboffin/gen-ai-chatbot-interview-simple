from gemini_client import gemini_client


def safe_generate(prompt: str, fallback: str, gemini_client=gemini_client) -> str:
    try:
        return gemini_client.generate_content(prompt) or fallback
    except Exception as e:
        return fallback
