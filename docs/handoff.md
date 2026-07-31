# Aster 引き継ぎ書(2026-07-31 時点・第2版)

このセッションでの作業のまとめです。次にこのプロジェクトを見るAI(Claude/ChatGPT問わず)は、まずこのファイル全体を読んでから着手してください。

---

## 1. プロジェクト概要

「Aster」は、Discord上で動作する人格付きAIアシスタント。単なる質問応答Botではなく、**「AIアシスタント」ではなく対等な友達(少しだけ恋愛要素あり)**として自然に会話することを目指している。文章生成はGemini API。

- GitHub: https://github.com/yuki967787/Aster_2 (Public)
- 開発環境: Windows / VS Code / Python venv(`.venv`)
- **実行時は`src`をカレントディレクトリにして`python -m aster.main`する必要がある**(または`set PYTHONPATH=src`を使う方法でも可)。恒久対策としてpyproject.tomlでのpip install -e化が未着手
- **将来的な目標**: このBotを友達に配布したいと考えている。配布先のユーザーごとに好きな性格へカスタマイズできるようにしたい、という構想がある(現時点では未着手。persona.txtが1つのファイルにハードコードされているので、ユーザーごとに切り替えられる設計への変更が今後必要)

---

## 2. 開発ロードマップと現在地

```
Phase 1(土台)                          完了
Phase 2-1(Discord接続の基礎)            完了
Phase 2-2(会話基盤: ReplyManager等)     完了
Phase 2-3(Memory: 短期記憶/長期記憶)     完了
Phase 2-5(添付画像対応)                 完了
Phase 2-5(スタンプ=絵文字リアクション)   完了 ← 今回ここまで
Phase 2-5(リアクション/Embed)           未着手(スタンプ以外)
Phase 2-4(Character: 感情/照れ屋等)     persona.txt調整で一部実現済み、継続調整中
手書きノート画像機能(数式・詳細解説用)   完了 ← 今回ここまで
Phase 3(PDF解析/OCR)                    未着手
Phase 4(VOICEVOX/VC参加/読み上げ)        未着手(希望音声: ナースロボ＿タイプT ノーマル)
配布・性格カスタマイズ機能               未着手(将来構想。6章参照)
```

次にやるべきこと: 実機テスト(まだ一度も通しで試せていない機能が複数ある)。その後Phase 2-5の残り(リアクション・Embed)、Phase 3、配布・カスタマイズ機能。

---

## 3. このセッションで決まった仕様・決定事項(重要)

