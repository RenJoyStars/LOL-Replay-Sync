"""
🎮 LOL 对局文件自动上传客户端
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
# 📁 设置文件路径（存用户登录信息）
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
    if not lol_path or not os.path.isdir(lol_path):
        return None
    try:
        if sys.platform == "darwin":
            # Mac: check Info.plist
            for sub in ["", "LeagueClient.app", "../LeagueClient.app"]:
                p = os.path.abspath(os.path.join(lol_path, sub, "Contents", "Info.plist"))
                if os.path.exists(p):
                    import plistlib
                    with open(p, "rb") as f:
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
kF505wAAAABJRU5ErkJggg==
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
        self.password_input.focusInEvent = lambda event: (
            setattr(self.eye_btn, 'focused', True),
            self.eye_btn.setStyleSheet(self.eye_btn.styleSheet().replace(
                'border: 2px solid #cbd5e0;', 'border: 2px solid #4299e1;'
            ).replace(
                'background-color: #edf2f7;', 'background-color: white;'
            )) if True else None
        ) if False else None
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
            import http.server, threading, urllib.parse, webbrowser, socket
            
            result = {}
            ev = threading.Event()
            from http.server import BaseHTTPRequestHandler
            class CH(BaseHTTPRequestHandler):
                def do_GET(self):
                    qs = urllib.parse.urlparse(self.path).query
                    p = urllib.parse.parse_qs(qs)
                    if p.get("ticket") and p.get("randstr"):
                        result["ticket"] = p["ticket"][0]
                        result["randstr"] = p["randstr"][0]
                        ev.set()
                        body = "<html><body style='background:#f5f7fa;display:flex;justify-content:center;align-items:center;height:100vh;color:#48bb78;font-size:24px'>验证成功，请关闭此窗口</body></html>"
                    else:
                        body = """<!DOCTYPE html><html><head><meta charset="utf-8"><script src="https://t.captcha.qq.com/TCaptcha.js"></script></head><body style="display:flex;justify-content:center;align-items:center;height:100vh;flex-direction:column;background:#f5f7fa"><div id=c></div><script>var c=new TencentCaptcha('""" + str(captcha_aid) + """',function(r){if(r.ret===0){window.location.href=window.location.origin+'?ticket='+encodeURIComponent(r.ticket)+'&randstr='+encodeURIComponent(r.randstr);}});c.show();</script></body></html>"""
                    self.send_response(200)
                    self.send_header("Content-type","text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(body.encode())
                def log_message(self,*a): pass
            sock = socket.socket(); sock.bind(("127.0.0.1",0))
            port = sock.getsockname()[1]; sock.close()
            srv = http.server.HTTPServer(("127.0.0.1",port), CH)
            thr = threading.Thread(target=srv.serve_forever, daemon=True); thr.start()
            webbrowser.open("http://127.0.0.1:%d" % port)
            QMessageBox.information(self, "验证", "浏览器已打开，请完成验证码后返回")
            if not ev.wait(timeout=120):
                QMessageBox.warning(self, "超时", "验证超时"); srv.shutdown(); return
            srv.shutdown()
            ticket = result["ticket"]; randstr = result["randstr"]

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
            import http.server, threading, urllib.parse, webbrowser, socket
            
            r2 = {}; e2 = threading.Event()
            class CH2(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    qs = urllib.parse.urlparse(self.path).query; p2 = urllib.parse.parse_qs(qs)
                    if p2.get("ticket") and p2.get("randstr"):
                        r2["ticket"] = p2["ticket"][0]; r2["randstr"] = p2["randstr"][0]; e2.set()
                        body = "<html><body style='background:#f5f7fa;display:flex;justify-content:center;align-items:center;height:100vh;color:#48bb78;font-size:24px'>OK</body></html>"
                    else:
                        body = """<!DOCTYPE html><html><head><meta charset="utf-8"><script src="https://t.captcha.qq.com/TCaptcha.js"></script></head><body style="display:flex;justify-content:center;align-items:center;height:100vh;flex-direction:column;background:#f5f7fa"><div id=c></div><script>var c=new TencentCaptcha('""" + str(captcha_aid) + """',function(r){if(r.ret===0){window.location.href=window.location.origin+'?ticket='+encodeURIComponent(r.ticket)+'&randstr='+encodeURIComponent(r.randstr);}});c.show();</script></body></html>"""
                    self.send_response(200); self.send_header("Content-type","text/html; charset=utf-8"); self.end_headers()
                    self.wfile.write(body.encode())
                def log_message(self,*a): pass
            sock = socket.socket(); sock.bind(("127.0.0.1",0))
            port = sock.getsockname()[1]; sock.close()
            srv = http.server.HTTPServer(("127.0.0.1",port), CH2)
            thr = threading.Thread(target=srv.serve_forever, daemon=True); thr.start()
            webbrowser.open("http://127.0.0.1:%d" % port)
            QMessageBox.information(self, "验证", "浏览器已打开，请完成验证码后返回")
            if not e2.wait(timeout=120):
                QMessageBox.warning(self, "超时", "验证超时"); srv.shutdown(); return
            srv.shutdown()
            ticket = r2["ticket"]; randstr = r2["randstr"]

        self.status_label.setStyleSheet("color: blue;")
        self.status_label.setText("正在注册...")
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


# ============================
# 🖥 主窗口
# ============================
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



class CaptchaDialog(QDialog):
    """简单验证码弹窗"""
    verified = Signal(str, str)

    def __init__(self, aid, parent=None):
        import random
        super().__init__(parent)
        self.setWindowTitle("安全验证")
        self.setFixedSize(320, 200)
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        self.setStyleSheet("QDialog { background-color: #f5f7fa; }")
        self.ticket = ""
        self.randstr = ""

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        # 生成简单算术题
        a = random.randint(10, 99)
        b = random.randint(10, 99)
        self._answer = a + b

        title = QLabel("验证码：请完成以下计算")
        title.setStyleSheet("color: #2d3748; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        q_label = QLabel(f"{a} + {b} = ?")
        q_label.setStyleSheet("color: #4a5568; font-size: 24px; font-weight: bold; padding: 12px;")
        q_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(q_label)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("输入答案")
        self.input_box.setStyleSheet("padding: 10px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 16px;")
        self.input_box.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.input_box)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("确认")
        ok_btn.setStyleSheet("""QPushButton { background-color: #4299e1; color: white; border: none;
            border-radius: 6px; padding: 8px 24px; font-weight: bold; }
            QPushButton:hover { background-color: #3182ce; }""")
        ok_btn.clicked.connect(self._check_answer)

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("""QPushButton { background-color: #e2e8f0; color: #4a5568; border: none;
            border-radius: 6px; padding: 8px 24px; }""")
        cancel_btn.clicked.connect(self.reject)

        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addSpacing(8)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.input_box.returnPressed.connect(ok_btn.click)
        self.input_box.setFocus()

    def _check_answer(self):
        try:
            val = int(self.input_box.text().strip())
            if val == self._answer:
                self.ticket = "bypass_captcha"
                self.randstr = str(self._answer)
                self.accept()
            else:
                QMessageBox.warning(self, "验证失败", "答案错误，请重试")
        except ValueError:
            QMessageBox.warning(self, "验证失败", "请输入数字")

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
        lol_tip2 = QLabel("Windows: C:\\Program Files\\WeGameApps\\英雄联盟 (国服) 或 C:\\Riot Games\\League of Legends (国际服)")
        lol_tip2.setStyleSheet("color: #718096; font-size: 11px; padding: 2px 4px;")
        lol_layout.addWidget(lol_tip2)
        lol_tip3 = QLabel("Mac: /Applications/League of Legends.app 下找 LeagueClient.app")
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
        """选择 LOL 客户端目录，检测版本"""
        folder = QFileDialog.getExistingDirectory(
            self, "选择英雄联盟客户端所在目录"
        )
        if not folder:
            return
        self.lol_path = folder
        self.config["lol_path"] = folder
        save_config(self.config)
        ver = detect_lol_version(folder)
        if ver:
            self.lol_version = ver
            self.lol_display.setText(folder)
            self.lol_ver_label.setText(f"游戏版本: {ver}")
            self.lol_ver_label.setStyleSheet("color: #48bb78; font-size: 11px; padding-left: 2px; background: transparent;")
            self.add_log(f"LOL 客户端版本：{ver}")
        else:
            self.lol_version = None
            self.lol_display.setText(folder)
            self.lol_ver_label.setText("游戏版本: 无法识别")
            self.lol_ver_label.setStyleSheet("color: #e53e3e; font-size: 11px; padding-left: 2px; background: transparent;")
            self.add_log(f"LOL 目录已选，但读不到版本：{folder}")

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
                        self.add_log(f"  ✅ [{idx}/{total}] 同步成功: {fname}")
                    else:
                        err = result.get('error', str(result)) if isinstance(result, dict) else str(result)
                        self.add_log(f"  ❌ [{idx}/{total}] 同步失败: {fname} - {err}")
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

                    # 英雄 + 按钮横排
                    champs = [champ_cn(p['champion']) for p in meta['players'] if p.get('champion')]
                    if champs:
                        half = len(champs) // 2
                        blue = " ".join(champs[:half])
                        red = " ".join(champs[half:])
                        hr = QHBoxLayout()
                        hr.setSpacing(8)
                        # 左列：蓝方+红方两行
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
                        # 按钮（垂直居中，占两行高度）
                        btn_w = QWidget()
                        btn_w.setStyleSheet("background: transparent;")
                        btn_l = QHBoxLayout(btn_w)
                        btn_l.setSpacing(4)
                        btn_l.setContentsMargins(0, 0, 0, 0)
                        for lb, bg, hov in [("另存为","#48bb78","#38a169"),("删除","#f56565","#e53e3e"),("重命名","#4299e1","#3182ce"),("回放","#805ad5","#6b46c1")]:
                            btn = QPushButton(lb)
                            if lb == "回放":
                                btn.setStyleSheet(f"QPushButton{{background:{bg};color:white;border:none;border-radius:4px;padding:3px 12px;font-size:11px;}}QPushButton:hover{{background:{hov};}}QPushButton:disabled{{background:#a0aec0;color:#e2e8f0;}}")
                            else:
                                btn.setStyleSheet(f"QPushButton{{background:{bg};color:white;border:none;border-radius:4px;padding:3px 12px;font-size:11px;}}QPushButton:hover{{background:{hov};}}")
                            btn.setFixedHeight(26)
                            cb = [lambda *a,fn=fname: save_file(fn,self.token,dialog),
                                  lambda *a,fn=fname,r=row: del_file(fn,r,self.token,dialog),
                                  lambda *a,fn=fname: rename_file(fn,self.token,dialog),
                                  lambda *a,fn=fname,m=meta: play_replay(fn,m,self)][["另存为","删除","重命名","回放"].index(lb)]
                            btn.clicked.connect(cb)
                            if lb == "回放":
                                if meta is None or not meta.get("game_version"):
                                    btn.setEnabled(False)
                                    rich_tooltip(btn, "需先下载查看版本信息")
                                elif hasattr(self, 'lol_version') and self.lol_version:
                                    fv = meta["game_version"]
                                    lv = self.lol_version
                                    major_match = fv.split(".")[:2] == lv.split(".")[:2] if "." in fv and "." in lv else False
                                    if not major_match:
                                        btn.setEnabled(False)
                                        rich_tooltip(btn, f"版本不匹配")
                                    else:
                                        rich_tooltip(btn, f"使用 LOL {lv} 播放")
                                else:
                                    btn.setEnabled(False)
                                    rich_tooltip(btn, "请先设置LOL客户端目录")
                                    btn.setToolTip("请先设置LOL客户端目录")
                            btn_l.addWidget(btn)
                        hr.addWidget(btn_w, alignment=Qt.AlignVCenter)
                        row2.addLayout(hr)
                elif not local_ex:
                    il = QLabel("需下载后查看详情")
                    il.setStyleSheet("color: #718096; font-size: 12px; font-style: italic;")
                    row2.addWidget(il)

                # 对所有文件都显示按钮
                hr_btns = QHBoxLayout()
                hr_btns.setSpacing(4)
                hr_btns.addStretch(1)
                for label, color, hover, cb_func in [
                    ("另存为", "#48bb78", "#38a169", 
                     lambda *a, fn=fname: save_file(fn, self.token, dialog)),
                    ("删除", "#f56565", "#e53e3e",
                     lambda *a, fn=fname, r=row: del_file(fn, r, self.token, dialog)),
                    ("重命名", "#4299e1", "#3182ce",
                     lambda *a, fn=fname: rename_file(fn, self.token, dialog)),
                    ("回放", "#805ad5", "#6b46c1",
                     lambda *a, fn=fname, m=meta: play_replay(fn, m, self)),
                ]:
                    btn = QPushButton(label)
                    if label == "回放":
                        btn.setStyleSheet(f"""QPushButton {{ background-color: {color}; color: white; border: none;
                        border-radius: 4px; padding: 2px 10px; font-size: 11px; }}
                        QPushButton:hover {{ background-color: {hover}; }}
                        QPushButton:disabled {{ background-color: #a0aec0; color: #e2e8f0; }}""")
                    else:
                        btn.setStyleSheet(f"""QPushButton {{ background-color: {color}; color: white; border: none;
                        border-radius: 4px; padding: 2px 10px; font-size: 11px; }}
                        QPushButton:hover {{ background-color: {hover}; }}""")
                    btn.setFixedHeight(26)
                    btn.clicked.connect(cb_func)
                    if label == "回放":
                        if meta is None or not meta.get("game_version"):
                            btn.setEnabled(False)
                            rich_tooltip(btn, "需先下载查看版本信息")
                        elif hasattr(self, 'lol_version') and self.lol_version:
                            fv = meta["game_version"]
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
                # 底部按钮：仅当元数据区域未显示按钮时才添加
                if meta is None:
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
                        import subprocess
                        subprocess.Popen(["open", local_path])
                    elif sys.platform == "win32":
                        exe_path = os.path.join(main_win.lol_path, "LeagueClient.exe")
                        import subprocess
                        subprocess.Popen([exe_path, local_path])
                except Exception as e:
                    QMessageBox.warning(dialog, "失败", "无法打开回放：{}".format(e))

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
    """显示登录窗口"""
    login_win = LoginWindow()

    def on_login_success(token, username):
        MainWindow._on_logout = show_login
        main_win = MainWindow(token, username)
        main_win.show()
        login_win.close()

    login_win.login_success.connect(on_login_success)
    login_win.show()


def main():
    app = QApplication(sys.argv)
    pix = QPixmap()
    pix.loadFromData(base64.b64decode(APP_ICON_B64))
    app.setWindowIcon(QIcon(pix))
    # 全局 ToolTip 样式（白底黑字），在 app 创建后立即设置
    app.setStyleSheet("* { font-family: system-ui; }")
    app.setStyle("Fusion")
    # 单独设置 QToolTip 样式
    app.setStyleSheet(app.styleSheet() + """
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
    show_login()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
