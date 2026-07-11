"""
db.py
-----
Asterの「長期記憶」を永続化するモジュール。

SQLiteファイル1つ(aster.db)にSQLAlchemyでアクセスする。
サーバー不要で、リポジトリ直下に aster.db が作られるだけなので、
デプロイ環境が変わっても構成が複雑にならない。

ここで持つ情報は、あえて notes という自由記述1本にしている。
「好きな食べ物」「口調」のようにカラムを最初から分けると、
Geminiにとって「どのカラムに書くべきか」の判断が複雑になるため、
まずは自由記述にして、実際に必要になったカラムだけ後で追加する方針。
"""

from __future__ import annotations

from sqlalchemy import String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from aster.config import BASE_DIR

DB_PATH = BASE_DIR / "aster.db"
engine = create_engine(f"sqlite:///{DB_PATH}")


class Base(DeclarativeBase):
    pass


class UserProfile(Base):
    """Discordユーザーごとに覚えておく情報。"""

    __tablename__ = "user_profiles"

    # Discordのユーザーid(int)をそのまま主キーにする
    user_id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))
    notes: Mapped[str] = mapped_column(Text, default="")


def init_db() -> None:
    """テーブルが無ければ作成する。起動時に1回呼べばよい。"""
    Base.metadata.create_all(engine)


def get_notes(user_id: int) -> str:
    """このユーザーについて覚えている内容を返す。無ければ空文字。"""

    with Session(engine) as session:
        profile = session.get(UserProfile, user_id)
        return profile.notes if profile else ""


def save_notes(user_id: int, display_name: str, notes: str) -> None:
    """このユーザーについての記憶(notes全文)を保存/上書きする。"""

    with Session(engine) as session:
        profile = session.get(UserProfile, user_id)

        if profile is None:
            profile = UserProfile(
                user_id=user_id,
                display_name=display_name,
                notes=notes,
            )
            session.add(profile)
        else:
            profile.display_name = display_name
            profile.notes = notes

        session.commit()