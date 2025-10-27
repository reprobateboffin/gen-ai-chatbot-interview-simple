import google.generativeai as genai
from dotenv import load_dotenv
import os

load_dotenv()
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
gemini_api_key = GEMINI_API_KEY

genai.configure(api_key=gemini_api_key)
GeminiModel = genai.GenerativeModel("gemini-2.5-flash")
