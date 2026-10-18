import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
api_key = os.getenv("XAI_API_KEY")
client = Groq(api_key=api_key)

model = "qwen/qwen3.8-27b"

# Create a dummy image
from PIL import Image
import io
import base64
img = Image.new('RGB', (100, 100), color='white')
buffered = io.BytesIO()
img.save(buffered, format="JPEG")
img_str = base64.b64encode(buffered.getvalue()).decode()

schema = {
    "type": "object",
    "properties": {
        "text": {"type": "string"}
    },
    "required": ["text"],
    "additionalProperties": False
}

try:
    print("Testing JSON Schema...")
    res = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": [
                {"type": "text", "text": "Describe the image"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}}
            ]}
        ],
        response_format={"type": "json_schema", "json_schema": {"name": "test", "schema": schema, "strict": True}},
        max_tokens=50
    )
    print("Success:", res.choices[0].message.content)
except Exception as e:
    print("JSON Schema Failed:", str(e))

try:
    print("Testing JSON Object (JSON Mode)...")
    res = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": [
                {"type": "text", "text": "Describe the image in JSON format: {\"text\": \"description\"}"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}}
            ]}
        ],
        response_format={"type": "json_object"},
        max_tokens=50
    )
    print("Success:", res.choices[0].message.content)
except Exception as e:
    print("JSON Object Failed:", str(e))
