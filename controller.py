# 241107_2356
# 機能
# 1. /mcsv-run       サーバー起動    （スラッシュコマンドのみで実装）
# 2. /mcsv-stop      サーバー停止    （スラッシュコマンドのみで実装）
# 3. /mcsv-backup    サーバーのバックアップ作成  （スラッシュコマンド→モーダルで実装）
# 4. /mcsv-restore   サーバーの復元  （スラッシュコマンド→モーダルで実装）
# 5. /mcsv-logs      サーバーログの直近30行を取得して表示する
# 6. /mcsv-status    サーバーの状態を取得する
# 7. /mcsv-checkbackup バックアップ一覧を表示
# 8. botにDMを送信    サーバーOPコマンドを実行する

import discord
from discord import app_commands
from discord.ext import tasks
import os
from dotenv import load_dotenv
from discord import ui # フォーム作成に必要
import re # splitを使うため
import subprocess # .batファイルを実行したりするために必要
import threading # サーバーを開いたとき、プロセスをサーバーが占有してしまうため非同期処理が適している
import re # バリデーション処理を行う為に必要
import shutil # ファイルをコピーするために必要
import datetime as dt
import logging

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
logChannelID = os.getenv("1304403751901331476") # ログを出力するテキストチャンネルのID
logTarget = client.get_channel(logChannelID)    # ログを出力するテキストチャンネルのｵﾌﾞｼﾞｪｸﾄ

# ディレクトリ定義
# 作業ディレクトリに関連するエラーが発生して面倒なので、作業ディレクトリをこのスクリプトの場所に固定する
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
# 同じ階層にサーバーファイルを配置
svbat_path = "run.bat"           # マイクラのサーバーを起動させるバッチファイルのパス
svworking_dir = "./sv"           # マイクラサーバーの？作業ディレクトリ
svlog_path = "../svlog.txt"        # マイクラサーバーのログをここに出力
server_dir = "."                 # コピー元（サーバーが置かれている場所）
backup_dir = "../__backups/"     # コピー先（バックアップの保存先）

# バックアップ作成時に無視するファイル
ignore = ['controller.py', '.env']

# サーバーの状態を格納する変数
svStatus = dict(
    isRunning = False,
    startTime = None, #サーバーが起動した時刻
    workingTime = 0, #[minute]
    startBy = '',
)

# discordからサーバーのopコマンドを実行できる人（discordのDMのチャンネルIDとする）
# opコマンドは、このbotとのDMで行うことにする
operatorID = [
    os.getenv("DISCORD_CHANNELID_DR"),    # 自分
    # os.getenv("DISCORD_CHANNELID_YA")     # 友人代表
]

# discordからbotスラッシュコマンドを実行できる人（discordユーザID）
commanderID = [
    os.getenv("DISCORD_USERID_DR"),    # 自分
    os.getenv("DISCORD_USERID_YA")     # 友人代表
]

thread = 'default'

