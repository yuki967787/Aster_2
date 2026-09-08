# Aster VC音声受信

今回追加するのは「Asterの耳」の最初の実装です。

## 処理の流れ

Discord VC
→ ユーザー別にPCM受信
→ 約1.2秒の無音で発話確定
→ メモリ上でWAV化
→ ローカルWhisper
→ `MessageListener.handle_voice_text()`
→ Gemini
→ 既存のVOICEVOX読み上げ

Aster自身のユーザーIDは受信対象から除外します。

## 注意

`voice_receive.py` は `MessageListener` に次のメソッドが存在することを前提にしています。

```python
async def handle_voice_text(self, guild, member, text):
    ...
```

このメソッドは既存の `message.py` に追加してください。

また、`openai-whisper` の音声デコードに `soundfile` と `numpy` を使用します。

## インストール

```powershell
python -m pip install -r requirements_voice.txt
```

既存の `requirements.txt` に統合する場合は、重複するパッケージを整理してください。

## 重要

Whisperはローカルで動作するため、通常の文字起こし処理そのものをGoogle APIへ送る設計ではありません。

初回はモデルのダウンロードが発生します。
