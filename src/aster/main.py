"""
main.py
-------
起動処理だけを行うエントリーポイント。

以前はここに on_message の直書きロジックがあったが、
listeners/message.py の MessageListener と処理が重複していたため削除し、
bot.py の Aster クラス(Cog読み込み・スラッシュコマンド同期対応)に一本化した。
main.pyは「Asterを作って動かす」以外のロジックを持たせない方針にする。
"""

from aster.bot import Aster
from aster.config import DISCORD_TOKEN

if __name__ == "__main__":
    bot = Aster()
    bot.run(DISCORD_TOKEN)