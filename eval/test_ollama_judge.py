import json
import urllib.request

url = "http://localhost:11434/api/generate"
payload = {
    "model": "llama3.1:8b",
    "prompt": "Respond ONLY with a JSON object: {\"status\": \"ok\"}",
    "stream": False,
    "format": "json"
}

req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        print("Ollama llama3.1:8b output:", res.get("response"))
except Exception as e:
    print("Ollama test failed:", e)
