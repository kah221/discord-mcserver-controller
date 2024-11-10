# 241107_2356~241111_0022
# 機能
# ■【1.】 /mcsv-run          サーバー起動    （スラッシュコマンドのみで実装）
# ■【2.】 /mcsv-stop         サーバー停止    （スラッシュコマンドのみで実装）
# ■【3.】 /mcsv-backup       サーバーのバックアップ作成  （スラッシュコマンド→□モーダルで実装）
# ■【4.】 /mcsv-restore      サーバーの復元  （スラッシュコマンド→□モーダルで実装）
# ■【5.】 -     　            -
# ■【6.】 /mcsv-status       サーバーの状態を取得する (スラッシュコマンドのみで実装)
# ■【7.】 /mcsv-checkbackup  バックアップ一覧を表示 （スラッシュコマンドのみで実装）
# ■【8.】 botにDMを送信       サーバーOPコマンドを実行する   (eventで補足し、権限はチャンネルIDを照合)

import discord
from discord import app_commands # スラッシュコマンドの実装に必要
import os
from dotenv import load_dotenv
from discord import ui # モーダル作成に必要
import re # 入力値のバリデーションに必要
import subprocess # .batファイルを実行したりするために必要
import threading # マイクラサーバーをここで動かす（サーバー起動時プロセスをサーバーが占有してしまうため非同期処理が適している）
import re # バリデーション処理を行う為に必要
import shutil # ファイルをコピーするために必要
import datetime as dt # 現在時刻取得に必要


# ------------------------------
# ↓ 変数定義
# ------------------------------


load_dotenv()

# discordボットの設定
intents = discord.Intents.default()
intents.messages = True
client = discord.Client(intents=intents)
client.wait_until_ready()
tree = app_commands.CommandTree(client)

# ディレクトリ関連
# 作業ディレクトリに関連するエラーが発生して面倒なので、作業ディレクトリをこのスクリプトの場所に固定する
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir) # 作業ディレクトリ移動
# ※同じ階層にサーバーファイルを配置
svbat_path = "run.bat"           # マイクラのサーバーを起動させるバッチファイルのパス
svlog_path = "../svlog.txt"      # マイクラサーバーのログをここに出力（する予定）
server_dir = "."                 # サーバーが置かれている場所
backup_dir = "../__backups/"     # バックアップの保存先

# バックアップ作成時に無視するファイル
ignore = ['controller.py', '.env']

# サーバーの状態を格納する変数
svStatus = dict(
    startTime = None,  # サーバーが起動した時刻
    whoStarted = '',   # サーバーを起動した人
    joinedPlayer = {}  # 起動中にサーバーに参加した人の情報
)
# ↑svStatusの説明
# - サーバーに参加した時点でkeyが文字列、valueが要素2のリストで追加される
# - サーバー停止時{}に初期化する
# - リストの1つ目の要素は deltatime ｵﾌﾞｼﾞｪｸﾄが入り、サーバーに滞在した時間分加算される
# - リストの2つ目の要素は datetime  ｵﾌﾞｼﾞｪｸﾄが入り、サーバーに参加したタイミングで更新される
#     ↑また、サーバーから退出したタイミングでNoneに置き換える
#     ↑サーバーに参加中か否かはここを見る（Noneでないとき参加中）
# 例）
# {
#     'drop221': [deltatimeｵﾌﾞｼﾞｪｸﾄ, datetimeｵﾌﾞｼﾞｪｸﾄ],
#     'steevee': [deltatimeｵﾌﾞｼﾞｪｸﾄ, datetimeｵﾌﾞｼﾞｪｸﾄ],
#     ...
# }

# discordからサーバーのopコマンドを実行できる人（discordのDMのチャンネルIDとする）
# opコマンドは、このbotとのDMで行うことにする
operatorID = [
    os.getenv("DISCORD_CHANNELID_DR"),    # 自分
    # os.getenv("DISCORD_CHANNELID_YA")     # 友人代表
]

