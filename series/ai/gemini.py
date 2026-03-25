from os import getenv

from google import genai

client = genai.Client(api_key=getenv("GOOGLE_API_KEY"))
embedding_model = "text-embedding-004"
generation_model = "gemini-2.5-flash"
