#!/usr/bin/env python3
"""
Debug script to test cookie handling
"""

from fastapi import FastAPI, Request

app = FastAPI()

@app.get("/test-cookie")
async def test_cookie(request: Request):
    """Test cookie parsing"""
    cookies = dict(request.cookies)
    session_token = request.cookies.get("session_token")
    
    return {
        "all_cookies": cookies,
        "session_token": session_token,
        "headers": dict(request.headers)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8086)