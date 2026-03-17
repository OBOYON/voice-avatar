#!/usr/bin/env python3
"""WebSocket speech recognition server using Vosk."""
import json
import asyncio
from pathlib import Path

from aiohttp import web
from vosk import Model, KaldiRecognizer, SetLogLevel

SetLogLevel(-1)  # suppress vosk logs

MODEL_PATH = str(Path(__file__).parent / "vosk-model-small-ja-0.22")
SAMPLE_RATE = 16000
STATIC_DIR = str(Path(__file__).parent)

print(f"Loading Vosk model from {MODEL_PATH}...")
model = Model(MODEL_PATH)
print("Model loaded.")


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    print("[WS] Client connected")

    # Get language from query string (unused by vosk-small-ja, but for future)
    lang = request.query.get("lang", "ja-JP")
    rec = KaldiRecognizer(model, SAMPLE_RATE)
    rec.SetWords(True)

    async for msg in ws:
        if msg.type == web.WSMsgType.BINARY:
            if rec.AcceptWaveform(msg.data):
                result = json.loads(rec.Result())
                text = result.get("text", "")
                if text:
                    await ws.send_json({"type": "final", "text": text})
            else:
                partial = json.loads(rec.PartialResult())
                text = partial.get("partial", "")
                if text:
                    await ws.send_json({"type": "partial", "text": text})
        elif msg.type == web.WSMsgType.TEXT:
            data = json.loads(msg.data)
            if data.get("command") == "eof":
                final = json.loads(rec.FinalResult())
                text = final.get("text", "")
                if text:
                    await ws.send_json({"type": "final", "text": text})
                rec = KaldiRecognizer(model, SAMPLE_RATE)
                rec.SetWords(True)
        elif msg.type in (web.WSMsgType.ERROR, web.WSMsgType.CLOSE):
            break

    print("[WS] Client disconnected")
    return ws


async def index_handler(request):
    return web.FileResponse(Path(STATIC_DIR) / "index.html")

app = web.Application()
app.router.add_get("/ws", websocket_handler)
app.router.add_get("/", index_handler)
# Serve other static files
app.router.add_static("/static/", STATIC_DIR)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=8000)