# discordからbotのスラッシュコマンドを実行できる人（discordユーザID）
commanderID = [
    os.getenv("DISCORD_USERID_DR"),    # 自分
    os.getenv("DISCORD_USERID_YA")     # 友人代表
]

# botを立ち上げてから1度も起動していない場合は文字列defaultを入れておき、サーバー起動中or停止中の判定に用いる（無理矢理）
thread = 'default'


# ------------------------------
# ↑ 変数定義
# ↓ その他の関数
# ------------------------------


# サーバーへの合計参加時間を計算し記録する関数
def joinLeftLog(pName, which): # pName対称のプレイヤー名, which:参加ならFalse-退出ならTrueが入る
    now = dt.datetime.now()
    jP = svStatus['joinedPlayer'] # 辞書型

    # 既に参加済みか判断
    if(pName in list(jP.keys())):
        totalTime = jP[pName][0]    # ｲﾝﾃﾞｯｸｽ0に累計参加時間を入れている [timedelta]
        lastJoinTime = jP[pName][1] # ｲﾝﾃﾞｯｸｽ1に最後に参加した時刻を入れている [datetime]

        if(which): # 退出時のみ処理
            totalTime += now - lastJoinTime # 現在時刻と前回参加時刻の差分を加算 型...[datetime] - [datetime] = [deltatime]
            now = None # 退出時はここをNoneにすることで、/mcsv-statusでﾌﾟﾚｲﾔｰが現在参加中か否かを判断できるようにする

        jP.update({pName: [totalTime, now]}) # {プレイヤー名: [累計時間, 現在時刻で更新]}
        print({pName: [totalTime, now]})

    else:
        # 初回参加（この節は参加時にしか動かない。退出時には既に辞書に登録されているため）
        print('初回参加')
        jP.update({pName: [dt.timedelta(), now]}) # {プレイヤー名: [累計参加時間初期値0, 現在時刻で更新]}

    # 更新
    svStatus['joinedPlayer'] = jP
    return


# [timedelta]を見やすく整形する関数→[string]
def formatTimeDelta(delta):
    d = delta.days
    h = delta.seconds // 3600
    m = (delta.seconds % 3600) // 60
    s = delta.seconds % 60
    r = []
    if d:
        r.append(f"{d}日")
    if h:
        r.append(f"{h}時間")
    if m:
        r.append(f"{m}分")
    if s:
        r.append(f"{s}秒")

    return " ".join(r)


# サーバー停止時、まとめを文字列で返す関数（/mcsv-status の処理とほぼ同じだが...）
def summarize():
    result = ''
    # 起動時刻を取得
    startTime = svStatus['startTime'].strftime("%y%m%d_%H%M")

    # 稼働時間を計算
    workingTime = formatTimeDelta(dt.datetime.now() - svStatus['startTime']) # [timedelta]→[string]

    # 参加者まとめ
    playerData = '↓\n' # [string]
    jP = svStatus['joinedPlayer'] # 参加済みﾌﾟﾚｲﾔｰの辞書を取得
    nameList = list(jP.keys()) # 辞書から参加者の名前を取得
    for name in nameList: # ﾌﾟﾚｲﾔｰ毎に累計参加時間を文字列にして加える
        playerData += '　　　　   ' + name + ' : ' + formatTimeDelta(jP[name][0]) + '\n'
    if playerData == '↓\n': playerData = '参加者はいませんでした\n'

    result += '\n======まとめ======\n'
    result += '起動者　 : ' + svStatus['whoStarted'] + '\n'
    result += '起動時刻 : ' + startTime + '\n'
    result += '停止時刻 : ' + dt.datetime.now().strftime("%y%m%d_%H%M") + '\n'
    result += '稼働時間 : ' + workingTime + '\n'
    result += '参加者　 : ' + playerData
    result += '==================\n'
    result += '```'
    return result


# ------------------------------
# ↑ その他の関数
# ↓ モーダル
# ------------------------------


