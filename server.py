#!/usr/bin/env python3
"""WebSocket speech recognition server using Vosk + Ollama LLM."""
import json
import asyncio
from pathlib import Path

import aiohttp
from aiohttp import web
from vosk import Model, KaldiRecognizer, SetLogLevel

SetLogLevel(-1)

MODEL_PATH = str(Path(__file__).parent / "vosk-model-small-ja-0.22")
SAMPLE_RATE = 16000
STATIC_DIR = str(Path(__file__).parent)
OLLAMA_URL = "http://127.0.0.1:11434"
LLM_MODEL = "gemma3:1b"

print(f"Loading Vosk model from {MODEL_PATH}...")
model = Model(MODEL_PATH)
print("Model loaded.")


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    print("[WS] Client connected")

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


async def chat_handler(request):
    """POST /api/chat - Send user text to Ollama LLM, stream response."""
    body = await request.json()
    user_text = body.get("text", "")
    history = body.get("history", [])  # [{role, content}, ...]

    if not user_text:
        return web.json_response({"error": "no text"}, status=400)

    # Build messages for Ollama
    messages = [
        {"role": "system", "content": "あなたは親切で簡潔な日本語アシスタントです。ユーザーの音声入力に対して、分かりやすく回答してください。回答は200文字以内に収めてください。"}
    ]
    for h in history[-6:]:  # Keep last 6 turns
        messages.append(h)
    messages.append({"role": "user", "content": user_text})

    # Stream response from Ollama
    response = web.StreamResponse(
        headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"}
    )
    await response.prepare(request)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{OLLAMA_URL}/api/chat",
                json={"model": LLM_MODEL, "messages": messages, "stream": True},
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                async for line in resp.content:
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        done = chunk.get("done", False)
                        if content:
                            await response.write(
                                f"data: {json.dumps({'text': content, 'done': False})}\n\n".encode()
                            )
                        if done:
                            await response.write(
                                f"data: {json.dumps({'text': '', 'done': True})}\n\n".encode()
                            )
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        print(f"[LLM] Error: {e}")
        await response.write(
            f"data: {json.dumps({'text': f'エラー: {e}', 'done': True})}\n\n".encode()
        )

    await response.write_eof()
    return response


async def index_handler(request):
    return web.FileResponse(Path(STATIC_DIR) / "index.html")


app = web.Application()
app.router.add_get("/ws", websocket_handler)
app.router.add_post("/api/chat", chat_handler)
app.router.add_get("/", index_handler)
app.router.add_static("/static/", STATIC_DIR)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=8000)
