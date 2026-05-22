import os
import json
import urllib.request
import urllib.error
from dotenv import load_dotenv

# Load env from workspace
load_dotenv(dotenv_path=r"c:\Users\SOFT\OneDrive\Desktop\discordbolt\.env")

def test():
    gemini_key = os.getenv("GEMINI_API_KEY")
    print(f"API Key: {gemini_key}")
    if not gemini_key:
        print("No API Key found!")
        return

    payload = {
        "contents": [{"role": "user", "parts": [{"text": "Hello, roast me"}]}],
        "systemInstruction": {
            "parts": [{"text": "You are a witty, highly sarcastic Discord bot."}]
        }
    }
    data = json.dumps(payload).encode("utf-8")
    
    # Test v1 with systemInstruction
    url_v1 = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={gemini_key}"
    req_v1 = urllib.request.Request(
        url_v1,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    print("Testing v1 with systemInstruction...")
    try:
        with urllib.request.urlopen(req_v1) as response:
            print(f"v1 status: {response.status}")
            print(f"v1 response: {response.read().decode('utf-8')}")
    except urllib.error.HTTPError as e:
        print(f"v1 failed with status: {e.code}")
        print(f"v1 error response: {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"v1 exception: {e}")

if __name__ == "__main__":
    test()