# □【3.】バックアップ作成時に開かれるモーダル
class McsvBackup(ui.Modal, title='バックアップを生成'):
    def __init__(self, svStatus):
        super().__init__()

    # 入力欄により格納される値
    input_backupDescription = ui.TextInput(label='バックアップの名前', placeholder='例）平仮名カタカナ半角英数字', required=True, max_length=30, default=None) # バックアップの説明（フォルダ名の一部になる）

    # モーダルが送信されたとき
    """流れ
    (0. モーダルが開く際にはサーバーは停止状態になっている)
    1. 入力値のバリデーション
    2. フォルダ名を「現在時刻+入力文字」としてフォルダを生成
    3. 作成したフォルダにコピーする
    """
    async def on_submit(self, interaction: discord.Interaction):
        result_msg = '```【バックアップ作成】\n'
        error_count = 0
        now = dt.datetime.now().strftime("%y%m%d_%H%M")
        # ------------------------------
        # 1. バリデート処理
        pattern = r'^[\u3040-\u309F\u30A0-\u30FFa-zA-Z0-9]+$'
        if(bool(re.fullmatch(pattern, self.input_backupDescription.value)) == False):
            result_msg += '>>> 入力値に不正な文字が含まれています\n'
            error_count += 1
        else:
            backupName = backup_dir + now + "_" + self.input_backupDescription.value # バックアップ名
            # ------------------------------
            # 2. フォルダ生成
            try:
                os.makedirs(backupName, exist_ok=False)
            except OSError as e:
                result_msg += '>>> ディレクトリ作成に失敗\n'
                error_count += 1

            # ------------------------------
            # 3. コピー
            if(error_count == 0):
                try:
                    shutil.copytree(
                        server_dir,         # コピー元のパス
                        backupName,         # コピー先のパス
                        dirs_exist_ok=True, # ？
                        ignore=shutil.ignore_patterns(*ignore)       # 無視するファイル名を指定
                        )
                except FileExistsError:
                    result_msg += '>>> バックアップ生成に失敗（コピー先に問題）\n'
                    error_count += 1
                except Exception as e:
                    result_msg += '>>> バックアップ生成に失敗（不明なエラー）' + str(e) + '\n'
                    error_count += 1

        if(error_count == 0):
            result_msg += '>>> 成功しました\n'
            result_msg += '作成者　　 : ' + str(interaction.user.name) + '\n'
            result_msg += 'ﾊﾞｯｸｱｯﾌﾟ名 : ' + now + "_" + self.input_backupDescription.value + '\n'
        else:
            result_msg += 'もう一度やり直してください'

        result_msg += '```'
        print(result_msg)
        await interaction.response.send_message(result_msg)
        return


