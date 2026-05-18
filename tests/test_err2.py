import sys
import urllib.request
import json

try:
    req = urllib.request.Request("http://127.0.0.1:8000/api/v1/voice/start", headers={"Content-Type": "application/json"}, method="POST", data=b"{}")
    with urllib.request.urlopen(req) as res:
        data = json.loads(res.read())
        print("START SUCCESS", data["session_id"])
        sys.stdout.flush()
        
    req2 = urllib.request.Request("http://127.0.0.1:8000/api/v1/voice/chat", headers={"Content-Type": "application/json"}, method="POST", data=json.dumps({"session_id": data["session_id"], "user_transcript": "hi"}).encode("utf-8"))
    with urllib.request.urlopen(req2) as res2:
        print("CHAT SUCCESS", res2.read())
        sys.stdout.flush()
except Exception as e:
    print("ERROR", str(e))
    if hasattr(e, 'read'):
        print(e.read().decode())
    sys.stdout.flush()
