# Aster 引き継ぎ書(2026-07-11 時点)

このセッションでの作業のまとめです。次にこのプロジェクトを見るAI(Claude/ChatGPT問わず)は、まずこのファイル全体を読んでから着手してください。

---

## 1. プロジェクト概要

「Aster」は、Discord上で動作する人格付きAIアシスタント。単なる質問応答Botではなく、**「AIアシスタント」ではなく対等な友達**として自然に会話することを目指している。文章生成はGemini API(`gemini-flash-latest`。`.env`で`GEMINI_MODEL`を上書き可能)。

- GitHub: https://github.com/yuki967787/Aster (Public)
- 開発環境: Windows / VS Code / Python venv(`.venv`)
- リポジトリ構成は `src/aster/` パッケージ形式(下記「4. ファイル構成」参照)

---

## 2. 開発ロードマップと現在地

```
Phase 1(土台)                          ✅ 完了
  - Discord Bot / Gemini接続 / .env / ログ

Phase 2-1(Discord接続の基礎)            ✅ 完了
  - Discord接続 / Gemini接続 / メンション返信

Phase 2-2(会話基盤)                     ✅ 完了 ← 今回ここまで実装
  - ReplyManager(typing演出/分割送信/送信間隔)
  - error_messages.py
  ※ 本来ロードマップではPhase2-3より先の予定だった

Phase 2-3(Memory)                       ✅ 完了(先行して実装済み)
  - 会話履歴保存(短期記憶) / 長期記憶(DB)
  - 「ユーザーごとの履歴」は不採用、チャンネル単位に決定(詳細は5章)
  - 「要約」は長期記憶の自動抽出が実質その役割を兼ねている

Phase 2-4(Character)                    🔲 未着手
  - 感情 / 照れ屋 / ランダムリアクション / 会話パターン

Phase 2-5(Discordらしさ)                🔲 未着手
  - リアクション / 添付画像対応 / スタンプ / Embed

Phase 3(画像解析/PDF解析/OCR)            🔲 未着手

Phase 4(VOICEVOX/VC参加/読み上げ)        🔲 未着手
  - 希望音声: 「ナースロボ＿タイプT(ノーマル)」
```

**次にやるべきこと**: Phase 2-4(Character)またはPhase 2-5(Discordらしさ)。どちらを先にするかはまだ未決定。

---

## 3. このセッションで決まった仕様・決定事項(重要)

- **`/chat`のようなスラッシュコマンドは無し**。メンションされたら返信する方式(`on_message`)のみで進める。
- **返信はDiscordの引用返信(reply)を使わず、通常送信(send)で統一**。友達同士の会話らしさを優先した判断。
- 短期記憶は**チャンネル単位**(誰の発言かに関わらず、同じチャンネルの会話をまとめて覚える)、**直近20件**まで。
- 長期記憶の自動抽出は**「発言が5分間止まったら実行」**というデバウンス方式。毎メッセージ実行はコスト面で不採用。
- 長期記憶の保存形式は、最初からカラムを分けず**自由記述の`notes`1本**(理由: 何を覚えさせたいかが固まってから細分化する方が安全なため)。
- コード修正のルール: **どんな変更も「変更前後の理由と影響範囲」を説明してから実施する**(このセッションで確立したルール。次のAIも踏襲すること)。

---

## 4. ファイル構成(現状)

```
Aster/
├── .env                      # 実際のAPIキー(Git管理外)
├── .gitignore                # *.db, .env, __pycache__ など除外済み
├── README.md
├── requirements.txt           # SQLAlchemy含む
├── test.py                    # Gemini疎通確認用の簡易スクリプト(そのまま残置)
├── prompts/
│   ├── persona.txt            # Asterの人格プロンプト(作り込み済み)
│   ├── developer.txt          # 空(未使用、用途未定)
│   └── rules.txt              # 空(未使用、用途未定)
└── src/
    └── aster/
        ├── main.py             # エントリーポイント。Aster()を作ってrun()するだけ
        ├── bot.py              # Asterクラス(commands.Bot継承)。setup_hookでinit_db()とCog読込
        ├── config.py           # .env読込、BASE_DIR、DISCORD_TOKEN、GEMINI_API_KEY、COGSリスト
        ├── ai.py               # Gemini通信。ask_gemini() / extract_memory_update()
        ├── db.py               # 長期記憶の永続化(SQLAlchemy + SQLite、aster.db)
        ├── memory.py           # 短期記憶(ConversationHistory、チャンネル単位・直近20件)
        ├── reply_manager.py    # 返信の演出(typing/分割送信/送信間隔)
        ├── error_messages.py   # エラー時のランダム返答文
        ├── cogs/
        │   ├── ping.py         # /ping スラッシュコマンド
        │   └── help.py         # /help スラッシュコマンド
        ├── listeners/
        │   └── message.py      # メイン処理。on_messageで全部つながる場所
        └── utils/
            └── logger.py       # ロガー設定
```

**注意**: `reply_manager.py`は元々リポジトリ直下にあったが、他の機能ファイルと揃えるため`src/aster/`直下に移動済み。リポジトリ側で移動が反映されているか要確認。

---

## 5. `listeners/message.py` の処理フロー(最重要ファイル)

```
メッセージ受信
  ↓
Bot自身の発言なら無視
  ↓
短期記憶に今回の発言を記録 → history_context取得(チャンネル単位・直近20件)
  ↓
長期記憶(notes)をDBから取得(ユーザーID単位)
  ↓
typing表示しながら ask_gemini(message, history_context, long_term_notes) を呼ぶ
  ↓
  成功 → Asterの返答も短期記憶に記録 → ReplyManagerで送信(演出付き)
         → 5分デバウンスで長期記憶の自動抽出をスケジュール
  失敗 → error_messagesからランダムな一言を通常送信して終了
```

`MessageListener`クラス内の`_pending_extraction`辞書(user_id→asyncio.Task)で、デバウンスのタイマー管理をしている。会話が続く限りタイマーが延長され、5分止まった時だけ`extract_memory_update()`が呼ばれて`db.save_notes()`される。

---

## 6. 未整理・保留中の項目

- `test.py`(ルート直下、Gemini疎通確認用の使い捨てスクリプト): 削除するか残すか未決定
- `prompts/developer.txt`, `prompts/rules.txt`: 空ファイル。用途が決まっていない
- Phase 2-4以降は設計自体が未着手(感情表現、リアクション、画像対応など、まだ仕様の相談すらしていない)

---

## 7. 動作確認・デバッグ用コマンド

```bash
# 起動
python -m aster.main   # src/ ディレクトリから実行する想定

# 長期記憶(notes)の中身を直接確認したい時
python3 -c "from aster.db import get_notes; print(get_notes(DiscordのユーザーID))"
```

起動ログに「X 個のスラッシュコマンドを同期しました。」と出れば、`bot.py`のAsterクラス経由で正しく起動している。

---

## 8. 次のAIへ

このプロジェクトのオーナー(ゆうき)は、コードだけでなく**「なぜその設計にするか」の説明**を重視する。大きな変更の前には必ず理由と影響範囲を説明し、合意を得てから実装すること。場当たり的な修正ではなく、長期的に育てるプロジェクトとして扱うこと。