# □【4.】復元時に開かれるモーダル
class McsvRestore(ui.Modal, title='復元 （注意：現行データは上書きされ消えます）'):
    def __init__(self, svStatus):
        super().__init__()

    # 入力欄により格納される値
    input_backupName = ui.TextInput(label='バックアップ名をコピペ', placeholder='例）241109_1440_拠点完成時', required=True, max_length=50, default=None)

    # モーダルが送信されたとき
    """流れ
    (0. モーダルが開く際にはサーバーは停止状態になっている)
    1. 存在するバックアップをリストで取得
    2. 入力値が↑のリストに存在するかを判断
    3. 現在のサーバーファイルを削除
    4. バックアップをコピー
    """
    async def on_submit(self, interaction: discord.Interaction):
        print(f'/mcsv-restore のモーダルが送信された')
        result_msg = '```【バックアップから復元】\n'
        error_count = 0

        # ------------------------------
        # 1. 存在するバックアップをリストで取得
        backups = os.listdir(backup_dir)

        # ------------------------------
        # 2. 入力値の存在性確認
        print(f'入力値: {self.input_backupName.value}')
        if self.input_backupName.value in backups:
            print(f'同じバックアップ名が存在')
            # ------------------------------
            # 3. 現在のサーバーファイルを削除
            try:
                shutil.rmtree('config')
                shutil.rmtree('crash-reports')
                shutil.rmtree('libraries')
                shutil.rmtree('logs')
                shutil.rmtree('mods')
                shutil.rmtree('world')
                deleteFile = ['banned-ips.json',
                            'banned-players.json',
                            'eula.txt',
                            'minecraft_server.1.10.2.jar',
                            'ops.json',
                            'run.bat',
                            'server.properties',
                            'usercache.json',
                            'usernamecache.json',
                            'whitelist.json']
                for df in deleteFile:
                    os.remove(df)
            except Exception as e:
                result_msg += '>>> ファイル削除失敗\n' + str(e)
                error_count += 1
        else:
            # 入力されたバックアップ名がヒットしなかった場合
            result_msg += '>>> 入力値: ' + self.input_backupName.value + '\n'
            result_msg += '>>> 入力されたバックアップ名は存在しません\n'
            error_count += 1


        # ------------------------------
        # 4. コピー
        if(error_count == 0): # ここまでエラーが無い場合実行
            try:
                shutil.copytree(
                    backup_dir + self.input_backupName.value,         # コピー元のパス
                    server_dir,         # コピー先のパス
                    dirs_exist_ok=True, # ？
                    # ignore=shutil.ignore_patterns(*ignore)       # 無視するファイル名を指定
                    )
            except FileExistsError:
                result_msg += '>>> 復元に失敗（コピー先に問題）\n'
                error_count += 1
            except Exception as e:
                result_msg += '>>> 復元に失敗（不明なエラー）\n'
                error_count += 1
                print(f'e: {e}')

        # 最終成功判定
        if(error_count == 0):
            result_msg += '>>> 成功しました\n'
            result_msg += '復元者　　 : ' + str(interaction.user.name) + '\n'
            result_msg += 'ﾊﾞｯｸｱｯﾌﾟ名 : ' + self.input_backupName.value + '\n'
        else:
            result_msg += 'もう一度やり直してください'


        result_msg += '```'
        print(result_msg)
        await interaction.response.send_message(result_msg)
        return


# ------------------------------
# ↑ モーダル
# ↓ スラッシュコマンド
# ------------------------------


