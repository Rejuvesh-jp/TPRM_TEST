import os
from dotenv import load_dotenv
from openai import OpenAI
import httpx

from services.embedding_service import openai_embed_text
 
load_dotenv()
 
 
OPEN_AI_API_KEY = os.getenv("OPEN_AI_API_KEY_GATEWAY")
 
KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IlFaZ045SHFOa0dORU00R2VLY3pEMDJQY1Z2NCIsImtpZCI6IlFaZ045SHFOa0dORU00R2VLY3pEMDJQY1Z2NCJ9.eyJhdWQiOiJhcGk6Ly80NmVjZWEzYy05MTU4LTQwM2QtYmJjMS0xNTExNTdlMTgyZWEiLCJpc3MiOiJodHRwczovL3N0cy53aW5kb3dzLm5ldC83Y2M5MWMzOC02NDhlLTRjZTItYTRlNC01MTdhZTM5ZmMxODkvIiwiaWF0IjoxNzczMjI0Njg2LCJuYmYiOjE3NzMyMjQ2ODYsImV4cCI6MTc3MzIyODg4MCwiYWNyIjoiMSIsImFpbyI6IkFhUUFXLzhiQUFBQVBHajV1WlFwN21JMlQ2Vm5FQjhId3NIN2l6TnAvaWhJemNOV005NGplaXJuL3BMVkd6bHJtZnRKRTYyaXBoc3JhZkZNVDFvRm1kTG5lTEpxOHBxeTFaanZ4SmpEMHNMNFg4aDlKVmU3N1JBYUkyMzQ2KzZKcDVSemdLVEM4Qkcvb1MyalZiL0VUcEl6Y3BhbVV0WTF1OWVpMEpIZ3NmZjhiZSt2WjdJczYrZ2xWMnEyRURYV0xkeWxqL20wK0s2OWJRUFBrSnRLOGk4aDhyWE1mME50Nmc9PSIsImFtciI6WyJwd2QiLCJyc2EiLCJtZmEiXSwiYXBwaWQiOiJiNzRjNmJiMC0zOTk2LTQ1ZTItYTg2NC01OWZiNTdiZTU0ZGEiLCJhcHBpZGFjciI6IjEiLCJkZXZpY2VpZCI6IjUyZTcyMjUzLTQ4MjAtNDEyMS1hYjg4LWFlOGE3OTQyM2Y2MiIsImZhbWlseV9uYW1lIjoiLiIsImdpdmVuX25hbWUiOiJDIEcgSGFyc2hhdmFyZGhhbiIsImlwYWRkciI6IjE2Ny4xMDMuNzQuMTEwIiwibmFtZSI6IkMgRyBIYXJzaGF2YXJkaGFuIC4iLCJvaWQiOiJjOWM2NDYzMC1jYmQ5LTQ1ZWQtOGY5YS1iNDdjYTk0NmJkNzciLCJvbnByZW1fc2lkIjoiUy0xLTUtMjEtMTA1Njg2MzYzMi04NjQ3MTE4MS0xODQ5NjAxMTMtMTA5NzIxIiwicmgiOiIxLkFWWUFPQnpKZkk1azRreWs1RkY2NDVfQmlUenE3RVpZa1QxQXU4RVZFVmZoZ3VvQUFIbFdBQS4iLCJzY3AiOiJhY2Nlc3NfYXNfdXNlciIsInNpZCI6IjAwMWVkYThhLTViNWEtZWIzNy02ZTUwLWQzYjRkZTBjMjQ5ZSIsInN1YiI6Im5MX016Q2d6X1VmQUdqeVlUMU10N3pJb2NsV1VmN0RqUllBbllmdEx1OGMiLCJ0aWQiOiI3Y2M5MWMzOC02NDhlLTRjZTItYTRlNC01MTdhZTM5ZmMxODkiLCJ1bmlxdWVfbmFtZSI6ImNnaGFyc2hhdmFyZGhhbkB0aXRhbi5jby5pbiIsInVwbiI6ImNnaGFyc2hhdmFyZGhhbkB0aXRhbi5jby5pbiIsInV0aSI6ImhpYVRIR0s0cTBtM24xZGR1WVVKQUEiLCJ2ZXIiOiIxLjAiLCJ4bXNfZnRkIjoiN19DN3AzQWY3bThmQXN1dllSMVRVZ0puV1RqVkZjRENaVTIycGZyM1R3RUJZWE5wWVhOdmRYUm9aV0Z6ZEMxa2MyMXoifQ.ZejmTsefmA6icHV8EfABUkEUg6rKBplWdIPuAQhUUl8ktzg3oX6erU_b2EJoIuOaY9ZUreJFobjznSdqRaBXg29_O2_s4Ly4KQjHZRKb_RACeh0F2LuroAHNV45h0WW1nttiqb-B5jVAMUCYavYRCTX0aDpxPrpp7ab80DWYutvrKa0m4qiYHtXy2J23ozu98xARr_8Se-b42rdQl9imNjhWazlltWxnggv6QKY5v21hAf7-11iHsEuOhJxmmow3e3a2nnY1CwG_zavXRnsMW57H4iHeKV6DcYuieNGGWYUB5XfOQycUSbSEktvcKecfj0qHISsPiluvKqMKpOI8ow"
 
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