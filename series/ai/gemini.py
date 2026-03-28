from os import getenv

from google import genai

EMBEDDING_DIMENSIONS = 1536

client = genai.Client(api_key=getenv("GOOGLE_API_KEY", default="GOOGLE_API_KEY"))
embedding_model = "models/gemini-embedding-001"
generation_model = "models/gemini-2.5-flash-lite"
