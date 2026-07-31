# Aster 引き継ぎ書(2026-07-31 時点)

このセッションでの作業のまとめです。次にこのプロジェクトを見るAI(Claude/ChatGPT問わず)は、まずこのファイル全体を読んでから着手してください。

---

## 1. プロジェクト概要

「Aster」は、Discord上で動作する人格付きAIアシスタント。単なる質問応答Botではなく、**「AIアシスタント」ではなく対等な友達**として自然に会話することを目指している。文章生成はGemini API。

- GitHub: https://github.com/yuki967787/Aster_2 (Public。旧リポジトリ`Aster`から移行済み)
- 開発環境: Windows / VS Code / Python venv(`.venv`)
- リポジトリ構成は `src/aster/` パッケージ形式(下記「4. ファイル構成」参照)
- **実行時は`src`をカレントディレクトリにして`python -m aster.main`する必要がある**(リポジトリ直下からだとModuleNotFoundError。恒久対策としてpyproject.tomlでのpip install -e化が未着手)

---

## 2. 開発ロードマップと現在地

```
Phase 1(土台)                          ✅ 完了
Phase 2-1(Discord接続の基礎)            ✅ 完了
Phase 2-2(会話基盤: ReplyManager等)     ✅ 完了
Phase 2-3(Memory: 短期記憶/長期記憶)     ✅ 完了
Phase 2-5(添付画像対応)                 ✅ 完了 ← 今回ここまで
  - リアクション/スタンプ/Embedは未着手のまま残っている
Phase 2-4(Character: 感情/照れ屋等)     🔲 未着手(下記「6. 保留中」参照、今まさに着手しようとしている)
Phase 3(PDF解析/OCR)                    🔲 未着手
Phase 4(VOICEVOX/VC参加/読み上げ)        🔲 未着手(希望音声: ナースロボ＿タイプT ノーマル)
```

**次にやるべきこと**: persona.txtの性格設計をGeminiに考え直してもらう(6章参照)。その後Phase 2-4の残り(リアクション/スタンプ/Embed)、Phase 3以降。

---

## 3. このセッションで決まった仕様・決定事項(重要)

- `/chat`のようなスラッシュコマンドは無し。メンションされたら返信する方式(`on_message`)のみ。
- 返信はDiscordの引用返信(reply)を使わず、通常送信(send)で統一。
- 短期記憶はチャンネル単位・直近20件まで(`memory.py`の`ConversationHistory`)。
- 長期記憶の自動抽出は「発言が5分間止まったら実行」のデバウンス方式。保存形式は自由記述の`notes`1本。
- **添付画像対応**: 1メッセージ最大6枚(`MAX_IMAGES`)。画像そのものは短期記憶に残さず、Geminiに120字程度で説明させたテキストを代わりに残す(`describe_image()`)。これが無いと数ターン後に画像の内容を忘れてしまう。
- **モデル振り分け**(レート制限対策): 通常会話・画像説明はメインモデル(`GEMINI_MODEL_MAIN`、精度重視のため画像系もこちら)、長期記憶抽出は軽量モデル(`GEMINI_MODEL_LIGHT`)。`.env`で上書き可能。
- コード修正のルール: **どんな変更も「変更前後の理由と影響範囲」を説明してから実施する**(次のAIも踏襲すること)。

---

## 4. ファイル構成(現状)

```
Aster/
├── .env                      # 実際のAPIキー(Git管理外)
├── .gitignore
├── README.md
├── requirements.txt           # SQLAlchemy, google-genai, discord.py, pillow, pymupdf 等
├── test.py                    # Gemini疎通確認用の使い捨てスクリプト(削除するか未決定)
├── docs/
│   └── handoff.md             # このファイル
├── prompts/
│   ├── persona.txt            # Asterの人格プロンプト(★このあとGeminiに再設計を依頼予定)
│   ├── developer.txt          # 空(未使用)
│   └── rules.txt              # 空(未使用)
└── src/
    └── aster/
        ├── main.py             # エントリーポイント。Aster()を作ってrun()するだけ
        ├── bot.py              # Asterクラス(commands.Bot継承)。setup_hookでinit_db()とCog読込
        ├── config.py           # .env読込、BASE_DIR、DISCORD_TOKEN、GEMINI_API_KEY、GEMINI_MODEL_MAIN/LIGHT、COGS
        ├── ai.py               # Gemini通信。ask_gemini() / describe_image() / extract_memory_update()
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

---

## 5. `listeners/message.py` の処理フロー(最重要ファイル)

```
メッセージ受信
  ↓
Bot自身の発言なら無視
  ↓
添付画像を抽出(最大6枚) → あればGeminiに説明させて短期記憶用テキストに変換
  ↓
短期記憶に記録 → history_context取得(チャンネル単位・直近20件)
  ↓
長期記憶(notes)をDBから取得(ユーザーID単位)
  ↓
typing表示しながら ask_gemini(message, history_context, long_term_notes, images) を呼ぶ
  ↓
  成功 → Asterの返答も短期記憶に記録 → ReplyManagerで送信(演出付き)
         → 5分デバウンスで長期記憶の自動抽出をスケジュール(軽量モデル使用)
  失敗 → error_messagesからランダムな一言を通常送信して終了
```

---

## 6. 保留中・今まさに相談中の課題

- **persona.txtの性格がまだ合っていない**: 「笑」を多用しすぎてムカつく、というフィードバックが直近で出た。これまで人力でpersona.txtを細かく調整してきたが、今回は**Gemini自身に性格設計を考え直してもらう**方向に切り替えることになった。次のAIは、ユーザーに送るための「Geminiへの依頼文」を作るところから着手すること。
- 過去に直した調整点(参考: 新しい依頼文を作る際に矛盾させないよう意識すること):
  - わからない事には茶化さず詳細に解説する
  - 名前呼びは9割省略、呼ぶのは強調したい時だけ
  - 改行禁止ルールに「詳細解説の時は例外」を追加済み
- `test.py`(使い捨てスクリプト)、`prompts/developer.txt`・`prompts/rules.txt`(空ファイル)の扱いは未決定のまま。
- Phase 2-4(感情/照れ屋/ランダムリアクション)、Phase 2-5の残り(リアクション/スタンプ/Embed)は未着手。

---

## 7. 動作確認・デバッグ用コマンド

```bash
# 起動(必ずsrcディレクトリから)
cd src
python -m aster.main

# 長期記憶(notes)の中身を直接確認したい時
python3 -c "from aster.db import get_notes; print(get_notes(DiscordのユーザーID))"
```

起動ログに「X 個のスラッシュコマンドを同期しました。」と出れば正しく起動している。

---

## 8. 次のAIへ

このプロジェクトのオーナー(ゆうき)は、コードだけでなく**「なぜその設計にするか」の説明**を重視する。大きな変更の前には必ず理由と影響範囲を説明し、合意を得てから実装すること。場当たり的な修正ではなく、長期的に育てるプロジェクトとして扱うこと。

また、セッション途中でクレジット切れ・GitHubリポジトリ移行が起きた実績があるため、**作業内容はこまめにコミットを促す・引き継ぎ書を随時更新する**ことを意識すること。