# ■【1.】サーバーを起動するスラッシュコマンド
@tree.command(name='mcsv-run', description='マイクラサーバーを起動する')
async def mcsvRun(interaction: discord.Interaction):
    # ------------------------------
    print(f'/mcsv-run が実行された')
    result_msg = '```【サーバー起動】\n'
    error_count = 0
    global thread
    # ------------------------------------------------------------
    # マイクラサーバーを起動する関数
    def runMCServer(result_msg, error_count, thread):
        # 非同期処理の定義？
        global process
        try:
            process = subprocess.Popen(
                [svbat_path],           # 実行するbatファイルのパス（リストで指定）
                stdout=subprocess.PIPE, # stdout, stderr引数を指定することでrun.batの出力結果をPython側で取得できる
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,  # 操作のために必要
                shell=False
                )
        except Exception as e:
            result_msg += '>>> サブプロセス作成に失敗\n'
            error_count += 1

        # サーバーの出力
        def print_log():
            for line in iter(process.stdout.readline, b''):
                try:
                    decode = line.decode('utf-8')
                except Exception as e:
                    print('mcsv >>> デコード失敗', end='')
                else:
                    print('mcsv >>> ' + decode, end='')
                    # with open(svlog_path, 'a', encoding='utf-8') as f: # a: 追記モード
                    #     f.write('>>> ' + str(line) + '\n')

                    # ﾌﾟﾚｲﾔｰが参加・退出を補足する（滞在時間計算と参加中かどうかの判定のため）
                    # [17:06:07] [Server thread/INFO]: drop221 joined the game
                    # [17:07:31] [Server thread/INFO]: drop221 left the game
                    joinObj = re.search('joined the game', decode)
                    leftObj = re.search('left the game', decode) # kickされた場合もleft the gameは出る

                    if(bool(joinObj)): # join the gameが含まれる
                        playerName = decode[33:joinObj.start()-1]
                        joinLeftLog(playerName, False) # 参加はFalse
                    elif(bool(leftObj)): # left the gameが含まれる
                        playerName = decode[33:leftObj.start()-1]
                        joinLeftLog(playerName, True) # 退出はTrue

        try:
            # マイクラサーバー用のスレッドを立てる
            thread = threading.Thread(target=print_log, name='mcserver', daemon=True)
            thread.start()
        except Exception as e:
            result_msg += '>>> スレッド起動失敗\n'
            error_count += 1

        return result_msg, error_count, thread

    # ------------------------------------------------------------
    # 権限確認
    print(f'コマンド実行者  {interaction.user.name}: {interaction.user.id}')
    if str(interaction.user.id) in commanderID:
        # サーバーが起動中かどうか判断
        if(thread != 'default'):
            # 1回以上起動したが現在起動中か停止中かはわからない
            print(f'thread.is_alive(): {thread.is_alive()}')
            if(thread.is_alive() == False):
                # ==False → 停止中ならOK
                result_msg, error_count, thread = runMCServer(result_msg, error_count, thread) # マイクラサーバーを起動する関数

            else: # 既に起動していた場合（is_alive()==Trueの場合）
                result_msg += '>>> サーバーは既に起動中です\n'
                error_count += 1

        else: # 停止中（default）
            result_msg, error_count, thread = runMCServer(result_msg, error_count, thread) # マイクラサーバーを起動する関数

        # 処理に成功したか判断
        if(error_count == 0):
            # 状態更新
            svStatus['startTime'] = dt.datetime.now() # フォーマットせずに
            svStatus['whoStarted'] = interaction.user.name

            result_msg += '>>> 成功しました\n'
            result_msg += '実行者　　 : ' + str(interaction.user.name) + '\n'
        else:
            result_msg += '>>> 失敗しました\nもう一度やり直してください\n'
    else:
        result_msg += '>>> コマンド実行権限がありません'

    result_msg += '```'
    print(result_msg)
    await interaction.response.send_message(result_msg)


# ■【2.】サーバーを停止するスラッシュコマンド
@tree.command(name='mcsv-stop', description='マイクラサーバー停止')
async def mcsvstop(interaction: discord.Interaction):
    # ------------------------------
    print(f'/mcsv-stop が実行された')
    result_msg = '```【サーバー停止】\n'
    error_count = 0
    resultFlag = False
    global process
    global thread
    # ------------------------------
    # 権限確認
    print(f'コマンド実行者  {interaction.user.name}: {interaction.user.id}')
    if str(interaction.user.id) in commanderID:
        # サーバーが起動中かどうか判断
        if(thread != 'default'):
            print(f'thread.is_alive(): {thread.is_alive()}')
            if(thread.is_alive()):
                # True→起動中 OK
                # さらに、現在参加中のプレイヤーがいる時、閉じさせない
                isExistPlayer = False # ﾌﾟﾚｲﾔｰがいない前提
                jP = svStatus['joinedPlayer'] # 参加済みﾌﾟﾚｲﾔｰの辞書を取得
                nameList = list(jP.keys()) # 辞書から参加者の名前を取得
                for name in nameList:
                    if(jP[name][1] != None): #jP[name][1]←サーバーに参加した時刻が入る（退出時はNoneになっている）
                        # つまり、全ての参加者についてjP[name][1]が全てNoneになっていればOK
                        isExistPlayer = True
                if isExistPlayer:
                    result_msg += '>>> 現在参加中のプレイヤーがいるため閉じられません\n'
                    error_count += 1
                else: # 参加中のプレイヤーがいないとき停止する
                    try:
                        process.stdin.write(b'stop\n') # 停止コマンドを送信
                        process.stdin.flush() # バッファにたまっているデータを強制的に送信
                    except Exception as e:
                        result_msg += '>>> 停止命令の送信に失敗\n'
                        error_count += 1
                    else: # 停止コマンドの送信に成功した時に実行
                        process.kill() # プロセスを終了
                        print(f'thread.is_alive(): {thread.is_alive()}')
                        thread.join()  # スレッド終了を待つ
                        print(f'thread.is_alive(): {thread.is_alive()}')

                        # サーバーステータスを表示するフラグを立てる
                        resultFlag = True
            else:
                # False→停止中
                result_msg += '>>> 既にサーバーは停止しています\n'
                error_count += 1
        else:
            # thread == 'default'→停止中（まだ一度も起動していない状態）
            result_msg += '>>> 既にサーバーは停止しています\n'
            error_count += 1

        # 処理に成功したか判断
        if(error_count == 0):
            # リザルトを表示のため。（サーバー停止時にsvStatusは初期化するのでそれより前に呼び出しておく）
            if(resultFlag):
                summary = summarize()

            # サーバー状態変数を初期状態に
            svStatus['startTime'] = None
            svStatus['whoStarted'] = ''
            svStatus['joinedPlayer'] = {}

            result_msg += '>>> 成功しました\n'
            result_msg += '実行者　 : ' + str(interaction.user.name) + '\n' + summary

        else:
            result_msg += '>>> 失敗しました\n'
    else:
        result_msg += '>>> コマンド実行権限がありません'

    result_msg += '```'
    print(result_msg)
    await interaction.response.send_message(result_msg)


