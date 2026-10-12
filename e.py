import os
from dotenv import load_dotenv
from openai import OpenAI
import httpx

from services.embedding_service import openai_embed_text
 
load_dotenv()
 
 
OPEN_AI_API_KEY = os.getenv("OPEN_AI_API_KEY_GATEWAY")
 

 
client = OpenAI(api_key=KEY, http_client=httpx.Client(verify=False), base_url="https://ai.titan.in/gateway")
 
# response = client.responses.create(
#     model="azure/gpt-4o",
#     input="Tell me a three sentence bedtime story about a unicorn.",
# )
 
# print(response)
 
# embeds = client.embeddings.create(model="azure/text-embedding-3-small",
#     input="Tell me a three sentence bedtime story about a unicorn.",
#                                   )
 
# print(embeds)
 
# models = client.models.list()
 
# for model in models.data:
#     print(model.id)
 
try:
    res = openai_embed_text(client=client, text="Tell me a three sentence bedtime story about a unicorn.")
    print(res)

except Exception as e:
    print("Error during embedding:", str(e))