# ------------------------------
# ↑ 変数定義
# ↓ モーダルフォーム
# ------------------------------
class McsvBackup(ui.Modal, title='バックアップを生成'):
    def __init__(self, svStatus):
        super().__init__()

    # 入力欄により格納される値
    input_backupDescription = ui.TextInput(label='バックアップの名前', placeholder='例）●●突撃前、▲▲完了時', required=True, max_length=30, default=None) # バックアップの説明（フォルダ名の一部になる）

    # モーダルが送信されたとき
    """流れ
    1. 入力値のバリデーション
    2. フォルダ名を「現在時刻+入力文字」としてフォルダを生成 成功↓ 失敗→
    3. 作成したフォルダにコピーする 成功↓ 失敗→
    4. サーバー
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
            # ------------------------------
            # 3. 現在のサーバーファイルを削除
            print(f'存在')
        else:
            result_msg += '>>> 入力値: ' + self.input_backupName.value + '\n'
            result_msg += '>>> 入力されたバックアップ名は存在しません\n'
            error_count += 1

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
# ↑ モーダルフォーム
# ↓ ツリーコマンド
# ------------------------------


# 【0.】ログを出力する関数
async def sendLog(text):
    log = 'ログです'
    await logTarget.send(log)



# 【1.】サーバーを起動するスラッシュコマンド
@tree.command(name='mcsv-run', description='マイクラサーバーを起動する')
async def mcsvRun(interaction: discord.Interaction):
    # ------------------------------
    print(f'/mcsv-run が実行された')
    result_msg = '```【サーバー起動】\n'
    error_count = 0        
    global process
    global thread
    # ------------------------------
    # 権限確認
    print(f'コマンド実行者  {interaction.user.name}: {interaction.user.id}')
    if str(interaction.user.id) in commanderID:
        # 非同期処理の定義？
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
                    print('mcsv >>> ' + line.decode('utf-8'), end='')
                    # with open(svlog_path, 'a', encoding='utf-8') as f: # a: 追記モード
                    #     f.write('>>> ' + str(line) + '\n')
                except Exception as e:
                    print('mcsv >>> デコード失敗', end='')

        try:
            # マイクラサーバー用のスレッドを立てる
            thread = threading.Thread(target=print_log, name='mcserver', daemon=True)
            thread.start()
        except Exception as e:
            result_msg += '>>> スレッド起動失敗\n'
            error_count += 1

        # 起動しているかを確認して状態変数を更新
        if(process.poll() == None):
            result_msg += '>>> サーバー起動を確認\n'
            svStatus['isRunning'] = True
            svStatus['startTime'] = dt.datetime.now().strftime("%y%m%d_%H%M")
        else:
            error_count += 1
            svStatus['isRunning'] = False
        
        # 処理に成功したか判断
        if(error_count == 0):
            result_msg += '>>> 成功しました\n'
            result_msg += '実行者　　 : ' + str(interaction.user.name) + '\n'
        else:
            result_msg += '>>> 失敗しました\nもう一度やり直してください\n'
    else:
        result_msg += '>>> コマンド実行権限がありません'
    
    
    result_msg += '```'        
    print(result_msg)
    await interaction.response.send_message(result_msg)
    return process


# 【2.】サーバーを停止するスラッシュコマンド
@tree.command(name='mcsv-stop', description='マイクラサーバー停止')
async def mcsvstop(interaction: discord.Interaction):
    # ------------------------------
    print(f'/mcsv-stop が実行された')
    result_msg = '```【サーバー停止】\n'
    error_count = 0    
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
                # True→起動中
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
            else:
                # False→停止中
                result_msg += '>>> 既にサーバーは停止しています\n'
        else:
            # thread == 'default'→停止中（まだ一度も起動していない状態）
            result_msg += '>>> 既にサーバーは停止しています\n'
        
        # 処理に成功したか判断
        if(error_count == 0):
            result_msg += '>>> 成功しました\n'
            result_msg += '実行者　　 : ' + str(interaction.user.name) + '\n'
        else:
            result_msg += '>>> 失敗しました\n'
    else:
        result_msg += '>>> コマンド実行権限がありません'

    result_msg += '```'        
    print(result_msg)
    await interaction.response.send_message(result_msg)


# 【3.】バックアップ生成モーダルを呼び出すスラッシュコマンド
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



    
# 【4.】サーバーを復元するモーダルを呼び出すスラッシュコマンド
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
        await interaction.response.send_message('```【バックアップから復元】\n>>> コマンド実行権限がありません```') # モーダルを開く関数呼び出し   



# 【6.】サーバーの状態を表示するスラッシュコマンド
@tree.command(name='mcsv-status', description='サーバーの状態を確認する')
async def mcsvstatus(interaction: discord.Interaction):
    # ------------------------------
    # ------------------------------

    # result_msg = ''
    # if(svStatus['isRunning']):
    #     result_msg += '- 稼働中\n'
    #     result_msg += '- 起動時刻: ' + svStatus['startTime'] + '\n'
    #     result_msg += '- 稼働時間: ' + svStatus['workingTime'] + '\n'
    #     result_msg += '- 起動者　: ' + svStatus['startBy'] + '\n'
    # else:
    #     result_msg += '- 停止中\n'
    
    await interaction.response.send_message(
        '```～このコマンドは開発中です～```'
    )


#【7.】バックアップリストを表示するスラッシュコマンド
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


# # 【8-1】サーバーにコマンドを送信する関数
# async def svOpStop():
#     print('svOpStopが実行された')
#     global process
#     global thread
#     try:
#         process.stdin.write(b'stop\n') # 停止コマンドを送信
#         process.stdin.flush() # バッファにたまっているデータを強制的に送信
#     except Exception as e:
#         result_msg += '>>> 停止命令の送信に失敗\n'
#         error_count += 1
#     else: # 停止コマンドの送信に成功した時に実行
#         process.kill() # プロセスを終了
#         print(f'thread.is_alive(): {thread.is_alive()}')
#         thread.join()  # スレッド終了を待つ
#         print(f'thread.is_alive(): {thread.is_alive()}')
#     await None

# 【8.】botとのDM
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
                    # stopコマンドの場合サーバーが停止し、スレッドがのこったままになるので、止めてあげる　×
                    # 非同期処理の書き方が分からないので、stopコマンドは使えないようにする
                    if(command == 'stop'):
                        # svOpStop()
                        # await message.channel.send(f'```{command} >>> stopコマンド送信済み```')
                        await message.channel.send('ここではstopコマンドは禁止されています')
                    else:
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
            try:
                process.stdin.write(byte)
                process.stdin.flush()
            except Exception as e:
                await message.channel.send(f'```{command} >>> 送信失敗```')
            else:
                await message.channel.send(f'```{command} >>> 送信成功```')


        
    else:
        return




# ------------------------------
# ↓ discordボットの初期化処理
# ------------------------------
@client.event
async def on_ready():
    # ツリーコマンドを同期
    await tree.sync()
    print('Bot起動')


# discordボット起動
client.run(os.getenv("DISCORD_TOKEN"))