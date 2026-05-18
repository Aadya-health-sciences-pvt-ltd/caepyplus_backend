import asyncio
import httpx
import json

async def test_backend():
    with open("test_endpoint_out.txt", "w") as f:
        async with httpx.AsyncClient() as client:
            f.write("1. Starting session...\n")
            res1 = await client.post("http://localhost:8000/caepy/api/v1/voice/start", json={"language": "en"})
            f.write(f"Status: {res1.status_code}\n")
            
            if res1.status_code != 201:
                f.write(res1.text + "\n")
                return
                
            data = res1.json()
            session_id = data["session_id"]
            f.write(f"Session started: {session_id}\n")
            f.write(f"Greeting: {data['greeting']}\n")
            
            f.write("\n2. Sending chat message...\n")
            res2 = await client.post("http://localhost:8000/caepy/api/v1/voice/chat", json={
                "session_id": session_id,
                "user_transcript": "My name is Dr. Sarah Johnson and I specialize in Cardiology. I have 5 years of experience."
            }, timeout=30.0)
            
            f.write(f"Chat Status: {res2.status_code}\n")
            if res2.status_code != 200:
                f.write(f"Error Body: {res2.text}\n")
            else:
                f.write(f"Response: {json.dumps(res2.json(), indent=2)}\n")

if __name__ == "__main__":
    asyncio.run(test_backend())
