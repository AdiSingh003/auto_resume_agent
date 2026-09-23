"""Quick API key validation test."""
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

print("=== API Key Validation ===\n")

# 1. Test Groq
print("[1] Testing Groq API (openai/gpt-oss-120b)...")
try:
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    resp = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": "Say hello in one word."}],
        max_tokens=10,
    )
    print(f"  OK: {resp.choices[0].message.content.strip()}")
except Exception as e:
    print(f"  FAIL: {e}")

# 2. Test Tavily
print("\n[2] Testing Tavily API...")
try:
    from tavily import TavilyClient
    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    resp = client.search("python programming", max_results=1)
    title = resp["results"][0]["title"] if resp.get("results") else "no results"
    print(f"  OK: Got result - {title[:80]}")
except Exception as e:
    print(f"  FAIL: {e}")

print("\n=== Done ===")
