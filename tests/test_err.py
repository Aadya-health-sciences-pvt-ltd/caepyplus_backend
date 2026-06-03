import sys
import json
import urllib.request
import urllib.error

def go():
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/api/v1/voice/start", headers={"Content-Type": "application/json"}, data=b"{}")
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read())
            print("START SUCCESS")
            
        session_id = data["session_id"]
        
        req2 = urllib.request.Request("http://127.0.0.1:8000/api/v1/voice/chat", headers={"Content-Type": "application/json"}, data=json.dumps({"session_id": session_id, "user_transcript": "hi"}).encode("utf-8"))
        with urllib.request.urlopen(req2) as res2:
            print("CHAT SUCCESS")
            print(res2.read())
            
    except urllib.error.HTTPError as e:
        print("HTTP ERROR:", e.code)
        print(e.read().decode("utf-8"))
    except Exception as e:
        print("OTHER ERROR:", e)

if __name__ == "__main__":
    go()