# ■【3.】バックアップ生成モーダルを呼び出すスラッシュコマンド
@tree.command(name='mcsv-backup', description='バックアップを作成する')
async def mcsvbackup(interaction: discord.Interaction):
    # ------------------------------
    print(f'/mcsv-backup が実行された')
    global thread

    # ------------------------------
    # 権限確認
    print(f'コマンド実行者  {interaction.user.name}: {interaction.user.id}')
    if str(interaction.user.id) in commanderID:
        # サーバーが停止していることを確認してからモーダルを開く
        if(thread != 'default'):
            print(f'thread.is_alive(): {thread.is_alive()}')
            if(thread.is_alive()):
                await interaction.response.send_message('```【バックアップ作成】\n>>> サーバーが稼働中\nバックアップ作成時はサーバーを停止してください```')
            else:
                await interaction.response.send_modal(McsvBackup(svStatus)) # モーダルを開く関数呼び出し
        else:
            await interaction.response.send_modal(McsvBackup(svStatus)) # モーダルを開く関数呼び出し
    else:
        await interaction.response.send_modal('```【バックアップ作成】\n>>> コマンド実行権限がありません```') # モーダルを開く関数呼び出し


# ■【4.】サーバーを復元するモーダルを呼び出すスラッシュコマンド
@tree.command(name='mcsv-restore', description='バックアップから復元する')
async def mcsvrestore(interaction: discord.Integration):
    # ------------------------------
    print(f'/mcsv-restore が実行された')
    global thread
    # ------------------------------

    # 権限確認
    print(f'コマンド実行者  {interaction.user.name}: {interaction.user.id}')
    if str(interaction.user.id) in commanderID:
        # サーバーが停止していることを確認してからモーダルを開く
        if(thread != 'default'):
            print(f'thread.is_alive(): {thread.is_alive()}')
            if(thread.is_alive()):
                await interaction.response.send_message('```【バックアップから復元】\n>>> サーバーが稼働中\n復元時はサーバーを停止してください```')
            else:
                await interaction.response.send_modal(McsvRestore(svStatus)) # モーダルを開く関数呼び出し
        else:
            await interaction.response.send_modal(McsvRestore(svStatus)) # モーダルを開く関数呼び出し
    else:
        await interaction.response.send_message('```【バックアップから復元】\n>>> コマンド実行権限がありません```')