- `/chat`のようなスラッシュコマンドは無し。メンションされたら返信する方式(`on_message`)のみ。
- 返信はDiscordの引用返信(reply)を使わず、通常送信(send)で統一。
- 短期記憶はチャンネル単位・直近20件まで。長期記憶は自由記述`notes`1本、5分デバウンスで自動抽出。
- 添付画像対応: 1メッセージ最大6枚。画像内容はGeminiに120字程度で説明させたテキストとして短期記憶に残す。
- モデル振り分け(レート制限対策): 通常会話・画像系はメインモデル(`GEMINI_MODEL_MAIN`)、長期記憶抽出は軽量モデル(`GEMINI_MODEL_LIGHT`)。
  - 注意: Geminiのモデル名は頻繁に変わる/廃止される。2026年7月31日時点でのデフォルトは`gemini-3.6-flash` / `gemini-3.5-flash-lite`だが、404エラーが出たらモデル一覧ページ(https://ai.google.dev/gemini-api/docs/models)で現行モデル名を確認して`.env`か`config.py`のデフォルト値を更新すること。
- persona.txt: 一度Geminiに再設計を依頼し、「友達以上恋人未満」の案から嫉妬的な表現などを削って「少し恋愛要素のある対等な友達」に調整。「笑」は1返信に最大1つ、真剣な相談には付けない。名前呼びは9割省略。
- 絵文字リアクション(スタンプ): Gemini自身に文脈で判断させる方式。`ask_gemini()`の返答末尾に`[EMOJI: 🎉]`のようなタグを付けさせ、コード側で抽出して`add_reaction()`。普段は淡々、心が動いた時だけ稀に付く設計。
- 手書きノート画像: 数式・詳しい解説の時は毎回、Gemini自身が返答末尾に`[MODE: NOTE]`タグを付ける設計。画像送信の前に「ちょっと待っててね」のような一言を先に送ってから生成する。
- コード修正のルール: どんな変更も「変更前後の理由と影響範囲」を説明してから実施する(次のAIも踏襲すること)。

---

## 4. ファイル構成(現状)

```
Aster/
├── .env                      # 実際のAPIキー(Git管理外)
├── .gitignore                 # *.db, .env, pyos.otf/ttf(ライセンス上コミット不可) 等を除外
├── README.md
├── requirements.txt
├── test.py                    # 使い捨てスクリプト(削除するか未決定)
├── docs/
│   └── handoff.md             # このファイル
├── prompts/
│   ├── persona.txt            # Asterの人格プロンプト(継続調整中)
│   ├── developer.txt          # 空(未使用)
│   └── rules.txt              # 空(未使用)
└── src/
    └── aster/
        ├── main.py             # エントリーポイント
        ├── bot.py              # Asterクラス。setup_hookでinit_db()とCog読込
        ├── config.py           # .env読込、BASE_DIR、GEMINI_MODEL_MAIN/LIGHT等
        ├── ai.py               # Gemini通信。ask_gemini()はtuple(本文, 絵文字orNone, ノートモードか)を返す
        ├── formatter.py        # NEW: LaTeX/Markdown除去、分数(A/B)検出
        ├── handwriting.py      # NEW: 手書きノート画像の描画(B5風・分数縦組み・署名)
        ├── note_messages.py    # NEW: ノート送信前の「ちょっと待ってて」系セリフ
        ├── db.py               # 長期記憶の永続化(SQLAlchemy + SQLite)
        ├── memory.py           # 短期記憶(ConversationHistory)
        ├── reply_manager.py    # 返信演出。send()は送信したMessageのリストを返す(リアクション付与用)
        ├── error_messages.py   # エラー時のランダム返答文
        ├── assets/
        │   └── fonts/
        │       ├── Yomogi-Regular.ttf   # フォールバック用フォント(OFL、Git管理下)
        │       └── pyos.otf             # 本命フォント(手元のみ配置、.gitignore対象)
        ├── cogs/
        │   ├── ping.py
        │   └── help.py
        ├── listeners/
        │   └── message.py      # メイン処理。on_messageで全部つながる場所
        └── utils/
            └── logger.py
```

---

## 5. `listeners/message.py` の処理フロー(最重要ファイル)

```
メッセージ受信 → Bot自身なら無視
添付画像を抽出(最大6枚) → あればGeminiに説明させて短期記憶用テキストに変換
短期記憶に記録 → history_context取得
長期記憶(notes)をDBから取得
typing表示しながら ask_gemini(...) を呼ぶ → (本文, 絵文字, is_note) を受け取る

成功時:
  Asterの返答を短期記憶に記録
  is_note=True  → 「ちょっと待ってて」を先に送信 → render_note()で画像化 → 画像送信
  is_note=False → ReplyManagerで通常送信(演出付き)
  emojiがあれば最後に送ったメッセージにadd_reaction()
  5分デバウンスで長期記憶の自動抽出をスケジュール(軽量モデル使用)

失敗時: error_messagesからランダムな一言を送って終了
```

---

## 6. 保留中・未着手の課題

- 実機テスト未実施の機能が複数ある: スタンプ(絵文字リアクション)、手書きノート画像、モデル振り分け後のpersona.txt新方向。これらはまだ一度も通しでDiscord上で確認できていない。次のAIはまずここから。
- 友達への配布・性格カスタマイズ構想(1章参照): 現状`persona.txt`は1ファイル固定。将来的にはユーザー(サーバー)ごとに性格を切り替えられる設計が必要になる。想定される方向性の一例(未確定):
  - `db.py`の`UserProfile`のような形で、サーバー/ユーザーごとに使用するpersona.txtのパスや性格設定を持たせる
  - Discordのスラッシュコマンドで性格をある程度選べるようにする(ただし「`/chat`のようなコマンドは無し」という過去の決定と矛盾しないよう、設定系コマンドは別枠として扱うか要検討)
  - これは大きな設計変更になるため、着手前に必ずユーザーと方針をすり合わせること
- `test.py`、`prompts/developer.txt`・`prompts/rules.txt`(空ファイル)の扱いは未決定。
- Phase 2-5の残り(リアクション・Embed)、Phase 3(PDF解析/OCR)、Phase 4(VOICEVOX)は未着手。
- Geminiのモデル名は変わりやすいので、404エラーが出たら3章の注意点を参照。

---

## 7. 動作確認・デバッグ用コマンド

```
# 起動(Windowsの場合)
set PYTHONPATH=src && python -m aster.main

# 起動(macOS/Linuxの場合)
cd src && python -m aster.main

# 長期記憶(notes)の中身を直接確認したい時
python3 -c "from aster.db import get_notes; print(get_notes(DiscordのユーザーID))"
```

起動ログに「X 個のスラッシュコマンドを同期しました。」と出れば正しく起動している。

---

## 8. 次のAIへ

このプロジェクトのオーナー(ゆうき)は、コードだけでなく「なぜその設計にするか」の説明を重視する。大きな変更の前には必ず理由と影響範囲を説明し、合意を得てから実装すること。場当たり的な修正ではなく、長期的に育てるプロジェクトとして扱うこと。

セッション途中でのクレジット切れ・GitHubリポジトリ移行が過去に発生している。作業内容はこまめにコミットを促し、引き継ぎ書も区切りの良いタイミングで更新すること。

配布・性格カスタマイズ構想はまだ「言葉にしただけ」の段階なので、実装に入る前に必ずゆうきと具体的な仕様(どこまで自由に変えられるか、UIはどうするか等)を相談すること。