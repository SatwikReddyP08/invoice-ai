import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
# Read from XAI_API_KEY since it's temporarily misnamed
api_key = os.getenv("XAI_API_KEY")
client = Groq(api_key=api_key)

models = client.models.list()
print("Available models:")
for m in models.data:
    if "vision" in m.id.lower() or "llava" in m.id.lower() or "llama-3.2" in m.id.lower() or "qwen" in m.id.lower():
        print(f"- {m.id}")
