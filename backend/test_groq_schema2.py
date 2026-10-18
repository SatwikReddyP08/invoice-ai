import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
api_key = os.getenv("XAI_API_KEY")
client = Groq(api_key=api_key)

model = "qwen/qwen3.8-27b"

# Create a dummy image with some text so the model has something to describe
from PIL import Image, ImageDraw, ImageFont
import io
import base64
img = Image.new('RGB', (200, 100), color='white')
d = ImageDraw.Draw(img)
d.text((10,10), "Test Image", fill=(0,0,0))

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
    print("Testing JSON Schema again with better prompt...")
    res = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": [
                {"type": "text", "text": "Describe the image and return the output strictly matching the provided JSON schema, in JSON format. Provide the description in the 'text' field."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}}
            ]}
        ],
        response_format={"type": "json_schema", "json_schema": {"name": "test", "schema": schema, "strict": True}},
        max_tokens=50
    )
    print("Success:", res.choices[0].message.content)
except Exception as e:
    print("JSON Schema Failed:", str(e))
