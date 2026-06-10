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
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize
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
qYGC2QCBUQAAAABJRU5ErkJggg==
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
    def register(username, password):
        """注册新用户"""
        try:
            r = requests.post(
                f"{SERVER_URL}/register",
                json={"username": username, "password": password},
                timeout=10
            )
            data = r.json()
            return r.status_code == 201, data.get("message", data.get("error", "未知错误"))
        except requests.exceptions.ConnectionError:
            return False, "无法连接到服务器，请检查地址"
        except Exception as e:
            return False, f"网络错误：{str(e)}"

    @staticmethod
    def login(username, password):
        """用户登录"""
        try:
            r = requests.post(
                f"{SERVER_URL}/login",
                json={"username": username, "password": password},
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
            QTimer.singleShot(300, self.do_login)

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

        self.status_label.setStyleSheet("color: blue;")
        self.status_label.setText("正在登录...")
        self.login_btn.setEnabled(False)
        self.register_btn.setEnabled(False)
        QApplication.processEvents()

        success, result = ServerAPI.login(username, password)
        
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

        self.status_label.setStyleSheet("color: blue;")
        self.status_label.setText("正在注册...")
        self.login_btn.setEnabled(False)
        self.register_btn.setEnabled(False)
        QApplication.processEvents()

        success, message = ServerAPI.register(username, password)
        
        self.login_btn.setEnabled(True)
        self.register_btn.setEnabled(True)

        if success:
            self.status_label.setStyleSheet("color: green;")
            self.status_label.setText(f"{message}，现在登录吧！")
        else:
            self.status_label.setStyleSheet("color: red;")
            self.status_label.setText(f"{message}")


# ============================
# 🖥 主窗口
# ============================
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
        self.setFixedSize(620, 520)
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
                    self.lol_ver_label.setText(f"✅ 检测到版本：{ver}")
                    self.lol_ver_label.setStyleSheet("color: #48bb78; font-size: 11px; padding-left: 2px;")
        
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
        content_layout.setSpacing(12)
        content_layout.setContentsMargins(20, 16, 20, 16)

        # ===== 文件夹选择 =====
        folder_card = QFrame()
        folder_card.setStyleSheet("background: transparent; border: none;")
        folder_card_layout = QVBoxLayout(folder_card)
        folder_card_layout.setContentsMargins(0, 0, 0, 0)
        folder_card_layout.setSpacing(8)

        folder_title = QLabel("定位对局文件夹")
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

        lol_title = QLabel("定位LOL客户端目录")
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

        self.lol_ver_label = QLabel("")
        self.lol_ver_label.setStyleSheet("color: #718096; font-size: 11px; padding-left: 2px;")
        lol_layout.addWidget(self.lol_ver_label)

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
            self.lol_ver_label.setText(f"✅ 检测到版本：{ver}")
            self.lol_ver_label.setStyleSheet("color: #48bb78; font-size: 11px; padding-left: 2px;")
            self.add_log(f"LOL 客户端版本：{ver}")
        else:
            self.lol_version = None
            self.lol_display.setText(folder)
            self.lol_ver_label.setText("⚠️ 未检测到版本信息")
            self.lol_ver_label.setStyleSheet("color: #e53e3e; font-size: 11px; padding-left: 2px;")
            self.add_log(f"LOL 目录已选，但读不到版本：{folder}")

    def toggle_sync(self):
        """开始同步 — 对比本地和云端，上传缺失文件"""
        if not hasattr(self, 'current_folder') or not self.current_folder:
            QMessageBox.warning(self, "提示", "请先选择一个文件夹！")
            return

        self.start_btn.setEnabled(False)
        self.start_btn.setText("⏳ 同步中...")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4299e1,
                    stop:1 #3182ce
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
                self.add_log(f"需要上传 {len(to_upload)} 个文件...")
                for fname in to_upload:
                    fpath = os.path.join(self.current_folder, fname)
                    if not os.path.exists(fpath):
                        continue
                    meta = parse_rolf_metadata(fpath)
                    if meta:
                        info_parts = []
                        if meta.get('map'): info_parts.append(meta['map'])
                        if meta.get('game_mode'): info_parts.append(meta['game_mode'])
                        if meta.get('players'): info_parts.append(f"{len(meta['players'])}人")
                        if meta['game_length'] and meta['game_length'] > 0:
                            info_parts.append(f"{int(meta['game_length'])//60}分")
                        self.add_log(f"  上传 {fname}  ({' | '.join(info_parts)})")
                    else:
                        self.add_log(f"  上传 {fname}")

                    ok, result = ServerAPI.upload_file(fpath, self.token)
                    if ok:
                        self.add_log(f"  ✅ 同步成功: {fname}")
                    else:
                        err = result.get('error', str(result)) if isinstance(result, dict) else str(result)
                        self.add_log(f"  ❌ 同步失败: {fname} - {err}")

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
                QAbstractItemView, QInputDialog, QCheckBox, QComboBox)

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
                        for lb, bg, hov in [("另存为","#48bb78","#38a169"),("删除","#f56565","#e53e3e"),("重命名","#4299e1","#3182ce")]:
                            btn = QPushButton(lb)
                            btn.setStyleSheet(f"QPushButton{{background:{bg};color:white;border:none;border-radius:4px;padding:3px 12px;font-size:11px;}}QPushButton:hover{{background:{hov};}}")
                            btn.setFixedHeight(26)
                            cb = [lambda *a,fn=fname: save_file(fn,self.token,dialog),
                                  lambda *a,fn=fname,r=row: del_file(fn,r,self.token,dialog),
                                  lambda *a,fn=fname: rename_file(fn,self.token,dialog)][["另存为","删除","重命名"].index(lb)]
                            btn.clicked.connect(cb)
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
                ]:
                    btn = QPushButton(label)
                    btn.setStyleSheet(f"""QPushButton {{ background-color: {color}; color: white; border: none;
                        border-radius: 4px; padding: 2px 10px; font-size: 11px; }}
                        QPushButton:hover {{ background-color: {hover}; }}""")
                    btn.setFixedHeight(26)
                    btn.clicked.connect(cb_func)
                    hr_btns.addWidget(btn)
                    hr_btns.addSpacing(3)
                if not local_ex:
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
                    else:
                        if mode != "全部模式" or ver != "全部版本":
                            show = False
                    item.setHidden(not show)
            self.mode_filter.currentTextChanged.connect(lambda _: apply_filter())
            self.ver_filter.currentTextChanged.connect(lambda _: apply_filter())


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
    app.setStyle("Fusion")
    

    MainWindow._on_logout = show_login

    # 总是显示登录窗口（支持自动填充和自动登录）
    show_login()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
