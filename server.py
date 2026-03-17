#!/usr/bin/env python3
"""WebSocket speech recognition server using Vosk + Ollama LLM + Edge-TTS."""
import json
import asyncio
import io
import hashlib
import os
from pathlib import Path

import aiohttp
import edge_tts
from aiohttp import web
from vosk import Model, KaldiRecognizer, SetLogLevel

# TTS cache dir
TTS_CACHE = Path(__file__).parent / ".tts_cache"
TTS_CACHE.mkdir(exist_ok=True)
TTS_VOICE = "ja-JP-NanamiNeural"  # Female, friendly

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
        {"role": "system", "content": """あなたは『ハムちゃん』という可愛いハムスターのAI。
以下のように話してください:

質問: 今日の天気はどう？
回答: 今日はお天気がいいみたいだよ。お散歩日和だね。ハムちゃんもお外で遊びたいな〜

質問: 眠れない時はどうすればいい？
回答: 眠れない時は、温かいミルクを飲むといいよ。ハムちゃんはふわふわの毛布にくるまるのが好きなの

質問: 元気になる方法を教えて
回答: おいしいものを食べて、たくさん遊ぶと元気になるよ。ハムちゃんは回し車で遊ぶとすごく元気になるの

ルール: 日本語のみ。絵文字禁止。記号装飾禁止。50文字くらいで短く答えて。"""}
    ]
    for h in history[-4:]:  # Keep last 4 turns
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


async def tts_handler(request):
    """POST /api/tts - Convert text to speech using edge-tts."""
    body = await request.json()
    text = body.get("text", "").strip()
    voice = body.get("voice", TTS_VOICE)

    if not text:
        return web.json_response({"error": "no text"}, status=400)

    # Cache by text+voice hash
    key = hashlib.md5(f"{voice}:{text}".encode()).hexdigest()
    cached = TTS_CACHE / f"{key}.mp3"

    if not cached.exists():
        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(cached))
            print(f"[TTS] Generated: {text[:40]}...")
        except Exception as e:
            print(f"[TTS] Error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    return web.FileResponse(cached, headers={"Content-Type": "audio/mpeg"})


async def tts_voices_handler(request):
    """GET /api/tts/voices - List available Japanese voices."""
    voices = await edge_tts.list_voices()
    ja_voices = [v for v in voices if v["Locale"].startswith("ja-JP")]
    return web.json_response(ja_voices)


async def index_handler(request):
    return web.FileResponse(Path(STATIC_DIR) / "index.html")


app = web.Application()
app.router.add_get("/ws", websocket_handler)
app.router.add_post("/api/chat", chat_handler)
app.router.add_post("/api/tts", tts_handler)
app.router.add_get("/api/tts/voices", tts_voices_handler)
app.router.add_get("/", index_handler)
app.router.add_static("/static/", STATIC_DIR)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=8000)
