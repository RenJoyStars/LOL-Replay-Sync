"""
 LOL 对局文件自动上传客户端
===============================
功能：
  1. 登录 / 注册（连接你的服务器）
  2. 选择英雄联盟对局文件（.rolf）所在文件夹
  3. 监视文件夹变化，新文件自动上传

启动方式（用 CMD 运行）：
  pip install PySide6 requests watchdog
  python client.py

打包成 exe（给朋友用）：
  在 Windows 上运行 build.bat
"""

import sys
import os
import json
import time
import threading
import hashlib
import base64
from datetime import datetime
from pathlib import Path

import requests

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit,
    QFileDialog, QTabWidget, QMessageBox, QGroupBox,
    QCheckBox, QListWidget, QListWidgetItem, QFrame,
    QDialog, QDialogButtonBox, QSystemTrayIcon, QMenu
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QObject, Slot
from PySide6.QtGui import QFont, QIcon, QTextCursor, QAction, QPixmap


# ============================
# 深色/浅色模式自动适配
# ============================


# ============================
# 🔧 配置（你需要改这个！）
# ============================
SERVER_URL = "http://175.178.183.14:5050"  # ← 云服务器地址

# ============================
#  设置文件路径（存用户登录信息）
# ============================
CONFIG_DIR = Path.home() / ".lol_uploader"
CONFIG_FILE = CONFIG_DIR / "config.json"
os.makedirs(CONFIG_DIR, exist_ok=True)


# ============================
# 💾 设置读写
# ============================
def load_config():
    """读取本地保存的设置"""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return data
        except:
            pass
    return {"token": "", "username": "", "watch_folder": "", "lol_path": ""}

def save_config(config):
    """保存设置到本地"""
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================
# .rolf 文件解析
# ============================
def parse_rolf_metadata(filepath):
    """解析 .rolf 文件的元数据信息"""
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
        
        # .rolf 文件结构：魔数(4B) + 版本(4B) + JSON长度(4B) + JSON数据
        if len(data) < 12:
            return None
        
        magic = data[0:4]
        if magic not in (b'RLFR', b'RFLR'):
            return None  # 不是合法的 .rolf 文件
        
        json_len = int.from_bytes(data[8:12], 'little')
        if json_len <= 0 or json_len > len(data) - 12:
            return None
        
        metadata = json.loads(data[12:12+json_len].decode('utf-8', errors='replace'))
        
        # 提取有用信息
        info = {}
        
        # 游戏信息
        info['game_version'] = metadata.get('gameVersion', '未知')
        info['game_type'] = metadata.get('gameType', '未知')
        
        # 对局时间
        game_date = metadata.get('gameDate', '')
        if game_date:
            try:
                dt = datetime.fromisoformat(game_date.replace('Z', '+00:00'))
                info['game_time'] = dt.strftime('%Y-%m-%d %H:%M')
            except:
                info['game_time'] = game_date
        else:
            info['game_time'] = '未知'
        
        # 地图
        map_names = {11: '召唤师峡谷', 12: '嚎哭深渊', 30: '扭曲丛林', 
                     21: '统治战场', 14: '屠夫之桥', 33: '云顶之弈',
                     1020: '斗魂竞技场'}
        info['map'] = map_names.get(metadata.get('mapId', 0), f'地图{metadata.get("mapId", "?")}')
        
        # 对局时长
        info['game_length'] = metadata.get('gameLength', 0)
        
        # 游戏模式
        game_mode = metadata.get('gameMode', '')
        mode_names = {
            'CLASSIC': '经典模式', 'ARAM': '极地大乱斗', 'TFT': '云顶之弈',
            'ARENA': '斗魂竞技场', 'PRACTICETOOL': '训练模式',
            'URF': '无限火力', 'NEXUSBLITZ': '极限闪击',
            'ONEFORALL': '克隆模式', 'DOOMBOTSTEEMO': '末日人机'
        }
        info['game_mode'] = mode_names.get(game_mode, game_mode if game_mode else '未知')
        
        # 队列类型
        queue_types = {
            400: '单双排', 420: '单双排', 430: '匹配',
            440: '灵活排', 450: '极地大乱斗', 700: '组排',
            800: '云顶之弈', 900: '云顶之弈', 1020: '斗魂竞技场'
        }
        info['queue'] = queue_types.get(metadata.get('queueId', 0), '其他')
        
        # 玩家列表
        players = []
        for p in metadata.get('players', []):
            champion = p.get('championName', '') or p.get('championId', '')
            name = p.get('name', '未知') or p.get('summonerName', '未知')
            players.append({'name': name, 'champion': champion})
        
        info['players'] = players
        info['player_count'] = len(players)
        
        # 文件信息
        info['file_size_mb'] = round(os.path.getsize(filepath) / (1024*1024), 1)
        info['file_mtime'] = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%H:%M:%S')
        
        return info
    except Exception as e:
        return None


# 英雄联盟英雄名 英→中 对照表
CHAMPION_CN = {
    "Aatrox": "暗裔剑魔", "Ahri": "九尾妖狐", "Akali": "离群之刺",
    "Akshan": "影哨", "Alistar": "牛头酋长", "Amumu": "殇之木乃伊",
    "Anivia": "冰晶凤凰", "Annie": "黑暗之女", "Aphelios": "残月之肃",
    "Ashe": "寒冰射手", "AurelionSol": "铸星龙王", "Azir": "沙漠皇帝",
    "Bard": "星界游神", "Belveth": "不灭狂舞", "Blitzcrank": "蒸汽机器人",
    "Brand": "复仇焰魂", "Braum": "弗雷尔卓德之心", "Caitlyn": "皮城女警",
    "Camille": "青钢影", "Cassiopeia": "魔蛇之拥", "Chogath": "虚空恐惧",
    "Corki": "英勇投弹手", "Darius": "诺克萨斯之手", "Diana": "皎月女神",
    "Draven": "荣耀行刑官", "DrMundo": "祖安狂人", "Ekko": "时间刺客",
    "Elise": "蜘蛛女皇", "Evelynn": "痛苦之拥", "Ezreal": "探险家",
    "Fiddlesticks": "远古恐惧", "Fiora": "无双剑姬", "Fizz": "潮汐海灵",
    "Galio": "正义巨像", "Gangplank": "海洋之灾", "Garen": "德玛西亚之力",
    "Gnar": "迷失之牙", "Gragas": "酒桶", "Graves": "法外狂徒",
    "Gwen": "灵罗娃娃", "Hecarim": "战争之影", "Heimerdinger": "大发明家",
    "Illaoi": "海兽祭司", "Irelia": "刀锋舞者", "Ivern": "翠神",
    "Janna": "风暴之怒", "JarvanIV": "德玛西亚皇子", "Jax": "武器大师",
    "Jayce": "未来守护者", "Jhin": "戏命师", "Jinx": "暴走萝莉",
    "KaiSa": "虚空之女", "Kalista": "复仇之矛", "Karma": "天启者",
    "Karthus": "死亡颂唱者", "Kassadin": "虚空行者", "Katarina": "不祥之刃",
    "Kayle": "正义天使", "Kayn": "影流之镰", "Kennen": "狂暴之心",
    "Khazix": "虚空掠夺者", "Kindred": "永猎双子", "Kled": "暴怒骑士",
    "KogMaw": "深渊巨口", "LeBlanc": "诡术妖姬", "LeeSin": "盲僧",
    "Leona": "曙光女神", "Lillia": "含羞蓓蕾", "Lilia": "含羞蓓蕾", "Lissandra": "冰霜女巫",
    "Lucian": "圣枪游侠", "Lulu": "仙灵女巫", "Lux": "光辉女郎",
    "Malphite": "熔岩巨兽", "Malzahar": "虚空先知", "Maokai": "扭曲树精",
    "MasterYi": "无极剑圣", "MissFortune": "赏金猎人", "Mordekaiser": "铁铠冥魂",
    "Morgana": "堕落天使", "Nami": "唤潮鲛姬", "Nasus": "沙漠死神",
    "Nautilus": "深海泰坦", "Neeko": "万花通灵", "Nidalee": "狂野女猎手",
    "Nilah": "不羁之悦", "Nocturne": "永恒梦魇", "Nunu": "雪原双子",
    "Olaf": "狂战士", "Orianna": "发条魔灵", "Ornn": "山隐之焰",
    "Pantheon": "不屈之枪", "Poppy": "圣锤之毅", "Pyke": "血港鬼影",
    "Qiyana": "元素女皇", "Quinn": "德玛西亚之翼", "Rakan": "幻翎",
    "Rammus": "披甲龙龟", "RekSai": "虚空遁地兽", "Rell": "熔铁少女",
    "Renata": "烈娜塔", "Renekton": "荒漠屠夫", "Rengar": "傲之追猎者",
    "Riven": "放逐之刃", "Rumble": "机械公敌", "Ryze": "符文法师",
    "Samira": "沙漠玫瑰", "Sejuani": "凛冬之怒", "Senna": "涤魂圣枪",
    "Seraphine": "星籁歌姬", "Sett": "腕豪", "Shaco": "恶魔小丑",
    "Shen": "暮光之眼", "Shyvana": "龙血武姬", "Singed": "炼金术士",
    "Sion": "亡灵战神", "Sivir": "战争女神", "Skarner": "水晶先锋",
    "Sona": "琴瑟仙女", "Soraka": "众星之子", "Swain": "诺克萨斯统领",
    "Sylas": "解脱者", "Syndra": "暗黑元首", "TahmKench": "河流之王",
    "Taliyah": "岩雀", "Talon": "刀锋之影", "Taric": "瓦洛兰之盾",
    "Teemo": "迅捷斥候", "Thresh": "魂锁典狱长", "Tristana": "麦林炮手",
    "Trundle": "巨魔之王", "Tryndamere": "蛮族之王", "TwistedFate": "卡牌大师",
    "Twitch": "瘟疫之源", "Udyr": "兽灵行者", "Urgot": "无畏战车",
    "Varus": "惩戒之箭", "Vayne": "暗夜猎手", "Veigar": "邪恶小法师",
    "Velkoz": "虚空之眼", "Vex": "愁云使者", "Vi": "皮城执法官",
    "Viego": "破败之王", "Viktor": "机械先驱", "Vladimir": "猩红收割者",
    "Volibear": "不灭狂雷", "Warwick": "祖安怒兽", "Wukong": "齐天大圣",
    "Xayah": "逆羽", "Xerath": "远古巫灵", "XinZhao": "德邦总管",
    "Yasuo": "疾风剑豪", "Yone": "封魔剑魂", "Yorick": "牧魂人",
    "Yuumi": "魔法猫咪", "Zac": "生化魔人", "Zed": "影流之主",
    "Zeri": "祖安火花", "Ziggs": "爆破鬼才", "Zilean": "时光守护者",
    "Zoe": "暮光星灵", "Zyra": "荆棘之兴",
}
def champ_cn(name):
    """英雄英文名转中文"""
    return CHAMPION_CN.get(name, name)


