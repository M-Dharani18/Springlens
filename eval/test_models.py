import os
from langchain_google_genai import ChatGoogleGenerativeAI

os.chdir(os.path.dirname(os.path.abspath(__file__)))
key = os.environ.get("GOOGLE_API_KEY", "")

candidates = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite",
]

print("=== TESTING GEMINI 3.x MODEL NAMES ===")
for model in candidates:
    try:
        llm = ChatGoogleGenerativeAI(model=model, google_api_key=key, temperature=0)
        res = llm.invoke("Hi, answer with one word 'OK'")
        print(f"SUCCESS: {model:<25} -> {res.content.strip()}")
    except Exception as e:
        err = str(e).split("\n")[0]
        print(f"FAILED:  {model:<25} -> {err}")
