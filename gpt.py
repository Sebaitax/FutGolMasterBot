import os
from openai import OpenAI

client = OpenAI(
    base_url="https://api.aimlapi.com/v1",

    # Insert your AIML API Key in the quotation marks instead of <YOUR_API_KEY>.
    api_key="",  
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {
            "role": "system",
            "content": "Eres una ia buena onda",
        },
        {
            "role": "user",
            "content": "en que año mi pobre angelito quedo solito en casa"
        },
    ],
)

message = response.choices[0].message.content

print(f"Assistant: {message}")