def detect_lol_version(lol_path):
    """检测 LOL 客户端版本号"""
    if not lol_path or not os.path.isdir(lol_path) and not (sys.platform == "darwin" and lol_path.endswith(".app") and os.path.exists(lol_path)):
        return None
    try:
        if sys.platform == "darwin":
            # Mac: 进入 Contents/LoL/LeagueClient.app/Contents/Info.plist
            for base in [lol_path]:
                # 如果选的是 .app，进去找 LeagueClient
                inner = os.path.join(base, "Contents", "LoL", "LeagueClient.app", "Contents", "Info.plist")
                if os.path.exists(inner):
                    import plistlib
                    with open(inner, "rb") as f:
                        plist = plistlib.load(f)
                    ver = plist.get("CFBundleShortVersionString")
                    if ver:
                        return ver
                # fallback: 外层的 Info.plist
                outer = os.path.join(base, "Contents", "Info.plist")
                if os.path.exists(outer):
                    import plistlib
                    with open(outer, "rb") as f:
                        plist = plistlib.load(f)
                    ver = plist.get("CFBundleShortVersionString")
                    if ver:
                        return ver.split(" ")[0]
        elif sys.platform == "win32":
            import subprocess
            for exe in ["LeagueClient.exe"]:
                exe_path = os.path.join(lol_path, exe)
                if os.path.exists(exe_path):
                    result = subprocess.run(
                        ["powershell", "-Command",
                         f"(Get-Item '{exe_path}').VersionInfo.ProductVersion"],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        ver = result.stdout.strip()
                        if ver:
                            return ver
    except Exception:
        pass
    return None


# ============================
# 应用图标（Base64 嵌入，无需外部文件）
# ============================
APP_ICON_B64 = """
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
2v5RAAAAAElFTkSuQmCC
"""



def auto_rename_rolf(filepath):
    """根据 .rolf 文件的对局时间自动重命名"""
    try:
        meta = parse_rolf_metadata(filepath)
        if not meta or not meta.get('game_time') or meta['game_time'] == '未知':
            return None
        
        # 从 '2025-06-08 20:30' 提取日期
        date_str = meta['game_time']
        parts = date_str.split(' ')[0].split('-')
        if len(parts) == 3:
            new_name = f"{parts[0]}.{int(parts[1])}.{int(parts[2])}.rofl"
            folder = os.path.dirname(filepath)
            new_path = os.path.join(folder, new_name)
            
            # 如果新文件名已存在，在后面加序号
            if os.path.exists(new_path):
                base = new_name[:-5]
                for i in range(2, 100):
                    new_path = os.path.join(folder, f"{base}_{i}.rofl")
                    if not os.path.exists(new_path):
                        break
            
            os.rename(filepath, new_path)
            return new_path, new_name
        return None
    except Exception as e:
        return None


# ============================
# 与服务器通信
# ============================
class ServerAPI:
    """处理所有和服务器的请求"""

    @staticmethod
    def check_server():
        """检查服务器是否在线"""
        try:
            r = requests.get(f"{SERVER_URL}/", timeout=3)
            return r.status_code == 200
        except:
            return False

    @staticmethod
    def get_captcha_config():
        """获取服务器验证码配置"""
        try:
            r = requests.get(f"{SERVER_URL}/captcha/config", timeout=5)
            data = r.json()
            return data.get("enabled", False), data.get("aid", "")
        except:
            return False, ""

    @staticmethod
    def register(username, password, ticket="", randstr=""):
        """注册新用户"""
        try:
            payload = {"username": username, "password": password}
            if ticket:
                payload["ticket"] = ticket
                payload["randstr"] = randstr
            r = requests.post(
                f"{SERVER_URL}/register",
                json=payload,
                timeout=10
            )
            data = r.json()
            return r.status_code == 201, data.get("message", data.get("error", "未知错误"))
        except requests.exceptions.ConnectionError:
            return False, "无法连接到服务器，请检查地址"
        except Exception as e:
            return False, f"网络错误：{str(e)}"

    @staticmethod
    def login(username, password, ticket="", randstr=""):
        """用户登录"""
        try:
            payload = {"username": username, "password": password}
            if ticket:
                payload["ticket"] = ticket
                payload["randstr"] = randstr
            r = requests.post(
                f"{SERVER_URL}/login",
                json=payload,
                timeout=10
            )
            data = r.json()
            if r.status_code == 200:
                return True, data
            else:
                return False, data.get("error", "登录失败")
        except requests.exceptions.ConnectionError:
            return False, "无法连接到服务器"
        except Exception as e:
            return False, f"网络错误：{str(e)}"

    @staticmethod
    def upload_file(filepath, token):
        """上传单个文件"""
        try:
            filename = os.path.basename(filepath)
            with open(filepath, "rb") as f:
                files = {"file": (filename, f)}
                headers = {"Authorization": f"Bearer {token}"}
                r = requests.post(
                    f"{SERVER_URL}/upload",
                    files=files,
                    headers=headers,
                    timeout=60  # 大文件可能需要更长时间
                )
            data = r.json()
            return r.status_code == 200, data
        except Exception as e:
            return False, {"error": str(e)}

    @staticmethod
    def list_uploaded_files(token):
        """获取已上传的文件列表"""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            r = requests.get(f"{SERVER_URL}/files", headers=headers, timeout=10)
            data = r.json()
            if r.status_code == 200:
                return data.get("files", [])
            return []
        except:
            return []

    @staticmethod
    def download_file(filename, token, save_path):
        """从服务器下载文件"""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            r = requests.get(
                f"{SERVER_URL}/download/{filename}",
                headers=headers,
                timeout=30,
                stream=True
            )
            if r.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(r.content)
                return True, save_path
            else:
                try:
                    err = r.json().get("error", "下载失败")
                except:
                    err = r.text[:100]
                return False, err
        except Exception as e:
            return False, str(e)

    @staticmethod
    def rename_file(old_name, new_name, token):
        """重命名服务器上的文件"""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            r = requests.post(
                f"{SERVER_URL}/rename/{old_name}",
                json={"new_name": new_name},
                headers=headers,
                timeout=10
            )
            data = r.json()
            if r.status_code == 200:
                return True, data.get("new_name", new_name)
            return False, data.get("error", "重命名失败")
        except Exception as e:
            return False, str(e)

    @staticmethod
    def delete_file(filename, token):
        """删除服务器上的文件"""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            r = requests.delete(
                f"{SERVER_URL}/delete/{filename}",
                headers=headers,
                timeout=10
            )
            data = r.json()
            if r.status_code == 200:
                return True, data.get("message", "删除成功")
            return False, data.get("error", "删除失败")
        except Exception as e:
            return False, str(e)

    @staticmethod
    def change_password(old_pw, new_pw, token):
        """修改密码"""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            r = requests.post(
                f"{SERVER_URL}/user/change_password",
                json={"old_password": old_pw, "new_password": new_pw},
                headers=headers,
                timeout=10
            )
            data = r.json()
            return r.status_code == 200, data.get("message", data.get("error", "操作失败"))
        except Exception as e:
            return False, str(e)

    @staticmethod
    def get_user_info(token):
        """获取用户信息（含昵称）"""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            r = requests.get(f"{SERVER_URL}/user/info", headers=headers, timeout=10)
            data = r.json()
            return r.status_code == 200, data
        except Exception as e:
            return False, str(e)

    @staticmethod
    def change_nickname(nickname, token):
        """修改昵称"""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            r = requests.post(
                f"{SERVER_URL}/user/change_nickname",
                json={"nickname": nickname},
                headers=headers,
                timeout=10
            )
            data = r.json()
            return r.status_code == 200, data.get("nickname", nickname)
        except Exception as e:
            return False, str(e)


class LoginWindow(QWidget):
    """登录/注册界面"""
    login_success = Signal(str, str)  # 发送 (token, username)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("英雄联盟对局文件助手")
        self.setFixedSize(460, 520)
        self.setup_ui()
        
        
        # 自动填充保存的密码
        config = load_config()
        saved_user = config.get("username", "")
        saved_pw = config.get("password", "")
        auto_login = config.get("auto_login", False)
        if saved_user:
            self.username_input.setText(saved_user)
        if saved_pw:
            self.password_input.setText(saved_pw)
            self.remember_cb.setChecked(True)
        if auto_login and saved_user and saved_pw:
            self.auto_login_cb.setChecked(True)
            # 延迟一点自动触发登录
            from PySide6.QtCore import QTimer
            QTimer.singleShot(300, self.do_auto_login)

    def setup_ui(self):
        # 整体背景色
        self.setStyleSheet("""
            QWidget {
                background-color: #f5f7fa;
                color: #2d3748;
            }
            QLineEdit { color: #2d3748; background-color: #f7fafc; }
            QLabel { color: #2d3748; }
            QCheckBox { color: #4a5568; }
            QPushButton { color: white; }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ===== 顶部渐变色块 =====
        header = QWidget()
        header.setFixedHeight(96)
        header.setStyleSheet("""
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #1a1a2e,
                stop:0.5 #16213e,
                stop:1 #0f3460
            );
        """)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 6)
        header_layout.setSpacing(0)

        # 大标题 + 服务器地址合并显示（确保零间距）
        combined = QLabel(
            "<div style='text-align:center; line-height:1.1;'>"
            "<span style='font-size:22px; font-weight:bold; color:white;'>英雄联盟对局文件助手</span><br>"
            f"<span style='font-size:12px; color:#a0aec0;'>服务器地址：{SERVER_URL}</span>"
            "</div>"
        )
        combined.setAlignment(Qt.AlignCenter)
        combined.setStyleSheet("background: transparent;")
        header_layout.addWidget(combined)

        layout.addWidget(header)

        # ===== 表单区域（白色卡片） =====
        form_container = QWidget()
        form_container.setStyleSheet("background-color: white;")
        form_layout = QVBoxLayout(form_container)
        form_layout.setSpacing(14)
        form_layout.setContentsMargins(30, 40, 30, 20)

        # 用户名
        username_label = QLabel("用户名")
        username_label.setStyleSheet("color: #4a5568; font-size: 13px; font-weight: bold; background: transparent;")
        form_layout.addWidget(username_label)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("输入用户名（至少2个字符）")
        from PySide6.QtGui import QRegularExpressionValidator
        from PySide6.QtCore import QRegularExpression
        self.username_input.setValidator(QRegularExpressionValidator(QRegularExpression(r"[^\s]*")))
        self.username_input.setStyleSheet("""
            QLineEdit {
                border: 2px solid #e2e8f0;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 14px;
                background-color: #f7fafc;
                color: #2d3748;
            }
            QLineEdit:focus {
                border: 2px solid #4299e1;
                background-color: white;
            }
        """)
        self.username_input.setFixedHeight(42)
        self.username_input.returnPressed.connect(self.do_login)
        form_layout.addWidget(self.username_input)

        form_layout.addSpacing(10)

        # 密码
        password_label = QLabel("密码")
        password_label.setStyleSheet("color: #4a5568; font-size: 13px; font-weight: bold; background: transparent;")
        form_layout.addWidget(password_label)

        # 密码输入框 + 眼睛按钮
        pw_row = QHBoxLayout()
        pw_row.setSpacing(0)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("输入密码（至少6个字符）")
        self.password_input.setEchoMode(QLineEdit.Password)
        from PySide6.QtGui import QRegularExpressionValidator
        from PySide6.QtCore import QRegularExpression
        self.password_input.setValidator(QRegularExpressionValidator(QRegularExpression(r"[^\s]*")))
        self.password_input.setStyleSheet("""
            QLineEdit {
                border: 2px solid #e2e8f0;
                border-top-left-radius: 8px;
                border-bottom-left-radius: 8px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                padding: 10px 14px;
                font-size: 14px;
                background-color: #f7fafc;
                color: #2d3748;
            }
            QLineEdit:focus {
                border: 2px solid #4299e1;
                border-right: none;
                background-color: white;
            }
        """)
        self.password_input.setFixedHeight(42)
        self.password_input.returnPressed.connect(self.do_login)

        # 眼睛按钮（按住显示密码，松开隐藏）
        self.eye_btn = QPushButton("◉")
        self.eye_btn.setFixedSize(44, 42)
        self.eye_btn.setCursor(Qt.PointingHandCursor)
        self.eye_btn.setStyleSheet("""
            QPushButton {
                background-color: #edf2f7;
                border: 2px solid #cbd5e0;
                border-left: none;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                font-size: 18px;
                color: #4a5568;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
                border-color: #a0aec0;
            }
            QPushButton:pressed {
                background-color: #bee3f8;
                border-color: #4299e1;
                color: #2b6cb0;
            }
        """)
        # 密码框聚焦时同步改变眼睛图标边框
        orig_focus_in = self.password_input.focusInEvent
        def _on_pw_focus(event):
            self.eye_btn.setStyleSheet(self.eye_btn.styleSheet()
                .replace('border: 2px solid #cbd5e0;', 'border: 2px solid #4299e1;')
                .replace('background-color: #edf2f7;', 'background-color: white;'))
            if orig_focus_in:
                orig_focus_in(event)
        self.password_input.focusInEvent = _on_pw_focus
        self.eye_btn.pressed.connect(lambda: self.password_input.setEchoMode(QLineEdit.Normal))
        self.eye_btn.released.connect(lambda: self.password_input.setEchoMode(QLineEdit.Password))

        pw_row.addWidget(self.password_input, 1)
        pw_row.addWidget(self.eye_btn)
        form_layout.addLayout(pw_row)

        form_layout.addSpacing(16)

        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.login_btn = QPushButton("登  录")
        self.login_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4299e1,
                    stop:1 #3182ce
                );
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3182ce,
                    stop:1 #2b6cb0
                );
            }
            QPushButton:pressed {
                background: #2b6cb0;
            }
        """)
        self.login_btn.setFixedHeight(42)
        self.login_btn.clicked.connect(self.do_login)
        btn_layout.addWidget(self.login_btn)

        self.register_btn = QPushButton("注  册")
        self.register_btn.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: #4299e1;
                border: 2px solid #4299e1;
                border-radius: 8px;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ebf8ff;
            }
            QPushButton:pressed {
                background-color: #bee3f8;
            }
        """)
        self.register_btn.setFixedHeight(42)
        self.register_btn.clicked.connect(self.do_register)
        btn_layout.addWidget(self.register_btn)

        form_layout.addLayout(btn_layout)

        form_layout.addSpacing(8)

        # 检查服务器
        self.check_server_btn = QPushButton("测试服务器连接")
        self.check_server_btn.setStyleSheet("""
            QPushButton {
                background-color: #edf2f7;
                color: #4a5568;
                border: none;
                border-radius: 8px;
                padding: 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
        """)
        self.check_server_btn.setFixedHeight(38)
        self.check_server_btn.clicked.connect(self.check_server)
        form_layout.addWidget(self.check_server_btn)

        # 记住密码 + 自动登录
        check_layout = QHBoxLayout()
        check_layout.setSpacing(4)
        self.remember_cb = QCheckBox("记住密码")
        self.remember_cb.setStyleSheet("""
            QCheckBox { color: #4a5568; font-size: 12px; spacing: 6px; background: transparent; }
            QCheckBox::indicator { width: 16px; height: 16px;
                border: 2px solid #4299e1; border-radius: 4px; background: white; }
            QCheckBox::indicator:checked { background-color: #4299e1; border-color: #3182ce; }
        """)
        self.auto_login_cb = QCheckBox("自动登录")
        self.auto_login_cb.setStyleSheet("""
            QCheckBox { color: #4a5568; font-size: 12px; spacing: 6px; background: transparent; }
            QCheckBox::indicator { width: 16px; height: 16px;
                border: 2px solid #4299e1; border-radius: 4px; background: white; }
            QCheckBox::indicator:checked { background-color: #4299e1; border-color: #3182ce; }
        """)
        # 勾选自动登录时自动勾选记住密码
        self.auto_login_cb.toggled.connect(
            lambda checked: self.remember_cb.setChecked(True) if checked else None
        )
        check_layout.addWidget(self.remember_cb)
        check_layout.addStretch()
        check_layout.addWidget(self.auto_login_cb)
        form_layout.addLayout(check_layout)

        # 状态信息（居中在测试按钮和底部之间）
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("background: transparent; font-size: 12px;")
        self.status_label.setFixedHeight(20)
        form_layout.addStretch(1)
        form_layout.addWidget(self.status_label)
        form_layout.addStretch(1)

        layout.addWidget(form_container, 1)

        # ===== 底部 =====
        footer = QLabel("v0.2 test · Made By Joy")
        footer.setAlignment(Qt.AlignCenter)
        footer.setFixedHeight(36)
        footer.setStyleSheet("""
            color: #a0aec0;
            font-size: 12px;
            background-color: #f5f7fa;
        """)
        layout.addWidget(footer)

        self.setLayout(layout)

    def check_server(self):
        """测试服务器连接"""
        self.status_label.setStyleSheet("color: blue;")
        self.status_label.setText("正在检查服务器连接...")
        QApplication.processEvents()
        
        ok = ServerAPI.check_server()
        if ok:
            self.status_label.setStyleSheet("color: green;")
            self.status_label.setText("服务器连接正常！")
        else:
            self.status_label.setStyleSheet("color: red;")
            self.status_label.setText(f"无法连接服务器\n请检查地址：{SERVER_URL}")

    def do_login(self):
        """处理登录"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            self.status_label.setStyleSheet("color: red;")
            self.status_label.setText("请输入用户名和密码")
            return
        
        if ' ' in username or ' ' in password:
            self.status_label.setStyleSheet("color: red;")
            self.status_label.setText("用户名和密码不能包含空格")
            return

        # 验证码验证
        captcha_enabled, captcha_aid = ServerAPI.get_captcha_config()
        ticket, randstr = "", ""
        # 自动登录跳过验证码
        if getattr(self, '_skip_captcha', False):
            captcha_enabled = False
        if captcha_enabled:
            cap_result = launch_captcha_webkit(self)
            if cap_result.get("ticket"):
                ticket = cap_result["ticket"]; randstr = cap_result.get("randstr", "")
            else:
                self.status_label.setStyleSheet("color: red;")
                self.status_label.setText("验证取消")
                return

        self.status_label.setStyleSheet("color: blue;")
        self.status_label.setText("正在登录...")
        self.login_btn.setEnabled(False)
        self.register_btn.setEnabled(False)
        QApplication.processEvents()

        success, result = ServerAPI.login(username, password, ticket, randstr)
        
        self.login_btn.setEnabled(True)
        self.register_btn.setEnabled(True)

        if success:
            self.status_label.setStyleSheet("color: green;")
            self.status_label.setText(f"登录成功！欢迎 {result['username']}")
            # 保存登录设置
            config = load_config()
            config["username"] = username
            config["token"] = result["token"]
            if self.remember_cb.isChecked():
                config["password"] = password
            else:
                config.pop("password", None)
            config["auto_login"] = self.auto_login_cb.isChecked()
            save_config(config)
            # 立即进入主页面
            self.login_success.emit(result["token"], result["username"])
        else:
            self.status_label.setStyleSheet("color: red;")
            self.status_label.setText(f"{result}")

    def do_auto_login(self):
        """自动登录（跳过验证码）"""
        config = load_config()
        username = config.get("username", "")
        password = config.get("password", "")
        token = config.get("token", "")
        if username and password and token:
            # 已有 token，直接进入主页
            self.login_success.emit(token, username)
        elif username and password:
            self.username_input.setText(username)
            self.password_input.setText(password)
            # 自动登录，跳过验证码
            self._skip_captcha = True
            self.do_login()
        else:
            self.username_input.setText(username or "")

    def do_register(self):
        """处理注册"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            self.status_label.setStyleSheet("color: red;")
            self.status_label.setText("请输入用户名和密码")
            return
        
        if ' ' in username or ' ' in password:
            self.status_label.setStyleSheet("color: red;")
            self.status_label.setText("用户名和密码不能包含空格")
            return
        if len(username) < 2:
            self.status_label.setText("用户名至少2个字符")
            return
        if len(password) < 6:
            self.status_label.setText("密码至少6个字符")
            return

        # 验证码验证
        # 验证码验证
        captcha_enabled, captcha_aid = ServerAPI.get_captcha_config()
        ticket, randstr = "", ""
        if captcha_enabled:
            cap_result = launch_captcha_webkit(self)
            if cap_result.get("ticket"):
                ticket = cap_result["ticket"]; randstr = cap_result.get("randstr", "")
            else:
                self.status_label.setStyleSheet("color: red;")
                self.status_label.setText("验证取消")
                return

        self.status_label.setStyleSheet("color: blue;")
        self.status_label.setText("正在注册...")
        self.login_btn.setEnabled(False)
        self.register_btn.setEnabled(False)
        QApplication.processEvents()

        success, message = ServerAPI.register(username, password, ticket, randstr)
        
        self.login_btn.setEnabled(True)
        self.register_btn.setEnabled(True)

        if success:
            self.status_label.setStyleSheet("color: green;")
            self.status_label.setText(f"{message}，现在登录吧！")



def launch_captcha_webkit(parent=None):
    """弹出腾讯云验证码 —— 独立子进程运行，QTimer 非阻塞轮询结果
    Mac: WKWebView (captcha_webkit.py)
    Win: Edge WebView2 (captcha_win.py)
    """
    import os, platform, tempfile
    from urllib.parse import unquote
    from PySide6.QtCore import QTimer, QEventLoop
    
    is_mac = platform.system() == "Darwin"
    script_name = "captcha_webkit.py" if is_mac else "captcha_win.py"
    result_file = "/tmp/captcha_result.txt" if is_mac else os.path.join(tempfile.gettempdir(), "lol_captcha_result.txt")
    
    script_path = os.path.join(os.path.dirname(__file__), script_name)
    if not os.path.exists(script_path) and getattr(sys, 'frozen', False):
        script_path = os.path.join(os.path.dirname(sys.executable), script_name)
    if not os.path.exists(script_path):
        QMessageBox.critical(parent, "错误", f"验证码内核文件缺失 ({script_name})")
        return {"ticket": "", "randstr": ""}
    
    if os.path.exists(result_file):
        os.remove(result_file)
    
    result = {"ticket": "", "randstr": ""}
    
    # 启子进程 — 用当前 Python（pywebview 已安装在系统 Python）
    import subprocess
    py_bin = sys.executable
    proc = subprocess.Popen([py_bin, script_path],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # QTimer 非阻塞轮询
    loop = QEventLoop()
    elapsed = [0]
    
    def check():
        elapsed[0] += 100
        if os.path.exists(result_file):
            try:
                with open(result_file) as f:
                    data = f.read().strip()
                if data:
                    parts = data.split("&")
                    for p in parts:
                        if "=" in p:
                            k, v = p.split("=", 1)
                            v = unquote(v) if "%" in v else v
                            if k == "ticket": result["ticket"] = v
                            elif k == "randstr": result["randstr"] = v
            except:
                pass
            loop.quit()
        elif elapsed[0] >= 120000:  # 2 分钟超时
            loop.quit()
        elif proc.poll() is not None and elapsed[0] > 2000:
            # 进程退出但没结果文件 → 用户关了窗口
            loop.quit()
    
    timer = QTimer()
    timer.timeout.connect(check)
    timer.start(100)
    
    loop.exec()
    
    timer.stop()
    # 捕获子进程错误
    if proc.poll() is not None and proc.returncode != 0:
        err = proc.stderr.read().decode(errors='replace')[:500]
        if err.strip():
            QMessageBox.critical(parent, "验证码错误", f"子进程异常退出 (code={proc.returncode}):\n{err}")
    if proc.poll() is None:
        proc.kill()
        proc.wait()
    try:
        os.remove(result_file)
    except:
        pass
    
    if not result.get("ticket") and elapsed[0] >= 120000:
        QMessageBox.warning(parent, "超时", "验证码验证超时，请重试")
    
    return result


def rich_tooltip(widget, text):
    """自定义悬浮提示（白底黑字，macOS兼容）"""
    widget.setProperty("tip_text", text)
    widget._tip_label = None

    # 重写 enterEvent 和 leaveEvent
    orig_enter = widget.enterEvent
    orig_leave = widget.leaveEvent

    def on_enter(e):
        tl = QLabel(text, widget.window())
        tl.setWindowFlags(Qt.ToolTip)
        tl.setStyleSheet("""
            background-color: #ffffff;
            color: #2d3748;
            border: 1px solid #cbd5e0;
            border-radius: 4px;
            padding: 6px 10px;
            font-size: 11px;
        """)
        tl.adjustSize()
        # 定位到按钮右下方
        global_pos = widget.mapToGlobal(widget.rect().topRight())
        tl.move(global_pos.x() + 4, global_pos.y())
        tl.show()
        widget._tip_label = tl
        if orig_enter:
            orig_enter(e)

    def on_leave(e):
        if widget._tip_label:
            widget._tip_label.hide()
            widget._tip_label.deleteLater()
            widget._tip_label = None
        if orig_leave:
            orig_leave(e)

    widget.enterEvent = on_enter
    widget.leaveEvent = on_leave



class MainWindow(QWidget):
    """登录后的主界面"""
    # 退出时回调，由 main() 设置
    _on_logout = None

    def __init__(self, token, username):
        super().__init__()
        self.token = token
        self.username = username
        self.nickname = username  # 默认显示用户名
        self.config = load_config()
        self.lol_path = self.config.get("lol_path", "")
        self.lol_version = None
        self.lol_version_display = None

        self.setWindowTitle(f"英雄联盟对局文件助手 - {username}")
        self.setFixedSize(620, 640)
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint)
        self.setup_ui()

        # 异步获取昵称
        QTimer.singleShot(100, self.load_nickname)


        # 恢复上次保存的文件夹
        saved_folder = self.config.get("watch_folder", "")
        if saved_folder and os.path.isdir(saved_folder):
            self.folder_display.setText(saved_folder)
            self.current_folder = saved_folder
            self.add_log(f"使用上次的文件夹：{saved_folder}")
        else:
            self.select_folder()

        # 恢复 LOL 客户端路径
        saved_lol = self.config.get("lol_path", "")
        if saved_lol and os.path.isdir(saved_lol):
            self.lol_path = saved_lol
            ver = detect_lol_version(saved_lol)
            if ver:
                self.lol_version = ver
                if hasattr(self, 'lol_display'):
                    self.lol_display.setText(saved_lol)
                    self.lol_ver_label.setText(f"游戏版本: {ver}")
                    self.lol_ver_label.setStyleSheet("color: #48bb78; font-size: 11px; padding-left: 2px; background: transparent;")
        
        # 自动搜索常用路径（如果还没设置）
        if not self.lol_path or not os.path.isdir(self.lol_path):
            self._auto_search_lol()
        if not hasattr(self, 'current_folder') or not self.current_folder or not os.path.isdir(self.current_folder):
            self._auto_search_replay()

        # 系统托盘
        self.setup_tray()


    def setup_ui(self):
        # 整体背景
        self.setStyleSheet("""
            QWidget {
                background-color: #f5f7fa;
                color: #2d3748;
            }
            QLineEdit { color: #2d3748; background-color: #f7fafc; }
            QLabel { color: #2d3748; }
            QCheckBox { color: #4a5568; }
            QPushButton { color: white; }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ===== 顶部栏 =====
        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet("""
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #1a1a2e,
                stop:1 #16213e
            );

        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 8, 16, 8)

        self.user_label = QPushButton(f"{self.nickname}")
        user_font = QFont()
        user_font.setPointSize(12)
        user_font.setBold(True)
        self.user_label.setFont(user_font)
        self.user_label.setStyleSheet("""
            QPushButton {
                background-color: rgba(255,255,255,0.1);
                color: #e2e8f0;
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.2);
                color: white;
            }
        """)
        self.user_label.setCursor(Qt.PointingHandCursor)
        self.user_label.clicked.connect(self.show_user_settings)

        self.logout_btn = QPushButton("退出登录")
        self.logout_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255,255,255,0.1);
                color: #e2e8f0;
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.2);
            }
        """)
        self.logout_btn.clicked.connect(self.logout)

        # 云端管理按钮
        self.file_mgr_btn = QPushButton("云端管理")
        self.file_mgr_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255,255,255,0.1);
                color: #e2e8f0;
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.2);
            }
        """)
        self.file_mgr_btn.clicked.connect(self.show_file_manager)

        header_layout.addWidget(self.user_label)
        header_layout.addStretch()
        header_layout.addSpacing(10)
        header_layout.addWidget(self.file_mgr_btn)
        header_layout.addWidget(self.logout_btn)
        layout.addWidget(header)

        # ===== 内容区域 =====
        content = QWidget()
        content.setStyleSheet("background-color: #f5f7fa;")
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(10)
        content_layout.setContentsMargins(20, 12, 20, 12)

        # ===== 文件夹选择 =====
        folder_card = QFrame()
        folder_card.setStyleSheet("background: transparent; border: none;")
        folder_card_layout = QVBoxLayout(folder_card)
        folder_card_layout.setContentsMargins(0, 0, 0, 0)
        folder_card_layout.setSpacing(8)

        folder_title = QLabel("回放文件目录")
        folder_title.setStyleSheet("color: #2d3748; font-size: 14px; font-weight: bold; background: transparent;")
        folder_card_layout.addWidget(folder_title)

        folder_row = QHBoxLayout()

        self.folder_display = QLabel("尚未选择文件夹")
        self.folder_display.setStyleSheet("""
            background-color: #f7fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 10px 14px;
            color: #4a5568;
            font-size: 13px;
        """)
        self.folder_display.setWordWrap(True)

        self.select_btn = QPushButton("浏览...")
        self.select_btn.setStyleSheet("""
            QPushButton {
                background-color: #edf2f7;
                color: #4a5568;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
            }
        """)
        self.select_btn.setFixedHeight(42)
        self.select_btn.clicked.connect(self.select_folder)

        folder_row.addWidget(self.folder_display, 1)
        folder_row.addWidget(self.select_btn)
        folder_card_layout.addLayout(folder_row)

        folder_card_layout.addSpacing(8)

        # 提示文字
        tip = QLabel("英雄联盟默认对局文件存放位置：")
        tip.setStyleSheet("color: #a0aec0; font-size: 11px; background: transparent; padding-left: 2px;")
        folder_card_layout.addWidget(tip)

        tip2 = QLabel("Windows: C:\\Users\\你的用户名\\Documents\\League of Legends\\Replays")
        tip2.setStyleSheet("color: #718096; font-size: 11px; padding: 2px 4px;")
        folder_card_layout.addWidget(tip2)

        tip3 = QLabel("Mac: ~/Documents/League of Legends/Replays")
        tip3.setStyleSheet("color: #718096; font-size: 11px; padding: 2px 4px;")
        folder_card_layout.addWidget(tip3)

        folder_card_layout.addSpacing(4)
        content_layout.addWidget(folder_card)

        # ===== LOL 客户端目录 =====
        lol_card = QFrame()
        lol_card.setStyleSheet("background: transparent; border: none;")
        lol_layout = QVBoxLayout(lol_card)
        lol_layout.setContentsMargins(0, 0, 0, 0)
        lol_layout.setSpacing(6)

        lol_title = QLabel("客户端目录")
        lol_title.setStyleSheet("color: #2d3748; font-size: 14px; font-weight: bold; background: transparent;")
        lol_layout.addWidget(lol_title)

        lol_row = QHBoxLayout()
        self.lol_display = QLabel("尚未选择（回放功能需要）")
        self.lol_display.setStyleSheet("background-color: #f7fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px; color: #4a5568; font-size: 13px;")
        self.lol_display.setWordWrap(True)

        self.lol_btn = QPushButton("浏览...")
        self.lol_btn.setStyleSheet("""QPushButton { background-color: #edf2f7; color: #4a5568; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 20px; font-size: 13px; font-weight: bold; } QPushButton:hover { background-color: #e2e8f0; }""")
        self.lol_btn.setFixedHeight(42)
        self.lol_btn.clicked.connect(self.select_lol_folder)

        lol_row.addWidget(self.lol_display, 1)
        lol_row.addWidget(self.lol_btn)
        lol_layout.addLayout(lol_row)

        self.lol_ver_label = QLabel("游戏版本: 未设置")
        self.lol_ver_label.setStyleSheet("color: #d69e2e; font-size: 11px; padding-left: 2px; background: transparent;")
        lol_layout.addWidget(self.lol_ver_label)

        # LOL 客户端路径提示
        lol_tip = QLabel("英雄联盟客户端默认安装位置：")
        lol_tip.setStyleSheet("color: #a0aec0; font-size: 11px; background: transparent; padding-left: 2px;")
        lol_layout.addWidget(lol_tip)
        lol_tip2 = QLabel("Windows: C:\\Program Files\\WeGameApps\\英雄联盟 (WeGame国服默认路径)")
        lol_tip2.setStyleSheet("color: #718096; font-size: 11px; padding: 2px 4px;")
        lol_layout.addWidget(lol_tip2)
        lol_tip3 = QLabel("Mac: /Applications/League of Legends.app")
        lol_tip3.setStyleSheet("color: #718096; font-size: 11px; padding: 2px 4px;")
        lol_layout.addWidget(lol_tip3)

        lol_layout.addSpacing(4)
        content_layout.addWidget(lol_card)

        # ===== 开始同步按钮（无框） =====
        self.start_btn = QPushButton("开始同步")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #48bb78,
                    stop:1 #38a169
                );
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 32px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #38a169,
                    stop:1 #2f855a
                );
            }
        """)
        self.start_btn.setFixedHeight(44)
        self.start_btn.clicked.connect(self.toggle_sync)
        content_layout.addWidget(self.start_btn)

        content_layout.addSpacing(16)

        # ===== 日志区域 =====
        log_header = QHBoxLayout()
        log_title = QLabel("上传日志")
        log_title.setStyleSheet("color: #2d3748; font-size: 14px; font-weight: bold; background: transparent;")
        log_header.addWidget(log_title)
        log_header.addStretch()

        clear_btn = QPushButton("清空")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #fed7d7;
                color: #e53e3e;
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #feb2b2;
            }
        """)
        clear_btn.clicked.connect(lambda: self.log_area.clear())
        log_header.addWidget(clear_btn)

        # 导出日志
        export_btn = QPushButton("导出")
        export_btn.setStyleSheet("""
            QPushButton {
                background-color: #bee3f8;
                color: #2b6cb0;
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #90cdf4;
            }
        """)
        def do_export():
            log_text = self.log_area.toPlainText()
            if not log_text.strip():
                return
            file_path, _ = QFileDialog.getSaveFileName(
                self, "导出日志", f"sync_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                "文本文件 (*.txt);;所有文件 (*)"
            )
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("英雄联盟对局文件助手 - 同步日志\n")
                    f.write(f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("=" * 50 + "\n\n")
                    f.write(log_text)
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(self, "导出成功", f"日志已保存到：\n{file_path}")
        export_btn.clicked.connect(do_export)
        log_header.addSpacing(4)
        log_header.addWidget(export_btn)
        log_header.addSpacing(4)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("""
            QTextEdit {
                background-color: #1a202c;
                color: #68d391;
                border: 1px solid #2d3748;
                border-radius: 8px;
                padding: 10px;
                font-family: "SF Mono", "Menlo", "Consolas", monospace;
                font-size: 12px;
            }
        """)

        content_layout.addLayout(log_header)
        content_layout.addWidget(self.log_area, 1)

        layout.addWidget(content, 1)
        self.setLayout(layout)

        # 初始日志
        self.add_log("英雄联盟对局文件助手已启动")
        self.add_log(f"用户：{self.username}")
        self.add_log(f"服务器：{SERVER_URL}")
        self.add_log("━━━━━━━━━━━━━━━━━━━━")
        self.add_log("请选择文件夹，点击「开始同步」上传 .rolf 文件")


    def setup_tray(self):
        """设置系统托盘"""
        self.tray_icon = QSystemTrayIcon(self)
        pix = QPixmap()
        pix.loadFromData(base64.b64decode(APP_ICON_B64))
        self.tray_icon.setIcon(QIcon(pix))
        self.tray_icon.setToolTip(f"英雄联盟对局文件助手 - {self.username}")

        # 右键菜单
        tray_menu = QMenu()
        show_action = QAction("显示窗口", self)
        show_action.triggered.connect(self.show_and_raise)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)

        # 左键双击显示窗口
        self.tray_icon.activated.connect(
            lambda reason: self.show_and_raise() if reason == QSystemTrayIcon.DoubleClick else None
        )
        self.tray_icon.show()

    def show_and_raise(self):
        """显示并激活窗口"""
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        """关闭时最小化到托盘而不是退出"""
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "英雄联盟对局文件助手",
            "程序已最小化到系统托盘，双击图标恢复窗口",
            QSystemTrayIcon.Information,
            2000
        )

    def quit_app(self):
        """真正退出程序"""
        self.tray_icon.hide()
        self.close()
        QApplication.quit()

    def select_folder(self):
        """选择文件夹"""
        folder = QFileDialog.getExistingDirectory(
            self, "选择 LOL 对局文件文件夹"
        )
        if folder:
            self.folder_display.setText(folder)
            self.current_folder = folder
            self.add_log(f"已选择文件夹：{folder}")
            # 保存设置
            self.config["watch_folder"] = folder
            save_config(self.config)

    def select_lol_folder(self):
        """选择 LOL 客户端目录，检测版本（macOS 允许选 .app 包）"""
        import platform
        if platform.system() == "Darwin":
            path, _ = QFileDialog.getOpenFileName(
                self, "选择英雄联盟 .app 文件（如 League of Legends.app）",
                "/Applications",
                "应用程序 (*.app);;所有文件 (*)"
            )
            # 也允许直接选目录
            if not path:
                path = QFileDialog.getExistingDirectory(
                    self, "或选择英雄联盟客户端所在目录"
                )
        else:
            path = QFileDialog.getExistingDirectory(
                self, "选择英雄联盟客户端所在目录"
            )
        if not path:
            return
        self.lol_path = path
        self.config["lol_path"] = path
        save_config(self.config)
        ver = detect_lol_version(path)
        if ver:
            self.lol_version = ver
            self.lol_display.setText(path)
            self.lol_ver_label.setText(f"游戏版本: {ver}")
            self.lol_ver_label.setStyleSheet("color: #48bb78; font-size: 11px; padding-left: 2px; background: transparent;")
            self.add_log(f"LOL 客户端版本：{ver}")
        else:
            self.lol_version = None
            self.lol_display.setText(path)
            self.lol_ver_label.setText("游戏版本: 无法识别")
            self.lol_ver_label.setStyleSheet("color: #e53e3e; font-size: 11px; padding-left: 2px; background: transparent;")
            self.add_log(f"LOL 目录已选，但读不到版本：{path}")

    def _auto_search_lol(self):
        """自动搜索常见的 LOL 客户端安装路径"""
        common_paths = []
        if sys.platform == "darwin":
            common_paths = [
                "/Applications/League of Legends.app",
                os.path.expanduser("~/Applications/League of Legends.app"),
                "/Applications/WeChatGame/League of Legends.app",
            ]
        elif sys.platform == "win32":
            common_paths = [
                "C:\\Program Files\\WeGame\\league_of_legends",
                "C:\\Riot Games\\League of Legends",
                os.path.expanduser("~\\AppData\\Local\\Riot Games\\League of Legends"),
            ]
        for p in common_paths:
            if os.path.isdir(p):
                self.lol_path = p
                self.config["lol_path"] = p
                save_config(self.config)
                ver = detect_lol_version(p)
                if ver:
                    self.lol_version = ver
                    if hasattr(self, 'lol_display'):
                        self.lol_display.setText(p)
                        self.lol_ver_label.setText(f"游戏版本: {ver}")
                        self.lol_ver_label.setStyleSheet("color: #48bb78; font-size: 11px; padding-left: 2px; background: transparent;")
                        self.add_log(f"自动检测到 LOL 客户端：{ver}")
                break

    def _auto_search_replay(self):
        """自动搜索常见的回放文件存放路径"""
        common_paths = []
        if sys.platform == "darwin":
            common_paths = [
                os.path.expanduser("~/Documents/League of Legends/Replays"),
                os.path.expanduser("~/Documents/League of Legends/Replays/"),
            ]
        elif sys.platform == "win32":
            common_paths = [
                os.path.expanduser("~\\Documents\\League of Legends\\Replays"),
                "C:\\Program Files\\WeGame\\league_of_legends\\Replays",
            ]
        for p in common_paths:
            if os.path.isdir(p):
                self.current_folder = p
                self.folder_display.setText(p)
                self.config["watch_folder"] = p
                save_config(self.config)
                self.add_log(f"自动检测到回放目录：{p}")
                break

    def toggle_sync(self):
        """开始同步 — 对比本地和云端，上传缺失文件"""
        if not hasattr(self, 'current_folder') or not self.current_folder:
            QMessageBox.warning(self, "提示", "请先选择一个文件夹！")
            return

        self.start_btn.setEnabled(False)
        self.start_btn.setText("同步中...")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ecc94b,
                    stop:1 #d69e2e
                );
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 32px;
                font-size: 15px;
                font-weight: bold;
            }
        """)

        self.add_log("━━━━━━━━━━━━━━━━━━━━━")
        self.add_log("开始同步对局文件...")

        try:
            # 1. 获取本地 .rolf 文件
            local_rolf = []
            if os.path.isdir(self.current_folder):
                for f in os.listdir(self.current_folder):
                    if f.lower().endswith(".rolf") or f.lower().endswith(".rofl"):
                        local_rolf.append(f)
            self.add_log(f"本地找到 {len(local_rolf)} 个 .rolf 文件")

            # 2. 获取云端已上传文件列表
            uploaded = ServerAPI.list_uploaded_files(self.token)
            uploaded_names = {f["filename"] for f in uploaded}
            self.add_log(f"云端已有 {len(uploaded)} 个文件")

            # 3. 找出需要上传的本地文件
            to_upload = [f for f in local_rolf if f not in uploaded_names]
            if to_upload:
                total = len(to_upload)
                self.add_log(f"需要上传 {total} 个文件...")
                for idx, fname in enumerate(to_upload, 1):
                    fpath = os.path.join(self.current_folder, fname)
                    if not os.path.exists(fpath):
                        continue
                    # 获取文件大小
                    fsize = os.path.getsize(fpath)
                    size_str = f"{fsize/1024/1024:.1f}MB" if fsize > 1024*1024 else f"{fsize/1024:.1f}KB"
                    meta = parse_rolf_metadata(fpath)
                    if meta:
                        info_parts = []
                        if meta.get('map'): info_parts.append(meta['map'])
                        if meta.get('game_mode'): info_parts.append(meta['game_mode'])
                        if meta.get('players'): info_parts.append(f"{len(meta['players'])}人")
                        if meta['game_length'] and meta['game_length'] > 0:
                            info_parts.append(f"{int(meta['game_length'])//60}分")
                        self.add_log(f"  [{idx}/{total}] 上传 {fname} ({size_str})  {' | '.join(info_parts)}")
                    else:
                        self.add_log(f"  [{idx}/{total}] 上传 {fname} ({size_str})")
                    self.start_btn.setText(f"同步中 {idx}/{total}")
                    QApplication.processEvents()
                    ok, result = ServerAPI.upload_file(fpath, self.token)
                    if ok:
                        self.add_log(f"  [OK] [{idx}/{total}] 同步成功: {fname}")
                    else:
                        err = result.get('error', str(result)) if isinstance(result, dict) else str(result)
                        self.add_log(f"  [失败] [{idx}/{total}] 同步失败: {fname} - {err}")
                    QApplication.processEvents()

                self.add_log("本地文件同步完成")
            else:
                self.add_log("所有本地文件已同步，无需上传")
        finally:
            self.start_btn.setText("开始同步")
            self.start_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 #48bb78,
                        stop:1 #38a169
                    );
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 12px 32px;
                    font-size: 15px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 #38a169,
                        stop:1 #2f855a
                    );
                }
            """)
            self.start_btn.setEnabled(True)

    def add_log(self, message):
        """向日志区添加一条消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_area.append(f"[{timestamp}] {message}")
        cursor = self.log_area.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_area.setTextCursor(cursor)

    def update_status(self, text):
        pass

    def logout(self):
        """退出登录，返回登录界面（清除登录信息防死循环）"""
        self.config["token"] = ""
        self.config.pop("password", None)
        self.config["auto_login"] = False
        save_config(self.config)
        self.close()
        if MainWindow._on_logout:
            MainWindow._on_logout()

    
    

    def load_nickname(self):
        """从服务器加载昵称"""
        ok, data = ServerAPI.get_user_info(self.token)
        if ok and data.get("nickname"):
            self.nickname = data["nickname"]
            self.user_label.setText(f"{self.nickname}")

    def show_user_settings(self):
        """用户管理 — 修改昵称/密码"""
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
            QLabel, QLineEdit, QMessageBox, QGroupBox, QFormLayout)

        dialog = QDialog(self)
        dialog.setWindowTitle("用户管理")
        dialog.setMinimumWidth(380)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)

        info_label = QLabel(f'<b>当前用户：{self.username}</b>')
        info_label.setStyleSheet("font-size: 14px; color: #2d3748; padding: 8px;")
        layout.addWidget(info_label)

        # 修改昵称
        nick_group = QGroupBox("修改昵称")
        nick_layout = QVBoxLayout(nick_group)
        nick_input = QLineEdit()
        nick_input.setPlaceholderText("输入新昵称")
        nick_input.setFixedHeight(36)
        nick_input.setStyleSheet("padding: 8px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 13px;")
        nick_save = QPushButton("保存昵称")
        nick_save.setStyleSheet("""QPushButton { background-color: #4299e1; color: white; border: none;
            border-radius: 6px; padding: 8px; font-weight: bold; }
            QPushButton:hover { background-color: #3182ce; }""")
        def do_nick():
            name = nick_input.text().strip()
            if not name: return
            ok, result = ServerAPI.change_nickname(name, self.token)
            if ok:
                self.nickname = name
                self.user_label.setText(name)
                QMessageBox.information(dialog, "成功", f"昵称已改为：{result}")
            else:
                QMessageBox.warning(dialog, "失败", str(result))
        nick_save.clicked.connect(do_nick)
        nick_layout.addWidget(nick_input)
        nick_layout.addWidget(nick_save)
        layout.addWidget(nick_group)

        # 修改密码
        pw_group = QGroupBox("修改密码")
        pw_layout = QFormLayout(pw_group)
        pw_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        pw_layout.setSpacing(10)
        old_pw = QLineEdit()
        old_pw.setEchoMode(QLineEdit.Password)
        old_pw.setPlaceholderText("输入旧密码")
        old_pw.setFixedHeight(36)
        old_pw.setStyleSheet("padding: 8px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 13px;")
        new_pw = QLineEdit()
        new_pw.setEchoMode(QLineEdit.Password)
        new_pw.setPlaceholderText("输入新密码（至少6位）")
        new_pw.setFixedHeight(36)
        new_pw.setStyleSheet("padding: 8px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 13px;")
        pw_save = QPushButton("修改密码")
        pw_save.setStyleSheet("""QPushButton { background-color: #48bb78; color: white; border: none;
            border-radius: 6px; padding: 8px; font-weight: bold; }
            QPushButton:hover { background-color: #38a169; }""")
        def do_pw():
            if not old_pw.text() or not new_pw.text():
                QMessageBox.warning(dialog, "提示", "请填写旧密码和新密码")
                return
            if len(new_pw.text()) < 6:
                QMessageBox.warning(dialog, "提示", "新密码至少6位")
                return
            ok, result = ServerAPI.change_password(old_pw.text(), new_pw.text(), self.token)
            if ok:
                QMessageBox.information(dialog, "成功", "密码已修改！")
                old_pw.clear(); new_pw.clear()
            else:
                QMessageBox.warning(dialog, "失败", str(result))
        pw_save.clicked.connect(do_pw)
        pw_layout.addRow("旧密码:", old_pw)
        pw_layout.addRow("新密码:", new_pw)
        pw_layout.addRow(pw_save)
        layout.addWidget(pw_group)
        layout.addStretch()
        dialog.exec()

    def show_file_manager(self):
        """云端管理"""
        try:
            from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
                QListWidgetItem, QPushButton, QLabel, QMessageBox, QFileDialog, QWidget,
                QAbstractItemView, QInputDialog, QCheckBox, QComboBox, QDateEdit)

            dialog = QDialog()
            dialog.setWindowTitle("云端管理")
            dialog.setFixedSize(780, 540)
            dialog.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
            dialog.setStyleSheet("QDialog { background-color: #f5f7fa; }")
            layout = QVBoxLayout(dialog)

            # 顶部栏
            top = QHBoxLayout()
            title = QLabel("  云端文件管理  ")
            title.setStyleSheet("font-size: 14px; font-weight: bold; color: #2d3748; padding: 8px;")
            top.addWidget(title)
            top.addStretch()
            
            batch_del = QPushButton("删除选中")
            batch_del.setStyleSheet("""QPushButton { background-color: #f56565; color: white; border: none;
                border-radius: 6px; padding: 8px 16px; font-size: 12px; font-weight: bold; }
                QPushButton:disabled { background-color: #e2e8f0; color: #a0aec0; }""")
            batch_del.setEnabled(False)
            sel_all = QPushButton("全选")
            sel_all.setStyleSheet("""QPushButton { background-color: #4299e1; color: white; border: none;
                border-radius: 6px; padding: 8px 16px; font-size: 12px; font-weight: bold; }""")

            # 一键下载
            batch_dl = QPushButton("一键下载")
            batch_dl.setStyleSheet("""QPushButton { background-color: #48bb78; color: white; border: none;
                border-radius: 6px; padding: 8px 16px; font-size: 12px; font-weight: bold; }
                QPushButton:disabled { background-color: #e2e8f0; color: #a0aec0; }""")

            uploaded = ServerAPI.list_uploaded_files(self.token)
            fnames = sorted([f["filename"] for f in uploaded], reverse=True)
            finfo = {f["filename"]: f for f in uploaded}
            local_set = set()
            if hasattr(self, 'current_folder') and self.current_folder and os.path.isdir(self.current_folder):
                for f in os.listdir(self.current_folder):
                    if f.lower().endswith(".rolf") or f.lower().endswith(".rofl"):
                        local_set.add(f)

            def do_batch_download():
                if not hasattr(self, 'current_folder') or not self.current_folder:
                    QMessageBox.warning(dialog, "提示", "请先在主界面选择对局文件所在文件夹")
                    return
                if not os.path.isdir(self.current_folder):
                    QMessageBox.warning(dialog, "提示", "主界面选定的文件夹不存在")
                    return
                missing = [f for f in fnames if f not in local_set]
                if not missing:
                    QMessageBox.information(dialog, "提示", "所有文件已下载到本地")
                    return
                batch_dl.setEnabled(False)
                success = 0
                for fn in missing:
                    sp = os.path.join(self.current_folder, fn)
                    ok, _ = ServerAPI.download_file(fn, self.token, sp)
                    if ok:
                        success += 1
                batch_dl.setEnabled(True)
                QMessageBox.information(dialog, "完成", f"已下载 {success}/{len(missing)} 个文件到：\n{self.current_folder}")
                dialog.close()
                self.show_file_manager()

            batch_dl.clicked.connect(do_batch_download)

            top.addWidget(batch_dl)
            top.addSpacing(6)
            top.addWidget(batch_del)
            top.addSpacing(6)
            top.addWidget(sel_all)
            layout.addLayout(top)

            # ===== 筛选栏 =====
            filter_bar = QHBoxLayout()
            filter_bar.setSpacing(8)
            all_modes = set()
            all_vers = set()
            for fn in fnames:
                fp = os.path.join(self.current_folder, fn) if hasattr(self, 'current_folder') and self.current_folder else ""
                m = parse_rolf_metadata(fp) if fp and os.path.exists(fp) else None
                if m:
                    gv = m.get("game_version", "")
                    gm = m.get("game_mode", "")
                    if gv: all_vers.add(gv)
                    if gm: all_modes.add(gm)
            flt_label = QLabel("筛选：")
            flt_label.setStyleSheet("color: #4a5568; font-size: 12px; font-weight: bold; padding-left: 8px;")
            filter_bar.addWidget(flt_label)
            self.mode_filter = QComboBox()
            self.mode_filter.addItem("全部模式")
            for m in sorted(all_modes): self.mode_filter.addItem(m)
            self.mode_filter.setStyleSheet("padding: 3px 8px; border: 1px solid #e2e8f0; border-radius: 4px;")
            self.mode_filter.setFixedWidth(120)
            filter_bar.addWidget(self.mode_filter)
            self.ver_filter = QComboBox()
            self.ver_filter.addItem("全部版本")
            for v in sorted(all_vers, reverse=True): self.ver_filter.addItem(v)
            self.ver_filter.setStyleSheet("padding: 3px 8px; border: 1px solid #e2e8f0; border-radius: 4px;")
            self.ver_filter.setFixedWidth(140)
            filter_bar.addWidget(self.ver_filter)
            
            # 日期筛选
            from PySide6.QtCore import QDate
            self.date_from = QDateEdit()
            self.date_from.setCalendarPopup(True)
            self.date_from.setDate(QDate.currentDate().addYears(-1))
            self.date_from.setDisplayFormat("yyyy-MM-dd")
            self.date_from.setStyleSheet("padding: 2px 6px; border: 1px solid #e2e8f0; border-radius: 4px;")
            self.date_from.setFixedWidth(130)
            self.date_from.setSpecialValueText("起始日期")
            date_sep = QLabel(" ~ ")
            date_sep.setStyleSheet("color: #a0aec0; font-size: 12px;")
            self.date_to = QDateEdit()
            self.date_to.setCalendarPopup(True)
            self.date_to.setDate(QDate.currentDate())
            self.date_to.setDisplayFormat("yyyy-MM-dd")
            self.date_to.setStyleSheet("padding: 2px 6px; border: 1px solid #e2e8f0; border-radius: 4px;")
            self.date_to.setFixedWidth(130)
            self.date_to.setSpecialValueText("结束日期")
            
            filter_bar.addSpacing(10)
            filter_bar.addWidget(self.date_from)
            filter_bar.addWidget(date_sep)
            filter_bar.addWidget(self.date_to)
            filter_bar.addStretch()
            layout.addLayout(filter_bar)

            file_list = QListWidget()
            file_list.setStyleSheet("""QListWidget { border: 1px solid #e2e8f0; border-radius: 8px;
                font-size: 12px; outline: none; background-color: white; }
                QListWidget::item { border-bottom: 1px solid #f0f0f0; padding: 0px; }""")
            file_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
            file_list.setSelectionMode(QAbstractItemView.NoSelection)
            file_list.setFocusPolicy(Qt.NoFocus)
            layout.addWidget(file_list, 1)

            checked = [False] * len(fnames)
            sel_all.setEnabled(len(fnames) > 0)
            batch_del.setEnabled(False)

            for row, fname in enumerate(fnames):
                local_path = os.path.join(self.current_folder, fname) if hasattr(self, 'current_folder') and self.current_folder else ""
                local_ex = os.path.exists(local_path) if local_path else False
                meta = parse_rolf_metadata(local_path) if local_path and os.path.exists(local_path) else None

                w = QWidget()
                w.setStyleSheet("background: transparent;")
                wl = QVBoxLayout(w)
                wl.setContentsMargins(8, 2, 8, 2)
                wl.setSpacing(2)

                r1_widget = QWidget()
                r1_widget.setStyleSheet("background-color: #f0fff4; border-radius: 4px; padding: 2px 0px;")
                r1 = QHBoxLayout(r1_widget)
                r1.setContentsMargins(0, 2, 0, 2)
                r1.setSpacing(4)
                cb = QCheckBox()
                cb.setStyleSheet("""QCheckBox::indicator { width: 13px; height: 13px; 
                    border: 2px solid #4299e1; border-radius: 3px; background: white; }
                    QCheckBox::indicator:checked { background-color: #4299e1; }""")
                def cc(r):
                    def _(s):
                        checked[r] = s == 2
                        batch_del.setEnabled(any(checked))
                    return _
                cb.stateChanged.connect(cc(row))
                r1.addWidget(cb)
                nl = QLabel(f"<b>{fname}</b>")
                nl.setStyleSheet("color: #1a202c; font-size: 13px;")
                r1.addWidget(nl, 1)
                fs = finfo[fname].get('file_size', 0)
                if fs:
                    sk = round(fs/1024, 1)
                    sz = f"{sk}KB" if sk < 1000 else f"{round(sk/1024,1)}MB"
                    sl = QLabel(sz)
                    sl.setStyleSheet("color: #718096; font-size: 11px;")
                    r1.addWidget(sl)
                    r1.addSpacing(4)
                st = "✓ 已下载" if local_ex else "☁ 云端"
                sl2 = QLabel(st)
                sl2.setStyleSheet("""color: white; background-color: {}; font-size: 10px; font-weight: bold;
                    border-radius: 4px; padding: 2px 8px;""".format('#48bb78' if local_ex else '#a0aec0'))
                r1.addWidget(sl2)
                wl.addWidget(r1_widget)

                # 第二行：信息 + 英雄 + 按钮
                row2 = QVBoxLayout()
                row2.setContentsMargins(0, 0, 0, 0)
                row2.setSpacing(3)

                # 信息行
                if meta:
                    info_parts = []
                    if meta.get('game_time'):
                        info_parts.append(f"比赛时间：{meta['game_time'].split(' ')[0]}")
                    if meta.get('game_version'):
                        info_parts.append(f"版本：{meta['game_version']}")
                    if meta['game_length'] and meta['game_length'] > 0:
                        info_parts.append(f"时长：{int(meta['game_length'])//60}分钟")
                    if meta.get('map'):
                        info_parts.append(f"地图：{meta['map']}")
                    if meta.get('game_mode'):
                        info_parts.append(f"模式：{meta['game_mode']}")
                    if meta.get('queue'):
                        info_parts.append(f"队列：{meta['queue']}")
                    if info_parts:
                        iw = QWidget()
                        iw.setStyleSheet("background-color: #edf2f7; border-radius: 3px;")
                        il = QLabel("  ".join(info_parts))
                        il.setStyleSheet("color: #4a5568; font-size: 12px; padding: 3px 4px;")
                        iwl = QHBoxLayout(iw)
                        iwl.setContentsMargins(0, 0, 0, 0)
                        iwl.addWidget(il)
                        row2.addWidget(iw)

                    # 英雄信息
                    champs = [champ_cn(p['champion']) for p in meta['players'] if p.get('champion')]
                    if champs:
                        half = len(champs) // 2
                        blue = " ".join(champs[:half])
                        red = " ".join(champs[half:])
                        hr = QHBoxLayout()
                        hr.setSpacing(8)
                        cv = QVBoxLayout()
                        cv.setSpacing(3)
                        bl = QLabel(f'<span style="color:#3182ce;font-weight:bold">蓝方: {blue}</span>')
                        bl.setTextFormat(Qt.RichText)
                        bl.setStyleSheet("padding-left: 4px;")
                        cv.addWidget(bl)
                        rl = QLabel(f'<span style="color:#e53e3e;font-weight:bold">红方: {red}</span>')
                        rl.setTextFormat(Qt.RichText)
                        rl.setStyleSheet("padding-left: 4px;")
                        cv.addWidget(rl)
                        hr.addLayout(cv)
                        hr.addStretch(1)
                        row2.addLayout(hr)
                elif not local_ex:
                    il = QLabel("需下载后查看详情")
                    il.setStyleSheet("color: #718096; font-size: 12px; font-style: italic;")
                    row2.addWidget(il)

                # 按钮行（统一创建，所有文件都显示）
                hr_btns = QHBoxLayout()
                hr_btns.setSpacing(4)
                hr_btns.addStretch(1)
                for label, color, hover in [
                    ("另存为", "#48bb78", "#38a169"),
                    ("删除", "#f56565", "#e53e3e"),
                    ("重命名", "#4299e1", "#3182ce"),
                    ("回放", "#805ad5", "#6b46c1"),
                ]:
                    btn = QPushButton(label)
                    if label == "回放":
                        btn.setStyleSheet(f"QPushButton{{background:{color};color:white;border:none;border-radius:4px;padding:3px 12px;font-size:11px;}}QPushButton:hover{{background:{hover};}}QPushButton:disabled{{background:#a0aec0;color:#e2e8f0;}}")
                    else:
                        btn.setStyleSheet(f"QPushButton{{background:{color};color:white;border:none;border-radius:4px;padding:3px 12px;font-size:11px;}}QPushButton:hover{{background:{hover};}}")
                    btn.setFixedHeight(26)
                    if label == "另存为":
                        btn.clicked.connect(lambda *a, fn=fname: save_file(fn, self.token, dialog))
                    elif label == "删除":
                        btn.clicked.connect(lambda *a, fn=fname, r=row: del_file(fn, r, self.token, dialog))
                    elif label == "重命名":
                        btn.clicked.connect(lambda *a, fn=fname: rename_file(fn, self.token, dialog))
                    elif label == "回放":
                        btn.clicked.connect(lambda *a, fn=fname, m=meta: play_replay(fn, m, self))
                        if meta is None or not meta.get("game_version"):
                            btn.setEnabled(False)
                            rich_tooltip(btn, "需先下载查看版本信息")
                        elif hasattr(self, 'lol_version') and self.lol_version:
                            fv = meta.get("game_version", "")
                            lv = self.lol_version
                            major_match = fv.split(".")[:2] == lv.split(".")[:2] if "." in fv and "." in lv else False
                            if not major_match:
                                btn.setEnabled(False)
                                rich_tooltip(btn, "版本不匹配")
                            else:
                                rich_tooltip(btn, f"使用 LOL {lv} 播放")
                        else:
                            btn.setEnabled(False)
                            rich_tooltip(btn, "请先设置LOL客户端目录")
                    hr_btns.addWidget(btn)
                    hr_btns.addSpacing(3)
                row2.addLayout(hr_btns)

                wl.addLayout(row2)

                item = QListWidgetItem(file_list)
                item.setSizeHint(QSize(700, 125))
                file_list.addItem(item)
                file_list.setItemWidget(item, w)

            # 筛选功能
            def apply_filter():
                mode = self.mode_filter.currentText()
                ver = self.ver_filter.currentText()
                date_from = self.date_from.date().toPython() if self.date_from.date() > self.date_from.minimumDate() else None
                date_to = self.date_to.date().toPython() if self.date_to.date() > self.date_to.minimumDate() else None
                for i in range(file_list.count()):
                    item = file_list.item(i)
                    fname = fnames[i] if i < len(fnames) else ""
                    fp = os.path.join(self.current_folder, fname) if hasattr(self, "current_folder") and self.current_folder else ""
                    m = parse_rolf_metadata(fp) if fp and os.path.exists(fp) else None
                    show = True
                    if m:
                        if mode != "全部模式" and m.get("game_mode") != mode:
                            show = False
                        if ver != "全部版本" and m.get("game_version") != ver:
                            show = False
                        if date_from or date_to:
                            gt = m.get("game_time", "")
                            if gt:
                                try:
                                    from datetime import datetime
                                    dt = datetime.strptime(gt[:10], "%Y-%m-%d")
                                    if date_from and dt < date_from: show = False
                                    if date_to and dt > date_to: show = False
                                except: pass
                    else:
                        if mode != "全部模式" or ver != "全部版本":
                            show = False
                    item.setHidden(not show)
            self.mode_filter.currentTextChanged.connect(lambda _: apply_filter())
            self.ver_filter.currentTextChanged.connect(lambda _: apply_filter())
            self.date_from.dateChanged.connect(lambda _: apply_filter())
            self.date_to.dateChanged.connect(lambda _: apply_filter())


            def play_replay(fn, meta, main_win):
                """调用 LOL 客户端播放回放"""
                if not hasattr(main_win, 'lol_path') or not main_win.lol_path:
                    QMessageBox.warning(dialog, "提示", "请先在主界面设置LOL客户端目录")
                    return
                import tempfile
                tmp_dir = tempfile.gettempdir()
                local_path = os.path.join(tmp_dir, fn)
                ok, _ = ServerAPI.download_file(fn, main_win.token, local_path)
                if not ok:
                    QMessageBox.warning(dialog, "失败", "下载文件失败")
                    return
                try:
                    if sys.platform == "darwin":
                        # Mac: 通过 LeagueClient 二进制播放
                        # 路径: xxx.app/Contents/LoL/LeagueClient.app/Contents/MacOS/LeagueClient
                        import subprocess
                        client_bin = os.path.join(
                            main_win.lol_path,
                            "Contents", "LoL", "LeagueClient.app",
                            "Contents", "MacOS", "LeagueClient"
                        )
                        if os.path.exists(client_bin):
                            subprocess.Popen([client_bin, local_path],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        else:
                            # fallback: 用 open -a 尝试
                            subprocess.Popen(["open", "-a", main_win.lol_path, "--args", local_path],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    elif sys.platform == "win32":
                        exe_path = os.path.join(main_win.lol_path, "LeagueClient.exe")
                        import subprocess
                        subprocess.Popen([exe_path, local_path])
                except Exception as e:
                    QMessageBox.warning(dialog, "失败", f"无法打开回放：{e}")

            def save_file(fn, tok, dlg):
                sp, _ = QFileDialog.getSaveFileName(dlg, "保存文件", fn, "LOL Replay (*.rofl);;所有文件 (*)")
                if sp:
                    ok, r = ServerAPI.download_file(fn, tok, sp)
                    if ok: QMessageBox.information(dlg, "下载成功", f"已保存到：\n{sp}")
                    else: QMessageBox.warning(dlg, "下载失败", str(r))

            def del_file(fn, row_idx, tok, dlg):
                if QMessageBox.question(dlg, "确认", f"确定删除 {fn}？", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
                    ok, _ = ServerAPI.delete_file(fn, tok)
                    if ok:
                        dlg.close()
                        self.show_file_manager()

            def rename_file(fn, tok, dlg):
                nn, ok = QInputDialog.getText(dlg, "重命名", f'将 "{fn}" 重命名为：', text=fn)
                if ok and nn and nn != fn:
                    if not nn.lower().endswith(".rofl") and not nn.lower().endswith(".rolf"):
                        nn += ".rofl"
                    ok2, r = ServerAPI.rename_file(fn, nn, tok)
                    if ok2:
                        dlg.close()
                        self.show_file_manager()
                    else:
                        QMessageBox.warning(dlg, "失败", str(r))

            select_all = [False]
            def toggle_all():
                select_all[0] = not select_all[0]
                sel_all.setText("取消全选" if select_all[0] else "全选")
                for i in range(file_list.count()):
                    item = file_list.item(i)
                    if item:
                        w = file_list.itemWidget(item)
                        if w:
                            for cb in w.findChildren(QCheckBox):
                                cb.setChecked(select_all[0])
                batch_del.setEnabled(select_all[0])
            sel_all.clicked.connect(toggle_all)

            def do_batch():
                to_del = [fnames[i] for i in range(len(fnames)) if checked[i]]
                if not to_del: return
                if QMessageBox.question(dialog, "确认", f"确定删除选中的 {len(to_del)} 个文件？",
                    QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
                    for fn in to_del:
                        ServerAPI.delete_file(fn, self.token)
                    dialog.close()
                    self.show_file_manager()

            batch_del.clicked.connect(do_batch)

            sb = QLabel(f"云端共 {len(fnames)} 个文件")
            sb.setStyleSheet("color: #718096; font-size: 11px; padding: 4px;")
            layout.addWidget(sb)
            dialog.exec()
        except Exception as e:
            import traceback
            print(f"云端管理错误：{str(e)}\n{traceback.format_exc()}")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "错误", str(e))
def show_login():
    """显示登录窗口（返回窗口引用防止 GC 回收）"""
    login_win = LoginWindow()

    def on_login_success(token, username):
        MainWindow._on_logout = show_login
        main_win = MainWindow(token, username)
        main_win.show()
        login_win.close()

    login_win.login_success.connect(on_login_success)
    login_win.show()
    return login_win  # 返回引用防止 Python GC 回收


def main():
    app = QApplication(sys.argv)
    pix = QPixmap()
    pix.loadFromData(base64.b64decode(APP_ICON_B64))
    app.setWindowIcon(QIcon(pix))
    # 全局样式（Fusion 风格 + ToolTip + hover）
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QToolTip {
            background-color: #ffffff;
            color: #2d3748;
            border: 1px solid #cbd5e0;
            border-radius: 4px;
            padding: 6px 10px;
            font-size: 12px;
            font-family: system-ui;
        }
        QPushButton:hover {
            border: 2px solid rgba(0,0,0,0.25) !important;
        }
    """)
    

    MainWindow._on_logout = show_login

    # 总是显示登录窗口（支持自动填充和自动登录）
    _login_win = show_login()  # 保持引用防止 GC 回收

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
