import base64, json, os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

token = os.getenv("OPENAI_API_KEY", "")
parts = token.split(".")
if len(parts) == 3:
    payload = parts[1]
    payload += "=" * (4 - len(payload) % 4)
    d = json.loads(base64.urlsafe_b64decode(payload))
    exp = datetime.fromtimestamp(d["exp"])
    iat = datetime.fromtimestamp(d["iat"])
    upn = d.get("upn", "unknown")
    print(f"User: {upn}")
    print(f"Issued:  {iat}")
    print(f"Expires: {exp}")
    print(f"Now:     {datetime.now()}")
    print(f"EXPIRED: {datetime.now() > exp}")
    print(f"Token lifetime: {exp - iat}")
else:
    print("Not a JWT token")
