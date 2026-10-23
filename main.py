from fastapi import FastAPI, Request
import requests

app = FastAPI()

@app.post("/sync")
async def sync_flashscore(request: Request):
    data = await request.json()
    url = "https://lsid.eu/v3/storemergeddata"
    headers = {
        "content-type": "application/json",
        "origin": "https://www.flashscore.com",
        "referer": "https://www.flashscore.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    try:
        res = requests.post(url, headers=headers, json=data, timeout=10)
        return {"status": res.status_code, "response": res.text}
    except Exception as e:
        return {"error": str(e)}

@app.get("/search")
def search_flashscore(q: str):
    url = f"https://search.flashscore.com/search/all?q={q}&l=1"
    headers = {"user-agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        return res.json()
    except Exception as e:
        return {"error": str(e)}
