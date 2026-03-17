# 🐹 ハムスターAI（Voice Avatar）

ブラウザのマイクで日本語を話しかけると、可愛いハムスターのAIキャラクター「ハムちゃん」がリアルタイムで音声認識し、質問には音声付きで返答してくれるWebアプリです。

![ハムスターAI](https://img.shields.io/badge/AI-ハムちゃん-pink) ![Python](https://img.shields.io/badge/Python-3.12-blue) ![License](https://img.shields.io/badge/license-MIT-green)

## デモ

https://cloud-canyon.exe.xyz:8000/

## 特徴

- **リアルタイム音声認識** — ブラウザのマイクからサーバーサイドのVoskで日本語音声認識（iOS Safari対応）
- **AIチャット応答** — 質問や相談を検知すると、Ollama（gemma3:1b）でハムスター人格の回答を生成
- **高品質音声合成** — Edge-TTS（ja-JP-NanamiNeural）で自然な日本語音声を生成・再生
- **リップシンク** — AI音声再生中にアバターの口がAudioContext Analyserで音声に同期
- **可愛いアバター** — SVGハムスターアバター（表情変化: 嬉しい/驚き/通常）
- **パステルテーマ** — ピンク〜パープル〜ブルーのグラデーション背景
- **iOS対応** — AudioContext自動解除、サイレントバッファトリック、タッチ操作対応

## アーキテクチャ

```
┌─────────────────────────────────────────────────┐
│  ブラウザ (index.html)                           │
│                                                  │
│  マイク → MediaRecorder → PCM 16kHz Int16        │
│       ↓ WebSocket                                │
│  認識テキスト表示 ← JSON結果                      │
│       ↓ 質問検知 (isQuestion)                     │
│  POST /api/chat → SSEストリーム → テキスト表示     │
│       ↓                                          │
│  POST /api/tts → MP3 → AudioBufferSource再生     │
│       ↓                                          │
│  AudioContext Analyser → リップシンク              │
└──────────────┬──────────────────────────────────┘
               │ WebSocket / HTTP
┌──────────────▼──────────────────────────────────┐
│  サーバー (server.py - aiohttp)                   │
│                                                  │
│  /ws          → Vosk音声認識 (KaldiRecognizer)    │
│  /api/chat    → Ollama LLM (gemma3:1b) SSE       │
│  /api/tts     → Edge-TTS (NanamiNeural) MP3      │
│  /            → index.html 配信                   │
└──────────────────────────────────────────────────┘
```

## 技術スタック

| カテゴリ | 技術 | 説明 |
|---------|------|------|
| フロントエンド | HTML/CSS/JS (単一ファイル) | index.html にすべて含む |
| バックエンド | Python 3.12 + aiohttp | WebSocket＆HTTPサーバー |
| 音声認識 | Vosk (vosk-model-small-ja-0.22) | サーバーサイドで日本語認識 |
| LLM | Ollama + gemma3:1b | CPU動作の軽量LLM |
| 音声合成 | Edge-TTS (ja-JP-NanamiNeural) | Microsoft製高品質日本語音声 |
| アバター | SVG (インライン) | ハムスター、表情変化付き |

## APIエンドポイント

### `GET /ws` — WebSocket音声認識
ブラウザからPCM音声データ（16kHz, Int16, モノラル）をバイナリフレームで送信。

**受信メッセージ:**
```json
{"type": "final", "text": "認識されたテキスト"}
{"type": "partial", "text": "認識中のテキスト"}
```

**送信コマンド:**
```json
{"command": "eof"}  // 認識セッション終了
```

### `POST /api/chat` — AIチャット
**リクエスト:**
```json
{
  "text": "ユーザーの質問",
  "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
}
```

**レスポンス:** SSE (Server-Sent Events)
```
data: {"text": "応答テキストの断片", "done": false}
data: {"text": "", "done": true}
```

### `POST /api/tts` — 音声合成
**リクエスト:**
```json
{"text": "読み上げるテキスト", "voice": "ja-JP-NanamiNeural"}
```

**レスポンス:** `audio/mpeg` (MP3ファイル)  
※ テキスト+音声のハッシュでキャッシュされます。

### `GET /api/tts/voices` — 利用可能な日本語音声一覧
**レスポンス:** JSON配列

## セットアップ

### 必要なもの

- Python 3.10+
- Ollama（gemma3:1bモデル）
- Voskモデル（vosk-model-small-ja-0.22）

### インストール手順

```bash
# リポジトリをクローン
git clone https://github.com/OBOYON/voice-avatar.git
cd voice-avatar

# Python依存パッケージをインストール
pip install aiohttp vosk edge-tts

# Voskモデルをダウンロード（約50MB）
wget https://alphacephei.com/vosk/models/vosk-model-small-ja-0.22.zip
unzip vosk-model-small-ja-0.22.zip
rm vosk-model-small-ja-0.22.zip

# Ollamaをインストール（未インストールの場合）
curl -fsSL https://ollama.com/install.sh | sh

# LLMモデルをダウンロード
ollama pull gemma3:1b

# サーバーを起動
python3 server.py
```

ブラウザで http://localhost:8000/ を開いてください。

### systemdサービスとして実行（オプション）

```bash
# サービスファイルを作成
sudo tee /etc/systemd/system/vosk.service << 'EOF'
[Unit]
Description=Vosk Speech Recognition Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/path/to/voice-avatar
ExecStart=/usr/bin/python3 /path/to/voice-avatar/server.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# 有効化・起動
sudo systemctl daemon-reload
sudo systemctl enable --now vosk

# ログ確認
journalctl -u vosk -f
```

## ファイル構成

```
voice-avatar/
├── server.py          # バックエンドサーバー（aiohttp）
├── index.html         # フロントエンド（HTML/CSS/JS 単一ファイル）
├── vosk.service       # systemdサービス定義ファイル
├── README.md          # このドキュメント
├── requirements.txt   # Python依存パッケージ
├── .gitignore         # Git除外設定
└── vosk-model-small-ja-0.22/  # Voskモデル（gitignore対象）
```

## 開発の経緯

このプロジェクトは以下の段階を経て開発されました：

1. **Web Speech API版** — ブラウザ内蔵の音声認識APIで開始。デスクトップChromeでは動作したが、iOS Safariで `service-not-allowed` エラーが発生し動作せず。

2. **Vosk移行** — サーバーサイド音声認識に切り替え。ブラウザからWebSocketでPCM音声を送信し、Voskで認識する方式に。iOS含む全ブラウザで動作。

3. **AI応答追加** — Ollama（gemma3:1b）によるLLMチャット機能を追加。SSEストリーミングでリアルタイム表示。

4. **音声合成追加** — 最初はブラウザ内蔵TTS（SpeechSynthesis）を使用していたが、音質向上のためEdge-TTSに移行。サーバー側でMP3生成。

5. **iOS音声再生対応** — iOSのAutoplay Policy対策として、AudioContextの事前解除（サイレントバッファ再生）と `AudioBufferSourceNode` による再生方式を採用。

6. **ハムスターキャラクター** — SVGアバター、可愛い話し方のシステムプロンプト、質問のみに応答する仕組み、パステルカラーテーマを実装。

## 主な技術的課題と解決策

| 課題 | 解決策 |
|------|--------|
| iOS Safariで音声認識が動かない | Web Speech APIからVoskサーバーサイド認識に移行 |
| iOS Safariで音声が自動再生されない | AudioContextを初回タッチで解除＋サイレントバッファトリック |
| `<audio>`要素でiOSで再生できない | `AudioBufferSourceNode` + `decodeAudioData` に変更 |
| iOS SpeechRecognitionのcontinuous非対応 | `continuous=false` + `onend`での自動再開 |
| LLMが余計な応答をする | 質問・依頼パターンのクライアント側検知（`isQuestion()`関数） |
| LLMが絵文字やMarkdownを出力する | システムプロンプトでの制約＋クライアント側サニタイズ処理 |
| TTS生成が遅い | テキスト+音声のMD5ハッシュでMP3をキャッシュ |

## ライセンス

MIT
