import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
api_key = os.getenv("XAI_API_KEY")
client = Groq(api_key=api_key)

models = client.models.list()
print("All available models:")
for m in models.data:
    print(f"- {m.id}")