# ■【6.】サーバーの状態を表示するスラッシュコマンド
@tree.command(name='mcsv-status', description='サーバーの状態を確認する')
async def mcsvstatus(interaction: discord.Interaction):
    # ------------------------------
    result_msg = '```【サーバーの状態を確認】\n'
    result_msg_close = '```【サーバーの状態を確認】\n- 状態　　: 停止中\n```'
    # ------------------------------
    # サーバーが停止していることを確認してからモーダルを開く
    if(thread != 'default'):
        print(f'thread.is_alive(): {thread.is_alive()}')
        if(thread.is_alive()):
            # 起動中

            # 起動時刻を取得
            startTime = svStatus['startTime'].strftime("%y%m%d_%H%M")

            # 稼働時間を計算
            workingTime = formatTimeDelta(dt.datetime.now() - svStatus['startTime'])

            # 参加中
            online = ''
            jP = svStatus['joinedPlayer'] # 参加済みﾌﾟﾚｲﾔｰの辞書を取得
            nameList = list(jP.keys()) # 辞書から参加者の名前を取得
            for name in nameList:
                if(jP[name][1] != None): #jP[name][1]←サーバーに参加した時刻が入る（退出時はNoneになっている）
                    online += name + ' '
            if(online == ''): online = '今は誰もいません'

            result_msg += '状態　　 : 稼働中\n'
            result_msg += '起動者　 : ' + svStatus['whoStarted'] + '\n'
            result_msg += '起動時刻 : ' + startTime + '\n'
            result_msg += '稼働時間 : ' + workingTime + '\n'
            result_msg += '参加中　 : ' + online
            result_msg += '```'
            await interaction.response.send_message(result_msg)
        else:
            # 停止中
            await interaction.response.send_message(result_msg_close) # モーダルを開く関数呼び出し
    else:
        # 停止中
        await interaction.response.send_message(result_msg_close) # モーダルを開く関数呼び出し


# ■【7.】バックアップリストを表示するスラッシュコマンド
@tree.command(name='mcsv-checkbackup', description='バックアップを一覧表示する')
async def mcsvcheckbackup(interaction: discord.Interaction):
    # ------------------------------
    print(f'/mcsv-checkbackup が実行された')
    result_msg = '```【バックアップ一覧】\n'
    # ------------------------------

    # ディレクトリをリストで取得し、文字列に整形
    backups = os.listdir(backup_dir)
    for b in backups:
        result_msg += b + '\n'

    result_msg += '```'
    print(result_msg)
    await interaction.response.send_message(result_msg)


# ■【8.】botとのDM
@client.event
async def on_message(message):
    # メッセージ送信者がBotだった場合は無視する
    if message.author.bot:
        return

    global thread
    # メッセージが発生したチャンネルを判別
    if (str(message.channel.id) in operatorID):
        command = str(message.content)
        byte = command.encode() + b'\n'
        print(f'byte: {byte}')
        print(f'BotにDMが届いた！ [{command}]')

        # サーバーが稼働中か確認
        if(thread != 'default'):
            print(f'thread.is_alive(): {thread.is_alive()}')
            if(thread.is_alive()):
                # サーバースレッドがTrue→起動中
                try:
                    # 非同期処理の書き方が分からないので、stopコマンドは使えないようにする
                    if(command == 'stop'):
                        await message.channel.send('ここではstopコマンドは禁止されています')
                    else: # stop以外のコマンドなら許す
                        process.stdin.write(byte)
                        process.stdin.flush()
                except Exception as e:
                    await message.channel.send(f'```{command} >>> 送信失敗```')
                else:
                    await message.channel.send(f'```{command} >>> 送信成功```')
            else:
                # サーバースレッドがFalse→停止中
                await message.channel.send(f'```{command} >>> 現在サーバーは停止中です```')

        else:
            # process == 'default'→停止中
            await message.channel.send(f'```{command} >>> 現在サーバーは停止中です```')

    else:
        return


# ------------------------------
# ↑ ツリーコマンド
# ↓ discordボットの初期化処理
# ------------------------------


@client.event
async def on_ready():
    await tree.sync() # ツリーコマンドを同期
    print('Bot起動')

# discordボット起動
client.run(os.getenv("DISCORD_TOKEN"))