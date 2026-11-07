import json
import glfw
import OpenGL.GL as gl
import imgui
import pystray
from imgui.integrations.glfw import GlfwRenderer
import win32gui
from pystray import MenuItem as item
import threading
from PIL import Image
import win32con
import time
import numpy as np
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QOpenGLWidget
from PyQt5.QtGui import QColor  # 添加这行导入
from PyQt5.QtGui import QPainter, QFont, QFontMetrics
from OpenGL.GL import *
from OpenGL.GLU import gluOrtho2D  # 添加到文件顶部
from OpenGL.GLUT import *
from PyQt5.QtCore import pyqtSignal, pyqtSlot  # 添加这行导入
import ctypes
import socket
import serial
import random
import math
import csv
import vischeck

class UDPReceiver:
    def __init__(self, port=6564):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', port))
        self.data = {
            'esp_data': [],
            'player_data': {},
            'bones_data': [],
            'view_matrix': [  # 默认单位矩阵
                1, 0, 0, 0,
                0, 1, 0, 0,
                0, 0, 1, 0,
                0, 0, 0, 1
            ],
            'output': {  # ✅ 新增 output_data
                'aim_check': 0,
                'esp': 0,
                'radar': 0,
                'recoil': 0
            }
        }
        self.running = True
        self.lock = threading.Lock()
        threading.Thread(target=self._receive_loop, daemon=True).start()

    def _receive_loop(self):
        while self.running:
            try:
                data, _ = self.sock.recvfrom(65535)
                json_str = data.decode('utf-8')

                packet = json.loads(json_str)
                if 'type' in packet and 'data' in packet:
                    with self.lock:
                        if packet['type'] == 'view_matrix':
                            self._update_view_matrix(packet['data'])
                        else:
                            self.data[packet['type']] = packet['data']
            except json.JSONDecodeError as e:
                print(f"JSON 解析错误: {e}, 原始数据: {data}")
            except Exception as e:
                print(f"UDP接收错误: {e}")

    def _update_view_matrix(self, matrix_data):
        """ 处理 view_matrix 数据 """
        if isinstance(matrix_data, dict) and "view_matrix" in matrix_data:
            matrix_data = matrix_data["view_matrix"]  # ✅ 取出真正的矩阵数据
        if isinstance(matrix_data, list) and len(matrix_data) == 16:
            self.data['view_matrix'] = matrix_data
        else:
            print(f"❌ view_matrix 格式错误, 收到: {matrix_data}")  # 发现异常时打印

    def _update_output_data(self, output_data):
        """ 处理 output_data (aim_check, esp, radar) """
        if isinstance(output_data, dict):
            self.data['output_data']['aim_check'] = output_data.get('aim_check', 0)
            self.data['output_data']['esp'] = output_data.get('esp', 0)
            self.data['output_data']['radar'] = output_data.get('radar', 0)
            self.data['output_data']['recoil'] = output_data.get('recoil', 0)
        else:
            print(f"❌ output_data 格式错误, 收到: {output_data}")

    def get_data(self, data_type):
        with self.lock:  # 线程安全获取数据
            return self.data.get(data_type)

    def stop(self):
        self.running = False
        self.sock.close()

# 全局UDP接收器
udp_receiver = UDPReceiver(port=6564)  # 与C++端端口一致

def get_esp_data():
    data = udp_receiver.get_data('esp_data')
    return data if isinstance(data, list) else []

def get_bones_data():
    data = udp_receiver.get_data('bones_data')
    return data if isinstance(data, list) else []

def get_view_matrix():
    data = udp_receiver.get_data('view_matrix')
    return data if isinstance(data, list) and len(data) == 16 else [
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 1
    ]

def get_player_data():
    data = udp_receiver.get_data('player_data')
    return data if isinstance(data, dict) else {}

# ✅ **获取 output_data (aim_check, esp, radar)**
def get_output_data():
    data = udp_receiver.get_data('output')
    return (
        data.get('aim_check', 0),
        data.get('esp', 0),
        data.get('radar', 0),
        data.get('recoil', 0),
        data.get('aim_move', 0)
    )

# 读取配置文件
def load_resolution():
    try:
        with open("./XiaoPanSetting/resolution.json", "r") as resolution_file:
            resolution = json.load(resolution_file)
            return resolution
    except FileNotFoundError:
        print("配置文件未找到，使用默认分辨率")
        return {"resolution": {"width": 2560, "height": 1440}}  # 默认分辨率

# 加载配置
resolution = load_resolution()
WINDOW_WIDTH = resolution["resolution"]["width"]
WINDOW_HEIGHT = resolution["resolution"]["height"]



# 缓存变量用于存储上一次成功读取的数据
last_esp_data = []
last_bones_data = []
last_view_matrix = [0] * 16  # 默认视图矩阵

def get_esp_data():
    return udp_receiver.get_data('esp_data') or []

def get_bones_data():
    return udp_receiver.get_data('bones_data') or []

def get_view_matrix():
    return udp_receiver.get_data('view_matrix') or [0]*16

def get_player_data():
    return udp_receiver.get_data('player_data') or {}

# 读取颜色配置并返回指定颜色的整数（ARGB 格式）
def load_color_config(file_color, color_name):
    try:
        with open(file_color, 'r') as color_file:
            color_data = json.load(color_file)
            rgba = color_data.get(color_name, None)
            if rgba:
                return (rgba[3] << 24) | (rgba[0] << 16) | (rgba[1] << 8) | rgba[2]
            else:
                print(f"Error: Color '{color_name}' not found in the config.")
                return (255 << 24) | (255 << 16) | (255 << 8) | 255  # 默认白色 ARGB
    except Exception as e:
        print(f"Error loading color configuration: {e}")
        return (255 << 24) | (255 << 16) | (255 << 8) | 255  # 默认白色 ARGB

def argb_to_rgba_list(argb):
    return [
        argb & 0xFF,           # B -> R
        (argb >> 8) & 0xFF,    # G
        (argb >> 16) & 0xFF,   # R -> B
        (argb >> 24) & 0xFF    # A
    ]


def rgba_list_to_argb(rgba):
    return (rgba[3] << 24) | (rgba[0] << 16) | (rgba[1] << 8) | rgba[2]

def normalize_color(color):

    return [c / 255.0 for c in color]


def update_color_config(file_path, key, new_color_rgba):
    try:
        # 读取现有配置
        with open(file_path, "r", encoding="utf-8") as file:
            config = json.load(file)

        # 更新颜色值
        config[key] = new_color_rgba

        # 写回文件
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(config, file, indent=4)

        print(f"颜色 {key} 已更新为 {new_color_rgba}")
    except Exception as e:
        print(f"更新颜色配置失败: {e}")

# 三维坐标转换为屏幕坐标
def w2s(mtx, posx, posy, posz, width, height):
    screenW = (mtx[12] * posx) + (mtx[13] * posy) + (mtx[14] * posz) + mtx[15]
    if screenW > 0.001:
        screenX = (mtx[0] * posx) + (mtx[1] * posy) + (mtx[2] * posz) + mtx[3]
        screenY = (mtx[4] * posx) + (mtx[5] * posy) + (mtx[6] * posz) + mtx[7]
        camX = width / 2
        camY = height / 2
        x = camX + (camX * screenX / screenW) // 1
        y = camY - (camY * screenY / screenW) // 1
        return [x, y]
    return [-999, -999]


# CSV 文件路径
CSV_FILE = "./XiaoPanSetting/map_points.csv"

# 保存点位到 CSV
def save_point_to_csv(map_name, legX, legY, legZ, pitch, yaw, grenade="None", description="None", throw_type="None"):
    file_exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, mode="a", newline="", encoding='utf-8') as file:
        writer = csv.writer(file)

        # 如果文件不存在，写入表头
        if not file_exists:
            writer.writerow(["地图名称", "点位描述", "投掷方式", "投掷物", "legX", "legY", "legZ", "Pitch", "Yaw"])

        # 写入新点位（描述和投掷方式默认为None）
        writer.writerow([map_name, description, throw_type, grenade, legX, legY, legZ, pitch, yaw])
    print(f"已记录点位: {map_name} (X:{legX}, Y:{legY}, Z:{legZ})")

# 读取所有点位
def load_points_from_csv():
    points = []
    if not os.path.exists(CSV_FILE):
        return points

    with open(CSV_FILE, mode="r", newline="", encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            points.append({
                "地图名称": row["地图名称"],
                "点位描述": row["点位描述"],
                "投掷方式": row["投掷方式"],
                "投掷物": row["投掷物"],
                "站立点": [float(row["legX"]), float(row["legY"]), float(row["legZ"])],
                "Pitch": float(row["Pitch"]),
                "Yaw": float(row["Yaw"])
            })
    return points


# 全部地图的 VisCheck 缓存（包括预加载）
all_checkers = {}
# 加载失败的地图名（不再重复尝试加载）
failed_maps = set()

# 当前已加载的地图信息
checker = None
loaded_map_name = None

def preload_all_vischeck():
    """启动时预加载所有可用的 .opt 文件"""
    opt_base_path = "./maps"
    opt_files = [f for f in os.listdir(opt_base_path) if f.endswith("_world_physics.opt")]

    for opt_file in opt_files:
        map_name = opt_file.replace("_world_physics.opt", "").lower()  # 获取地图名
        opt_path = os.path.join(opt_base_path, opt_file)

        # 检查是否已经缓存过该地图
        if map_name in all_checkers:
            print(f"📥 地图 {map_name} 已加载，跳过")
            continue  # 如果已经加载过就跳过

        try:
            # 预加载该地图的 VisCheck
            vc = vischeck.VisCheck(opt_path)
            all_checkers[map_name] = vc
            print(f"✅ 成功预加载地图: {map_name}")
        except Exception as e:
            print(f"❌ 预加载地图 {map_name} 失败: {e}")
            failed_maps.add(map_name)

def update_checker_if_needed():
    """地图发生变化时切换 checker"""
    global checker, loaded_map_name

    try:
        player_data = get_player_data()
        local_player = player_data.get("localPlayer", {})
        current_map = local_player.get("mapName", "").lower()

        if not current_map:
            print("⚠️ 当前地图名无效")
            return

        if current_map == loaded_map_name:
            return  # 地图未变化，无需处理

        # 地图黑名单：之前加载失败的地图，跳过
        if current_map in failed_maps:
            return

        # 检查 .opt 文件是否存在
        opt_filename = f"{current_map}_world_physics.opt"
        opt_path = os.path.join("./maps", opt_filename)
        if not os.path.isfile(opt_path):
            failed_maps.add(current_map)
            return

        # 如果在预加载缓存中
        if current_map in all_checkers:
            checker = all_checkers[current_map]
            loaded_map_name = current_map
            print(f"✅ 已切换到地图 {current_map} 的 VisCheck")
        else:
            # 动态尝试加载（容错）
            try:
                checker = vischeck.VisCheck(opt_path)
                loaded_map_name = current_map
                all_checkers[current_map] = checker
                print(f"✅ 动态加载并切换到地图 {current_map}")
            except Exception as e:
                print(f"❌ 动态加载地图 {current_map} 失败: {e}")
                failed_maps.add(current_map)
                checker = None

    except Exception as e:
        print(f"💥 更新可视检测器时发生异常: {e}")
        checker = None

# 启动程序时预加载所有地图
preload_all_vischeck()

# 绘制方框
def draw_boxes_batch(draw_list, esp_data, bones_data, view_matrix, esp_color, player_color, bones_color,
                 hp_color, armor_color, weapon_color, money_color, state_color, c4time_color, scoped_color,
                 head_bones_color, grenade_points_color,grenade_throw_color,round_test_color,
                 WINDOW_WIDTH, WINDOW_HEIGHT, font, is_c4time_enabled, is_health_enabled, is_armor_enabled):
    imgui.push_font(font)
    imgui.pop_font()

    global aim_target
    aim_target = None  # 初始化为None
    aim_thread_running = False


    # 获取屏幕中心点
    screen_center_x = WINDOW_WIDTH // 2
    screen_center_y = WINDOW_HEIGHT // 2

    # 获取玩家数据
    player_data = get_player_data()

    local_player = player_data.get("localPlayer", {})
    local_weapon_id = local_player.get("localWeaponID", 0)
    current_map = local_player.get("mapName", "unknown").lower()  # 统一转为小写



    # 读取所有投掷点位
    grenade_points = load_points_from_csv()


    # 获取自身位置坐标（locallegX, locallegY, locallegZ）
    local_leg_X = local_player.get("locallegX", 0.0)
    local_leg_Y = local_player.get("locallegY", 0.0)
    local_leg_Z = local_player.get("locallegZ", 0.0)

    weapon_name_map = {
        43: "闪", 45: "烟", 46: "火", 48: "火",
        263187: "闪", 263189: "烟", 263190: "火", 263192: "火"
    }

    current_weapon = weapon_name_map.get(local_weapon_id, None)  # 获取武器名称，默认为 None

    # 计算玩家与 debug 位置的欧几里得距离
    def distance_3d(x1, y1, z1, x2, y2, z2):
        return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2)

    # 记录当前玩家所处的站立点
    current_stand_point = None

    # 只有当手持武器在指定范围内时才绘制正方形
    if local_weapon_id in weapon_name_map:

        # 计算玩家与所有投掷点的距离，找出最近的投掷点
        min_distance = float("inf")
        closest_point = None

        # 设定站立点的判定阈值
        stand_threshold = 30  # 你可以调整这个值，单位：游戏坐标的距离
        # 设置隐藏其他站立点的距离阈值
        distance_threshold = 30

        # 存储所有当前站立的投掷点
        current_stand_points = []

        # 遍历所有投掷点
        for point in grenade_points:

            # 只有当前地图匹配的投掷点才会继续处理
            if point["地图名称"].lower() != current_map:
                continue  # 如果地图不匹配，则跳过此投掷点

            point_legX, point_legY, point_legZ = point["站立点"]
            distance = distance_3d(local_leg_X, local_leg_Y, local_leg_Z, point_legX, point_legY, point_legZ)

            # 计算最近的点
            if distance < min_distance:
                min_distance = distance
                closest_point = point

            # **如果玩家在这个站立点内，存入列表**
            if distance < stand_threshold:
                # 只有当前地图匹配的投掷点才会继续处理
                if point["地图名称"].lower() != current_map:
                    continue  # 如果地图不匹配，则跳过此投掷点

                # **严格匹配：只绘制当前武器对应的投掷点**
                if point["投掷物"] != current_weapon:
                    continue  # 不匹配，跳过

                current_stand_points.append(point)
                current_stand_point = point  # 赋值当前站立点

        # **如果 current_stand_points 为空，绘制所有点**
        hide_other_points = len(current_stand_points) > 0

        # 重新遍历投掷点并绘制
        for point in grenade_points:

            # 只有当前地图匹配的投掷点才会继续处理
            if point["地图名称"].lower() != current_map:
                continue  # 如果地图不匹配，则跳过此投掷点

            # **严格匹配：只绘制当前武器对应的投掷点**
            if point["投掷物"] != current_weapon:
                continue  # 不匹配，跳过

            point_legX, point_legY, point_legZ = point["站立点"]

            # **如果玩家站在某个点上，并且需要隐藏其他站立点**
            if hide_other_points and point not in current_stand_points:
                continue  # 隐藏不属于当前站立点的其他点


            # 正方形的边长（可调整）
            square_size = 15

            # 计算水平面上的四个角点 (以 point_legX, point_legY 为中心)
            bottom_left_3d = (point_legX - square_size, point_legY - square_size, point_legZ)
            bottom_right_3d = (point_legX + square_size, point_legY - square_size, point_legZ)
            top_left_3d = (point_legX - square_size, point_legY + square_size, point_legZ)
            top_right_3d = (point_legX + square_size, point_legY + square_size, point_legZ)

            # 3D 点转换为屏幕坐标
            bottom_left_2d = w2s(view_matrix, *bottom_left_3d, WINDOW_WIDTH, WINDOW_HEIGHT)
            bottom_right_2d = w2s(view_matrix, *bottom_right_3d, WINDOW_WIDTH, WINDOW_HEIGHT)
            top_left_2d = w2s(view_matrix, *top_left_3d, WINDOW_WIDTH, WINDOW_HEIGHT)
            top_right_2d = w2s(view_matrix, *top_right_3d, WINDOW_WIDTH, WINDOW_HEIGHT)

            # 只有当所有点都有效时才绘制正方形
            if all(point != [-999, -999] for point in [bottom_left_2d, bottom_right_2d, top_left_2d, top_right_2d]):
                draw_list.add_line(*bottom_left_2d, *bottom_right_2d, grenade_points_color, 2.0)
                draw_list.add_line(*bottom_right_2d, *top_right_2d, grenade_points_color, 2.0)
                draw_list.add_line(*top_right_2d, *top_left_2d, grenade_points_color, 2.0)
                draw_list.add_line(*top_left_2d, *bottom_left_2d, grenade_points_color, 2.0)

                # **添加点位描述文本**
                point_description = point["点位描述"]  # 获取点位描述
                text_x, text_y = top_right_2d  # 选择右上角作为文本位置
                draw_list.add_text(text_x + 5, text_y - 10, grenade_points_color, point_description)


    # 只有当玩家站在某个站立点时，才绘制投掷点
    if current_stand_point:
        # 获取该站立点的对应投掷点
        throw_pitch = current_stand_point["Pitch"]
        throw_yaw = current_stand_point["Yaw"]
        throw_roll = current_stand_point.get("Roll", 0)  # 如果没有 "Roll" 字段，就使用默认值 0

        # 获取投掷方式
        throw_type = current_stand_point["投掷方式"]  # 获取投掷方式（如 "跳投" 或 "站投"）

        # 当前视角（摄像机角度）
        local_viewAngles = local_player.get("viewAngles", [0.0, 0.0, 0.0])  # 默认值防止 KeyError
        current_pitch = local_viewAngles[0]
        current_yaw = local_viewAngles[1]
        current_roll = local_viewAngles[2]

        # 计算角度误差
        pitch_error_throw = current_pitch - throw_pitch
        yaw_error_throw = current_yaw - throw_yaw

        # 角度转弧度
        yaw_rad_throw = math.radians(-throw_yaw)

        cos_yaw_throw, sin_yaw_throw = math.cos(yaw_rad_throw), math.sin(yaw_rad_throw)

        # 设定投掷点正方形大小
        half_width = 10

        # **计算投掷点在屏幕上的位置**
        if pitch_error_throw == 0 and yaw_error_throw == 0:
            center_x_throw, center_y_throw = screen_center_x, screen_center_y
        else:
            offset_x_throw = yaw_error_throw * 10  # 调整系数
            offset_y_throw = -pitch_error_throw * 10  # 调整系数
            center_x_throw = screen_center_x + offset_x_throw
            center_y_throw = screen_center_y + offset_y_throw

        # **计算投掷点正方形的四个角点**
        front_left_throw = (
            int(center_x_throw - half_width * cos_yaw_throw - half_width * sin_yaw_throw),
            int(center_y_throw - half_width * sin_yaw_throw + half_width * cos_yaw_throw)
        )
        front_right_throw = (
            int(center_x_throw + half_width * cos_yaw_throw - half_width * sin_yaw_throw),
            int(center_y_throw + half_width * sin_yaw_throw + half_width * cos_yaw_throw)
        )
        back_left_throw = (
            int(center_x_throw - half_width * cos_yaw_throw + half_width * sin_yaw_throw),
            int(center_y_throw - half_width * sin_yaw_throw - half_width * cos_yaw_throw)
        )
        back_right_throw = (
            int(center_x_throw + half_width * cos_yaw_throw + half_width * sin_yaw_throw),
            int(center_y_throw + half_width * sin_yaw_throw - half_width * cos_yaw_throw)
        )

        # **绘制投掷点**
        draw_list.add_line(*front_left_throw, *front_right_throw, grenade_throw_color, 2.0)  # 前边
        draw_list.add_line(*front_right_throw, *back_right_throw, grenade_throw_color, 2.0)  # 右边
        draw_list.add_line(*back_right_throw, *back_left_throw, grenade_throw_color, 2.0)  # 后边
        draw_list.add_line(*back_left_throw, *front_left_throw, grenade_throw_color, 2.0)  # 左边

        # **可选：显示角度误差信息**
        error_text_throw = f"上下误差: {pitch_error_throw:.2f}, 左右误差: {yaw_error_throw:.2f}"
        draw_list.add_text(center_x_throw, center_y_throw + 50, grenade_throw_color, error_text_throw)

        # **显示投掷方式**
        throw_type_text = f"投掷方式: {throw_type}"  # 显示投掷方式
        draw_list.add_text(center_x_throw, center_y_throw + 70, grenade_throw_color, throw_type_text)  # 投掷方式显示位置可以调整

    #__________________________________

    # 在代码开头定义圆圈参数

    CENTER_X = WINDOW_WIDTH // 2
    CENTER_Y = WINDOW_HEIGHT // 2

    # 将 bones_data 转换为以 entity_index 为键的字典，方便快速匹配
    bones_data_dict = {bone['entity_index']: bone for bone in bones_data}

    # **全局变量**
    global c4_timer_start, last_c4_plan_time

    # **确保全局变量存在**
    if 'c4_timer_start' not in globals():
        c4_timer_start = None  # C4 计时开始时间
    if 'last_c4_plan_time' not in globals():
        last_c4_plan_time = 0  # 默认无炸弹状态

    c4_countdown_duration = 41  # C4 爆炸倒计时时长（秒）

    c4_plan_time = 0  # 先给 c4_plan_time 赋默认值

    # 确保 esp_data 是一个列表，避免类型错误
    if isinstance(esp_data, list):
        for entry in esp_data:
            if isinstance(entry, dict) and "C4PlanTime" in entry:
                c4_plan_time = entry["C4PlanTime"]
                break  # 找到后立即跳出循环，提高效率

    if c4_plan_time is not None:  # 只有获取到值时才更新
        last_c4_plan_time = c4_plan_time  # 更新最新的 C4 状态

    # **如果 C4 计时器已经启动，并且检测到 `C4PlanTime == 0`，则直接终止**
    if c4_timer_start is not None and last_c4_plan_time == 0:
        c4_timer_start = None  # 终止计时
        last_c4_plan_time = 0  # 恢复未激活状态
        return None  # 计时结束，返回 `None`

    # **C4 倒计时逻辑**
    if c4_timer_start is None:  # 只有当倒计时未开始时才检测
        if last_c4_plan_time == 1:  # C4 正在安放
            c4_timer_start = time.time()  # 记录倒计时开始时间

    # **如果 C4 计时器已经启动，继续倒计时**
    if is_c4time_enabled and c4_timer_start is not None:
        elapsed_time = time.time() - c4_timer_start  # 计算已经经过的时间
        remaining_time = max(0, c4_countdown_duration - elapsed_time)  # 计算剩余时间
        countdown_percentage = remaining_time / c4_countdown_duration  # 计算进度条比例

        # **确保倒计时不会中途消失**
        if remaining_time <= 0:
            c4_timer_start = None  # 倒计时结束后重置
            last_c4_plan_time = 0  # 让 C4 状态回归未激活
            remaining_time = 0  # 避免负数

        # **倒计时文本**
        countdown_text = f"炸 弹 爆 炸 倒 计 时: {int(remaining_time)}s"
        text_width = imgui.calc_text_size(countdown_text).x
        text_y = 130  # 文本位置稍微上移

        # **进度条位置**
        bar_width = 300  # 进度条的宽度
        bar_height = 20  # 进度条的高度
        bar_x_left = (WINDOW_WIDTH - bar_width) / 2
        bar_y_top = text_y + 30  # 进度条位置稍微下移
        bar_y_bottom = bar_y_top + bar_height

        # **半透明玻璃背景**
        draw_list.add_rect_filled(bar_x_left, bar_y_top, bar_x_left + bar_width, bar_y_bottom,
                                  imgui.get_color_u32_rgba(0.2, 0.2, 0.2, 0.5), rounding=8)

        # **高光边缘（修正后）**
        draw_list.add_rect_filled(bar_x_left, bar_y_top, bar_x_left + bar_width, bar_y_top + bar_height - 1,
                                  imgui.get_color_u32_rgba(1, 1, 1, 0.3), rounding=8)

        # **炸弹倒计时进度条**
        progress_width = bar_width * countdown_percentage
        draw_list.add_rect_filled(bar_x_left, bar_y_top, bar_x_left + progress_width, bar_y_bottom,
                                  c4time_color, rounding=8)  # 红色炸弹进度条

        # **光晕效果**
        draw_list.add_rect_filled(bar_x_left - 2, bar_y_top - 2, bar_x_left + progress_width + 2,
                                  bar_y_bottom + 2,
                                  imgui.get_color_u32_rgba(1, 1, 1, 0.1), rounding=10)

        # **倒计时数字 (嵌入进度条)**
        text_x = bar_x_left + (bar_width / 2) - (text_width / 2)  # 居中对齐进度条
        text_y = bar_y_top + 1  # 让文本稍微偏上，避免紧贴底部

        draw_list.add_text(text_x, text_y, 0xFFFFFFFF, countdown_text)

    camera_data = local_player.get("localcamera", [0.0, 0.0, 0.0])

    if not camera_data or len(camera_data) < 3:
        print("错误：无效的摄像机数据")
        camera_pos = (0.0, 0.0, 0.0)
    else:
        camera_pos = (
            float(camera_data[0]) if camera_data[0] is not None else 0.0,
            float(camera_data[1]) if camera_data[1] is not None else 0.0,
            float(camera_data[2]) if camera_data[2] is not None else 0.0
        )

    for entity in esp_data:
        entity_index = entity.get("entity_index")  # 避免 KeyError
        if entity_index is None:
            continue  # 跳过 C4PlanTime 数据

        # 从 bones_data_dict 获取对应骨骼数据
        bone_entity = bones_data_dict.get(entity_index)
        if not bone_entity:
            continue  # 如果 bones_data 中没有对应的骨骼数据，跳过

        headX = bone_entity['headX']
        headY = bone_entity['headY']
        headZ = bone_entity['headZ']

        legZ = entity.get('legZ', headZ)  # 如果 legZ 不存在，使用 headZ

        # 从 bones_data 获取骨骼坐标q
        neckX = bone_entity['neckX']
        neckY = bone_entity['neckY']
        neckZ = bone_entity['neckZ']

        waistX = bone_entity['waistX']
        waistY = bone_entity['waistY']
        waistZ = bone_entity['waistZ']

        shoulderleftX = bone_entity['shoulderleftX']
        shoulderleftY = bone_entity['shoulderleftY']
        shoulderleftZ = bone_entity['shoulderleftZ']

        foreleftX = bone_entity['foreleftX']
        foreleftY = bone_entity['foreleftY']
        foreleftZ = bone_entity['foreleftZ']

        handleftX = bone_entity['handleftX']
        handleftY = bone_entity['handleftY']
        handleftZ = bone_entity['handleftZ']

        shoulderrightX = bone_entity['shoulderrightX']
        shoulderrightY = bone_entity['shoulderrightY']
        shoulderrightZ = bone_entity['shoulderrightZ']

        forerightX = bone_entity['forerightX']
        forerightY = bone_entity['forerightY']
        forerightZ = bone_entity['forerightZ']

        handrightX = bone_entity['handrightX']
        handrightY = bone_entity['handrightY']
        handrightZ = bone_entity['handrightZ']

        kneeleftX = bone_entity['kneeleftX']
        kneeleftY = bone_entity['kneeleftY']
        kneeleftZ = bone_entity['kneeleftZ']

        feetleftX = bone_entity['feetleftX']
        feetleftY = bone_entity['feetleftY']
        feetleftZ = bone_entity['feetleftZ']

        kneerightX = bone_entity['kneerightX']
        kneerightY = bone_entity['kneerightY']
        kneerightZ = bone_entity['kneerightZ']

        feetrightX = bone_entity['feetrightX']
        feetrightY = bone_entity['feetrightY']
        feetrightZ = bone_entity['feetrightZ']

        # 获取关键骨骼坐标
        head = (
            bone_entity['headX'],
            bone_entity['headY'],
            bone_entity['headZ']
        )


        # 转换为屏幕坐标
        head_screen = w2s(view_matrix, headX, headY, headZ, WINDOW_WIDTH, WINDOW_HEIGHT)
        leg_screen = w2s(view_matrix, headX, headY, legZ, WINDOW_WIDTH, WINDOW_HEIGHT)

        # 获取骨骼点列表
        bones = [
            ('headX', 'headY', 'headZ'),
            ('waistX', 'waistY', 'waistZ'),
            ('shoulderleftX', 'shoulderleftY', 'shoulderleftZ'),
            ('foreleftX', 'foreleftY', 'foreleftZ'),
            ('handleftX', 'handleftY', 'handleftZ'),
            ('shoulderrightX', 'shoulderrightY', 'shoulderrightZ'),
            ('forerightX', 'forerightY', 'forerightZ'),
            ('handrightX', 'handrightY', 'handrightZ'),
            ('kneeleftX', 'kneeleftY', 'kneeleftZ'),
            ('feetleftX', 'feetleftY', 'feetleftZ'),
            ('kneerightX', 'kneerightY', 'kneerightZ'),
            ('feetrightX', 'feetrightY', 'feetrightZ'),
        ]

        # 更新地图检查器（仅在地图变动时加载一次）
        update_checker_if_needed()

        # 全局最近骨骼点（不分实体）
        final_closest_bone = None
        final_closest_entity = None
        final_closest_entity_index = -1
        final_closest_distance = float('inf')


        for bone in bones:
            x = bone_entity.get(bone[0])
            y = bone_entity.get(bone[1])
            z = bone_entity.get(bone[2])
            if None in (x, y, z):
                continue
            if bone[2] == 'headZ':
                z -= 8

            screen_pos = w2s(view_matrix, x, y, z, WINDOW_WIDTH, WINDOW_HEIGHT)
            if screen_pos and screen_pos != [-999, -999]:
                sx, sy = screen_pos
                dist = ((sx - CENTER_X) ** 2 + (sy - CENTER_Y) ** 2) ** 0.5
                if dist <= CIRCLE_RADIUS:
                    if checker and checker.is_visible(camera_pos, (x, y, z)):
                        if dist < final_closest_distance:
                            final_closest_distance = dist
                            final_closest_bone = bone
                            final_closest_entity = bone_entity
                            final_closest_entity_index = entity_index
                        elif dist == final_closest_distance:
                            import random
                            if random.random() > 0.5:
                                final_closest_bone = bone
                                final_closest_entity = bone_entity
                                final_closest_entity_index = entity_index

        # 最终绘制/瞄准
        if final_closest_bone:
            x = final_closest_entity[final_closest_bone[0]]
            y = final_closest_entity[final_closest_bone[1]]
            z = final_closest_entity[final_closest_bone[2]]
            if final_closest_bone[2] == 'headZ':
                z -= 8
            target_screen = w2s(view_matrix, x, y, z, WINDOW_WIDTH, WINDOW_HEIGHT)
            if target_screen and target_screen != [-999, -999]:
                target_x, target_y = target_screen

                # 计算需要移动的像素距离
                dx = target_x - CENTER_X
                dy = target_y - CENTER_Y
                distance = (dx ** 2 + dy ** 2) ** 0.5

                aim_target = {
                    'dx': dx,
                    'dy': dy,
                    'distance': distance,
                    'entity_index': final_closest_entity_index,
                    'bone_name': final_closest_bone[0][:-1],
                    'screen_pos': (target_x, target_y)
                }

                # ============= 调试输出 =============
                # 1. 控制台彩色打印
                #print("\033[1;36m" + "=" * 40 + "\033[0m")
                #print(f"\033[1;33m[目标更新] 实体 {final_closest_entity_index}\033[0m")
                #print(f"\033[32m├─ 骨骼类型: {final_closest_bone[0][:-1]}")
                #print(f"├─ 屏幕坐标: ({target_x:.1f}, {target_y:.1f})")
                #print(f"├─ 中心偏移: dx={dx:.1f} dy={dy:.1f}")
                #print(f"└─ 直线距离: \033[1;35m{distance:.1f}px\033[0m")

                # 绘制锁定标记
                draw_list.add_circle(
                    target_x, target_y, 5,
                    round_test_color,
                    thickness=3
                )

                DYNAMIC_CENTER_X, DYNAMIC_CENTER_Y = target_screen
                draw_list.add_line(
                    CENTER_X, CENTER_Y,
                    DYNAMIC_CENTER_X, DYNAMIC_CENTER_Y,
                    round_test_color,
                    thickness=2
                )
                bone_name = final_closest_bone[0][:-1]
                #print(f"[锁定] 实体 {final_closest_entity_index} | 骨骼: {bone_name} | 坐标: ({DYNAMIC_CENTER_X:.1f}, {DYNAMIC_CENTER_Y:.1f})")
        else:
            # 没有目标时画默认圆
            draw_list.add_circle(CENTER_X, CENTER_Y, CIRCLE_RADIUS, round_test_color, thickness=2)

        if head_screen != [-999, -999] and leg_screen != [-999, -999]:
            head_position = head_screen
            leg_position = leg_screen

            deltaZ = abs(head_position[1] - leg_position[1])
            leftX = head_position[0] - deltaZ // 3
            rightX = head_position[0] + deltaZ // 3

            # 批量绘制方框
            draw_list.add_line(leftX, leg_position[1], rightX, leg_position[1], esp_color , 2.0)
            draw_list.add_line(leftX, leg_position[1], leftX, head_position[1], esp_color , 2.0)
            draw_list.add_line(rightX, leg_position[1], rightX, head_position[1], esp_color , 2.0)
            draw_list.add_line(leftX, head_position[1], rightX, head_position[1], esp_color , 2.0)

            draw_list.add_circle(CENTER_X, CENTER_Y, CIRCLE_RADIUS, round_test_color, thickness=2)


            if is_health_enabled:
                # 绘制血量条
                health = entity.get('health', 100)  # 假设默认血量为 100

                hp_bar_width = deltaZ * 0.8
                hp_bar_height = 12  # 血量条稍微高一点
                hp_percentage = max(0, min(health / 100.0, 1))

                # **血条位置**
                hp_bar_x_left = head_position[0] - hp_bar_width / 2
                hp_bar_y_top = head_position[1] - deltaZ / 10
                hp_bar_y_bottom = hp_bar_y_top - hp_bar_height

                # **半透明玻璃背景**
                draw_list.add_rect_filled(hp_bar_x_left, hp_bar_y_bottom, hp_bar_x_left + hp_bar_width, hp_bar_y_top,
                                          imgui.get_color_u32_rgba(0.2, 0.2, 0.2, 0.5), rounding=6)

                # **高光边缘**
                draw_list.add_rect_filled(hp_bar_x_left, hp_bar_y_bottom, hp_bar_x_left + hp_bar_width, hp_bar_y_top - 1,
                                          imgui.get_color_u32_rgba(1, 1, 1, 0.3), rounding=6)

                # **血量条**
                draw_list.add_rect_filled(hp_bar_x_left, hp_bar_y_bottom, hp_bar_x_left + (hp_bar_width * hp_percentage),
                                          hp_bar_y_top, hp_color, rounding=6)

                # **光晕效果**
                draw_list.add_rect_filled(hp_bar_x_left - 2, hp_bar_y_bottom - 2,
                                          hp_bar_x_left + (hp_bar_width * hp_percentage) + 2,
                                          hp_bar_y_top + 2, imgui.get_color_u32_rgba(1, 1, 1, 0.1), rounding=8)

                # **血量数字 (镶嵌到血条内部)**
                health_text = f"{health}"
                text_width = imgui.calc_text_size(health_text).x
                text_x = hp_bar_x_left + hp_bar_width / 2 - text_width / 2  # 居中对齐血条
                text_y = hp_bar_y_bottom - 2  # 让文本稍微偏上，避免紧贴底部

                text_color = imgui.get_color_u32_rgba(1, 1, 1, 1)
                draw_list.add_text(text_x, text_y, text_color, health_text)

            if is_armor_enabled:
                # 绘制护甲条
                ArmorValue = entity.get('ArmorValue', 100)  # 假设默认护甲值为 100

                AV_bar_width = deltaZ * 0.8  # 宽度与血量条一致
                AV_bar_height = 12  # 增加护甲条的高度
                AV_percentage = max(0, min(ArmorValue / 100.0, 1))  # 确保值在 0~1 之间

                # **护甲条位置**
                AV_bar_x_left = leg_position[0] - AV_bar_width / 2
                AV_bar_y_top = leg_position[1] + 8 + deltaZ / 10
                AV_bar_y_bottom = AV_bar_y_top - AV_bar_height

                # **半透明玻璃背景**
                draw_list.add_rect_filled(AV_bar_x_left, AV_bar_y_bottom, AV_bar_x_left + AV_bar_width, AV_bar_y_top,
                                          imgui.get_color_u32_rgba(0.2, 0.2, 0.2, 0.5), rounding=6)

                # **高光边缘**
                draw_list.add_rect_filled(AV_bar_x_left, AV_bar_y_bottom, AV_bar_x_left + AV_bar_width, AV_bar_y_top - 1,
                                          imgui.get_color_u32_rgba(1, 1, 1, 0.3), rounding=6)

                # **护甲条**
                draw_list.add_rect_filled(AV_bar_x_left, AV_bar_y_bottom, AV_bar_x_left + (AV_bar_width * AV_percentage),
                                          AV_bar_y_top, armor_color, rounding=6)

                # **光晕效果**
                draw_list.add_rect_filled(AV_bar_x_left - 2, AV_bar_y_bottom - 2,
                                          AV_bar_x_left + (AV_bar_width * AV_percentage) + 2,
                                          AV_bar_y_top + 2, imgui.get_color_u32_rgba(1, 1, 1, 0.1), rounding=8)

                # **护甲值数字 (镶嵌到护甲条内部)**
                ArmorValue_text = f"{ArmorValue}"
                text_width = imgui.calc_text_size(ArmorValue_text).x
                text_x = AV_bar_x_left + AV_bar_width / 2 - text_width / 2  # 居中对齐护甲条
                text_y = AV_bar_y_bottom - 2  # 让文本稍微偏上，避免紧贴底部

                text_color = imgui.get_color_u32_rgba(1, 1, 1, 1)
                draw_list.add_text(text_x, text_y, text_color, ArmorValue_text)

            # 绘制玩家名字
            PlayerName = entity.get('PlayerName', "Unknown")  # 获取玩家名字，默认值为 "Unknown"
            PlayerName_bar_y_top = head_position[1] - deltaZ / 6  # 将名字条绘制在头部上方

            # 绘制玩家名字
            text_width = imgui.calc_text_size(PlayerName).x  # 计算名字的宽度
            text_x = head_position[0] - text_width / 2  # 将文本居中
            text_y = PlayerName_bar_y_top - 30  # 在名字条上方稍微偏移

            # 绘制名字文本
            draw_list.add_text(text_x, text_y, player_color, PlayerName)  # 文字颜色

            # 获取金钱数值
            money = entity.get('moneyServices', 0)  # 获取金钱，默认为 0

            money_bar_y_top = head_position[1] - deltaZ / 6  # 将金钱条绘制在名字上方

            # 计算金钱文本的位置
            money_text = f"金钱:{money}"  # 格式化金钱，例如 "$1000"
            text_width = imgui.calc_text_size(money_text).x  # 计算文本宽度
            text_x = head_position[0] - text_width / 2  # 让文本居中
            text_y = money_bar_y_top - 50  # 让金钱显示在名字的上方

            # 绘制金钱文本
            draw_list.add_text(text_x, text_y, money_color, money_text)  # 设置颜色和文本

            # 武器代码到中文名称的映射字典
            weapon_names = {
                1: "沙漠之鹰",
                2: "双持贝瑞塔",
                3: "C4炸弹",
                4: "格洛克",
                7: "AK47",
                8: "AUG",
                9: "AWP",
                10: "法玛斯",
                11: "G3SG1",
                13: "加利尔AR",
                14: "M249",
                16: "M4A4",
                17: "MAC10",
                19: "P90",
                23: "MP5",
                24: "UMP45",
                25: "XM1014",
                26: "PP野牛",
                27: "MAG7",
                28: "内盖夫",
                29: "锯短霰弹枪",
                30: "TEC9",
                31: "电击枪",
                32: "P2000",
                33: "MP7",
                34: "MP9",
                35: "新星",
                36: "P250",
                38: "SCAR20",
                39: "SG553",
                40: "SSG08",
                42: "刀",
                43: "闪光弹",
                44: "手雷",
                45: "烟雾弹",
                46: "燃烧弹",
                47: "诱饵弹",
                48: "燃烧弹/燃烧手雷",
                49: "C4炸弹",
                59: "刀",
                60: "M4A1",
                61: "USP-S",
                63: "CZ75自动手枪",
                64: "左轮手枪",
                263145: "沙漠之鹰",
                263146: "双持贝瑞塔",
                263147: "C4炸弹",
                263148: "格洛克",
                263151: "AK47",
                263152: "AUG",
                263153: "AWP",
                263154: "法玛斯",
                263155: "G3SG1",
                263157: "加利尔AR",
                263158: "M249",
                263160: "M4A4",
                263161: "MAC10",
                263163: "P90",
                263167: "MP5",
                263168: "UMP45",
                263169: "XM1014",
                263170: "PP野牛",
                263171: "MAG7",
                263172: "内盖夫",
                263173: "锯短霰弹枪",
                263174: "TEC9",
                263175: "电击枪",
                263176: "P2000",
                263177: "MP7",
                263178: "MP9",
                263179: "新星",
                263180: "P250",
                263182: "SCAR20",
                263183: "SG553",
                263184: "SSG08",
                263186: "刀",
                263187: "闪光弹",
                263188: "手雷",
                263189: "烟雾弹",
                263190: "燃烧弹",
                263191: "诱饵弹",
                263192: "燃烧弹/燃烧手雷",
                263193: "C4炸弹",
                263203: "刀",
                263204: "M4A1",
                263205: "USP-S",
                263207: "CZ75自动手枪",
                263208: "左轮手枪",

            }

            # 获取武器代码
            weapon_code = entity.get('ClippingWeapon', None)  # 获取武器代码
            weapon_name = weapon_names.get(weapon_code, "刀")  # 映射到武器名称，默认值为 "Unknown Weapon"

            # 确定武器名称条的位置
            ClippingWeapon_bar_y_top = leg_position[1] + 8 + deltaZ /6   # 将武器名称条绘制在脚部下方

            # 计算武器名称文本的绘制位置
            text_width = imgui.calc_text_size(weapon_name).x  # 计算武器名称的宽度
            text_x = leg_position[0] - text_width / 2  # 将文本居中
            text_y = ClippingWeapon_bar_y_top + 0  # 在武器名称条下方稍微偏移

            # 绘制武器文本
            draw_list.add_text(text_x, text_y, weapon_color, weapon_name)  # 设置文字颜色为黑色

            state_name = {
                65681: "站立",
                65665: "站立",
                65683: "蹲下",
                65667: "蹲下",
                65664: "跳",
                65682: "跳",
                65680: "大跳",
                65666: "大跳",
                65672: "飞",
                65688: "飞",
            }

            # 获取站立代码
            state_code = entity.get('state', None)  # 获取状态代码
            state_name = state_name.get(state_code, "NONE")  # 映射到状态名称，默认值为 "NONE"

            # 检测是否正在下包
            is_planting = (weapon_code in [3, 49] and state_code in [65683, 65667])  # C4 且蹲下
            # 显示状态信息
            if is_planting:
                state_name = "正在下包"

            # 确定状态名称条的位置
            state_bar_y_top = leg_position[1] + 8 + deltaZ / 6  # 将状态名称条绘制在脚部下方

            # 计算状态名称文本的绘制位置
            text_width = imgui.calc_text_size(state_name).x  # 计算状态名称的宽度
            text_x = leg_position[0] - text_width / 2  # 将文本居中
            text_y = state_bar_y_top + 19  # 在状态名称条下方稍微偏移

            # 绘制状态文本
            draw_list.add_text(text_x, text_y, state_color, state_name)  # 设置文字颜色为黑色

            Scoped_name = {
                1: "开镜",  # 只有代码为 1 才表示开镜
            }

            # 获取开镜代码
            Scoped_code = entity.get('Scoped', None)  # 获取开镜状态代码

            # 只绘制开镜状态（Scoped_code == 1）
            if Scoped_code == 1:
                scoped_text = Scoped_name.get(Scoped_code, "NONE")  # 获取开镜状态名称

                # 确定开镜名称条的位置
                Scoped_bar_y_top = leg_position[1] + 8 + deltaZ / 6  # 将状态名称条绘制在脚部下方

                # 计算文本绘制位置
                text_width = imgui.calc_text_size(scoped_text).x
                text_x = leg_position[0] - text_width / 2  # 将文本居中
                text_y = Scoped_bar_y_top + 38  # 在状态名称条下方稍微偏移

                # 绘制开镜文本
                draw_list.add_text(text_x, text_y, scoped_color, scoped_text)

            # ====================== 骨骼信息定义 ======================
            # 定义骨骼信息，每个骨骼点有世界坐标、屏幕坐标、半径
            bones = {
                "head": (headX, headY, headZ),
                "neck": (neckX, neckY, neckZ),
                "waist": (waistX, waistY, waistZ),
                "shoulder_left": (shoulderleftX, shoulderleftY, shoulderleftZ),
                "shoulder_right": (shoulderrightX, shoulderrightY, shoulderrightZ),
                "hand_left": (handleftX, handleftY, handleftZ),
                "hand_right": (handrightX, handrightY, handrightZ),
                "forearm_left": (foreleftX, foreleftY, foreleftZ),
                "forearm_right": (forerightX, forerightY, forerightZ),
                "knee_left": (kneeleftX, kneeleftY, kneeleftZ),
                "knee_right": (kneerightX, kneerightY, kneerightZ),
                "foot_left": (feetleftX, feetleftY, feetleftZ),
                "foot_right": (feetrightX, feetrightY, feetrightZ),
            }

            # 连接线关系（骨骼连接）
            bone_connections = [
                ("head", "neck"),  # 头部和颈部的连接
                ("neck", "shoulder_right"),
                ("neck", "shoulder_left"),
                ("shoulder_right", "forearm_right"),
                ("forearm_right", "hand_right"),
                ("shoulder_left", "forearm_left"),
                ("forearm_left", "hand_left"),
                ("neck", "waist"),
                ("waist", "knee_right"),
                ("waist", "knee_left"),
                ("knee_right", "foot_right"),
                ("knee_left", "foot_left"),
            ]

            # ====================== 头部逻辑（保持不变） ======================
            # 头部碰撞盒
            head_pos = w2s(view_matrix, headX, headY, headZ - 8, WINDOW_WIDTH, WINDOW_HEIGHT)
            if head_pos != [-999, -999]:
                head_hitbox_radius = (rightX - leftX) / 20  # 头部半径较大
                draw_list.add_circle_filled(
                    head_pos[0], head_pos[1], head_hitbox_radius, head_bones_color
                )

                # 头部文字偏移
                offset_x, offset_y = 10, -10
                draw_list.add_text(
                    head_pos[0] + offset_x, head_pos[1] + offset_y, bones_color, ""
                )

            # ====================== 其他骨骼逻辑 ======================
            # **计算屏幕坐标并存储**
            bone_positions = {}  # 存储所有骨骼点的屏幕坐标
            for name, (x, y, z) in bones.items():
                if name == "head":
                    continue  # 头部已经单独处理
                bone_positions[name] = w2s(view_matrix, x, y, z, WINDOW_WIDTH, WINDOW_HEIGHT)

            # **批量绘制碰撞盒**
            for name, screen_pos in bone_positions.items():
                if screen_pos == [-999, -999]:
                    continue  # 如果某个点无法转换到屏幕坐标，则跳过

                # 计算半径
                hitbox_radius = (rightX - leftX) / 30

                # 画圆（碰撞盒）
                draw_list.add_circle_filled(
                    screen_pos[0], screen_pos[1], hitbox_radius, imgui.get_color_u32_rgba(255, 255, 255, 0)
                )

                # 文字偏移
                offset_x, offset_y = 10, -10
                draw_list.add_text(screen_pos[0] + offset_x, screen_pos[1] + offset_y, bones_color, "")

            # ====================== 批量绘制连线 ======================
            for bone1, bone2 in bone_connections:
                # 获取骨骼点的位置
                if bone1 == "head":
                    pos1 = head_pos  # head_pos 是头部的坐标
                else:
                    pos1 = bone_positions.get(bone1, [-999, -999])  # 从 bone_positions 字典中获取坐标

                if bone2 == "head":
                    pos2 = head_pos  # head_pos 是头部的坐标
                else:
                    pos2 = bone_positions.get(bone2, [-999, -999])  # 从 bone_positions 字典中获取坐标

                # 如果某个点的坐标无效，跳过绘制
                if pos1 == [-999, -999] or pos2 == [-999, -999]:
                    continue

                # 如果是 head 和 neck 的连线，使用特殊颜色
                if (bone1 == "head" and bone2 == "neck") or (bone1 == "neck" and bone2 == "head"):
                    draw_list.add_line(pos1[0], pos1[1], pos2[0], pos2[1], head_bones_color, 1.5)  # 特殊颜色
                else:
                    draw_list.add_line(pos1[0], pos1[1], pos2[0], pos2[1], bones_color, 1.5)  # 正常颜色

# 透视开关的按键
key_pause_start = None  # 透视开启按键
key_pause_end = None    # 透视关闭按键

# 雷达开关的按键
key_radar_start = None  # 雷达开启按键
key_radar_end = None    # 雷达关闭按键

waiting_for_key = None  # 当前是否在等待按键
qt_app = None
qt_window = None  # 先不创建窗口


def set_key_for_action(action, key):
    global key_pause_start, key_pause_end, key_radar_start, key_radar_end
    if action == 'pause start':
        key_pause_start = key
        print(f"透视开启按键设置为: {key}")
    elif action == 'pause end':
        key_pause_end = key
        print(f"透视关闭按键设置为: {key}")
    elif action == 'radar start':
        key_radar_start = key
        print(f"雷达开启按键设置为: {key}")
    elif action == 'radar end':
        key_radar_end = key
        print(f"雷达关闭按键设置为: {key}")

def handle_key_press(window, key, scancode, action, mods):
    """处理键盘按键事件"""
    global waiting_for_key
    if action == glfw.PRESS or action == glfw.RELEASE:  # 处理按键按下和释放事件
        if waiting_for_key == 'pause start':
            set_key_for_action('pause start', key)
            waiting_for_key = None  # 结束按键设置
        elif waiting_for_key == 'pause end':
            set_key_for_action('pause end', key)
            waiting_for_key = None  # 结束按键设置
        elif waiting_for_key == 'radar start':
            set_key_for_action('radar start', key)
            waiting_for_key = None  # 结束按键设置
        elif waiting_for_key == 'radar end':
            set_key_for_action('radar end', key)
            waiting_for_key = None  # 结束按键设置

# 从外部 JSON 文件加载窗口几何设置
def load_window_geometry(file_path):
    try:
        with open(file_path, 'r') as f:
            config_data = json.load(f)
            return config_data.get('windowGeometry', {})
    except Exception as e:
        print(f"加载窗口几何设置时发生错误: {e}")
        return {}


# 在 load_window_geometry 函数附近添加
def save_window_geometry(file_path, geometry):
    """保存窗口几何设置到JSON文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
    except FileNotFoundError:
        config_data = {}

    config_data['windowGeometry'] = geometry

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=4, ensure_ascii=False)

    print(f"雷达窗口几何设置已保存: {geometry}")

# 读取配置文件
def load_length():
    try:
        with open("./XiaoPanSetting/length.json", "r") as length_file:
            length = json.load(length_file)
            return length
    except FileNotFoundError:
        print("配置文件未找到，使用默认设置")
        return {
            "radar": {
                "player_view_length": 800,
                "enemy_view_length": 600
            }
        }  # 默认值

# 加载配置
lengthSetting = load_length()



# 获取自定义的视距长度
player_view_length = lengthSetting["radar"]["player_view_length"]
enemy_view_length = lengthSetting["radar"]["enemy_view_length"]


# 计算角度（度）到弧度的转换
def angle_to_radians(angle):
    return np.radians(angle)

# 计算朝向线的终点
def calculate_view_end(position, angle, length=400):
    radians = angle_to_radians(angle)
    direction = (np.cos(radians), np.sin(radians))
    return (position[0] + direction[0] * length, position[1] + direction[1] * length)

# 定义一些常量
DWMWA_CLOAK = 13
DWMWA_EXCLUDED_FROM_CAPTURE = 20

# 加载 Windows 的 dwmapi 库
dwmapi = ctypes.windll.dwmapi

# 获取窗口句柄
def get_hwnd_from_window(window):
    hwnd = window.winId()  # 获取窗口句柄
    hwnd = int(hwnd)  # 将窗口句柄转换为整数
    return ctypes.c_void_p(hwnd)  # 使用 c_void_p 来处理句柄


class TransparentMapWindow(QOpenGLWidget):
    update_geometry_signal = pyqtSignal(int, int, int, int)
    def __init__(self, player_radar_color, enemy_radar_color, player_angle_color,
                 enemy_angle_color, is_radar_enabled, x=0, y=0, width=500, height=500):
        super().__init__()
        self.is_radar_enabled = is_radar_enabled
        self.player_radar_color = self.argb_to_rgba(player_radar_color)
        self.enemy_radar_color = self.argb_to_rgba(enemy_radar_color)
        self.player_angle_color = self.argb_to_rgba(player_angle_color)
        self.enemy_angle_color = self.argb_to_rgba(enemy_angle_color)
        self.update_geometry_signal.connect(self.on_update_geometry)

        # 游戏数据
        self.local_player_position = (0, 0)
        self.local_player_view_angle = 0
        self.enemy_data = []

        # 性能优化
        self.last_update_time = 0
        self.zoom_factor = 1.0
        self.view_range = 2500

        # 窗口几何设置文件路径
        self.geometry_config_path = "./XiaoPanSetting/radarResolution.json"

        # UI初始化 - 使用传入的参数
        self.initUI(x, y, width, height)

        # 定时器设置33ms≈30FPS
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_map)
        self.timer.start(30)

        # 初始数据加载
        self.load_data()

    @pyqtSlot(int, int, int, int)
    def on_update_geometry(self, x, y, width, height):
        """在Qt线程中安全更新几何设置"""
        self.setGeometry(x, y, width, height)
        geometry = {
            'x': x,
            'y': y,
            'width': width,
            'height': height
        }
        self.save_current_geometry()
        print(f"雷达窗口已安全更新: x={x}, y={y}, width={width}, height={height}")

    def initUI(self, x=0, y=0, width=500, height=500):
        self.setWindowTitle('OpenGL Radar')
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(x, y, width, height)

    def save_current_geometry(self):
        """保存当前窗口几何设置"""
        geometry = {
            'x': self.x(),
            'y': self.y(),
            'width': self.width(),
            'height': self.height()
        }
        save_window_geometry(self.geometry_config_path, geometry)

    def update_geometry(self, x, y, width, height):
        """更新窗口几何设置并应用"""
        self.setGeometry(x, y, width, height)
        geometry = {
            'x': x,
            'y': y,
            'width': width,
            'height': height
        }
        save_window_geometry(self.geometry_config_path, geometry)
        print(f"雷达窗口已更新: x={x}, y={y}, width={width}, height={height}")

    def initializeGL(self):
        glClearColor(0.0, 0.0, 0.0, 0.0)  # 完全透明背景
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_POINT_SMOOTH)
        glEnable(GL_LINE_SMOOTH)
        glHint(GL_POINT_SMOOTH_HINT, GL_NICEST)
        glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        aspect = w / h
        gluOrtho2D(-aspect, aspect, -1, 1)  # 初始投影，会在paintGL中调整

    def update_map(self):
        """更新地图数据"""
        # 加载数据
        self.load_data()

        # 触发重绘
        self.update()

    def paintGL(self):
        """OpenGL绘制主函数"""
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        if not self.is_radar_enabled:
            return  # 雷达禁用时不绘制

        # 设置以玩家为中心的视图
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        px, py = self.local_player_position
        view_size = 2500 * self.zoom_factor  # 使用固定2500范围或根据需求调整
        glOrtho(px - view_size, px + view_size,
                py - view_size, py + view_size,
                -1, 1)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        # 绘制玩家
        self.draw_player()

        # 绘制敌人
        self.draw_enemies()

    def draw_player(self):
        """绘制玩家标记和朝向线（使用配置的长度）"""
        x, y = self.local_player_position

        # 绘制玩家点
        glPointSize(10)
        glBegin(GL_POINTS)
        glColor4f(*self.player_radar_color)
        glVertex2f(x, y)
        glEnd()

        # 使用配置的长度绘制朝向线
        end_x, end_y = calculate_view_end(
            (x, y),
            self.local_player_view_angle,
            player_view_length * self.zoom_factor  # 应用缩放因子
        )

        glLineWidth(2)
        glBegin(GL_LINES)
        glColor4f(*self.player_angle_color)
        glVertex2f(x, y)
        glVertex2f(end_x, end_y)
        glEnd()

    def draw_enemies(self):
        """绘制敌人标记和朝向线（使用配置的长度）"""
        if not self.enemy_data:
            return

        # 绘制敌人点
        glPointSize(8)
        glBegin(GL_POINTS)
        for enemy in self.enemy_data:
            glColor4f(*self.enemy_radar_color)
            glVertex2f(*enemy['position'])
        glEnd()

        # 使用配置的长度绘制敌人朝向线
        glLineWidth(1.5)
        glBegin(GL_LINES)
        for enemy in self.enemy_data:
            x, y = enemy['position']
            end_x, end_y = calculate_view_end(
                (x, y),
                enemy['view_angle'],
                enemy_view_length * self.zoom_factor  # 应用缩放因子
            )
            glColor4f(*self.enemy_angle_color)
            glVertex2f(x, y)
            glVertex2f(end_x, end_y)
        glEnd()

        # 批量绘制敌人朝向线
        glLineWidth(1.5)
        glBegin(GL_LINES)
        for enemy in self.enemy_data:
            x, y = enemy['position']
            angle_rad = math.radians(enemy['view_angle'])
            length = 400 * self.zoom_factor
            end_x = x + length * math.cos(angle_rad)
            end_y = y + length * math.sin(angle_rad)

            glColor4f(*self.enemy_angle_color)
            glVertex2f(x, y)
            glVertex2f(end_x, end_y)
        glEnd()

        # 获取当前OpenGL视口参数
        viewport = glGetIntegerv(GL_VIEWPORT)
        width, height = viewport[2], viewport[3]

        # 设置QPainter
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Arial", 10)
        painter.setFont(font)

        # 转换OpenGL坐标到窗口像素坐标
        for enemy in self.enemy_data:
            # 将OpenGL坐标转换为屏幕坐标
            screen_x = ((enemy['position'][0] - (self.local_player_position[0] - self.view_range)) /
                        (2 * self.view_range)) * width
            screen_y = height - ((enemy['position'][1] - (self.local_player_position[1] - self.view_range)) /
                                 (2 * self.view_range)) * height

            health_text = str(enemy['health'])
            text_width = painter.fontMetrics().width(health_text)

            # 调整文本位置
            painter.drawText(
                int(screen_x - text_width / 2),
                int(screen_y - 15),  # 在敌人上方15像素
                health_text
            )

        painter.end()


    def update_colors(self, player_radar_color, enemy_radar_color, player_angle_color, enemy_angle_color):
        """更新雷达和朝向颜色"""
        self.player_radar_color = self.argb_to_rgba(player_radar_color)
        self.enemy_radar_color = self.argb_to_rgba(enemy_radar_color)
        self.player_angle_color = self.argb_to_rgba(player_angle_color)
        self.enemy_angle_color = self.argb_to_rgba(enemy_angle_color)


    def set_radar_enabled(self, is_radar_enabled):
        """更新雷达开关状态"""
        self.is_radar_enabled = is_radar_enabled

    def argb_to_rgba(self, argb):
        """将 ARGB 整数转换为 RGBA 元组（修正 R 和 B）"""
        a = (argb >> 24) & 0xFF
        r = (argb >> 16) & 0xFF
        g = (argb >> 8) & 0xFF
        b = argb & 0xFF
        return (b, g, r, a)  # 交换 R 和 B

    def rgba_list_to_argb(rgba):
        return (rgba[3] << 24) | (rgba[2] << 16) | (rgba[1] << 8) | rgba[0]  # 交换 R 和 B

    def update_map(self):
        now = time.time()
        if now - self.last_update_time < 0.03:  # 30FPS节流
            return

        self.load_data()
        self.last_update_time = now
        self.update()

    def load_data(self):
        try:
            player_data = get_player_data()
            if not player_data:
                return

            # 更新玩家数据
            if 'localPlayer' in player_data:
                self.local_player_position = tuple(player_data['localPlayer']['worldOrigin'][:2])
                self.local_player_view_angle = player_data['localPlayer']['viewAngles'][1]

            # 更新敌人数据
            self.enemy_data = []
            for entity in player_data.get('entities', []):
                try:
                    self.enemy_data.append({
                        'position': tuple(entity['worldPosition'][:2]),
                        'view_angle': entity['viewAngles'][1],
                        'health': entity['health']
                    })
                except KeyError:
                    continue

        except Exception as e:
            print(f"数据加载错误: {e}")


# 设备配置
device_config_path = "./XiaoPanSetting/xiaopanbox.json"  # 配置文件路径

# 串口默认配置（优先使用 JSON 配置）
SERIAL_PORT = "COM"  # 默认串口
BAUD_RATE = 19200  # 默认波特率
ser = None  # 串口对象
device_initialized = False  # 设备是否已连接

# 默认值（单位：秒）
SHOOT_DELAY_MIN = 0.013  # 开枪延迟最小值
SHOOT_DELAY_MAX = 0.015  # 开枪延迟最大值
SHOOT_INTERVAL_MIN = 0.05  # 开枪间隔最小值
SHOOT_INTERVAL_MAX = 0.06  # 开枪间隔最大值
recoil_sensitivity = 1.0

# 自瞄配置
CIRCLE_RADIUS = 100
AIM_SMOOTHING = 5.0  # 平滑系数(1.0-20.0)
AIM_STEP_DELAY = 0  # 每步延迟（单位：秒，可调节 0~0.02）

recoil_enabled = True
aimbot_enabled = True
aimbot_move_enabled = True

def load_default_device_config():
    global SERIAL_PORT, BAUD_RATE
    global SHOOT_DELAY_MIN, SHOOT_DELAY_MAX, SHOOT_INTERVAL_MIN, SHOOT_INTERVAL_MAX
    global recoil_sensitivity, recoil_enabled
    global CIRCLE_RADIUS, AIM_SMOOTHING, AIM_STEP_DELAY, aimbot_enabled, aimbot_move_enabled

    default_config = {
        "serial_port": "COM5",
        "baud_rate": 9600,
        "shoot_delay_min": 0.013,
        "shoot_delay_max": 0.015,
        "shoot_interval_min": 0.05,
        "shoot_interval_max": 0.06,
        "recoil_sensitivity": 1.0,
        "CIRCLE_RADIUS": 100,
        "AIM_SMOOTHING": 2.0,
        "AIM_STEP_DELAY": 0,
        "recoil_enabled": True,
        "aimbot_enabled": True,
        "aimbot_move_enabled": True

    }

    try:
        # 确保配置文件存在
        if not os.path.exists(device_config_path):
            os.makedirs(os.path.dirname(device_config_path), exist_ok=True)
            with open(device_config_path, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)

        # 读取配置
        with open(device_config_path, "r", encoding="utf-8") as file:
            config = json.load(file)

            # 确保所有键都存在
            for key in default_config:
                if key not in config:
                    config[key] = default_config[key]

            # 更新全局变量
            SERIAL_PORT = config["serial_port"]
            BAUD_RATE = config["baud_rate"]
            SHOOT_DELAY_MIN = float(config["shoot_delay_min"])
            SHOOT_DELAY_MAX = float(config["shoot_delay_max"])
            SHOOT_INTERVAL_MIN = float(config["shoot_interval_min"])
            SHOOT_INTERVAL_MAX = float(config["shoot_interval_max"])
            recoil_sensitivity = float(config["recoil_sensitivity"])
            CIRCLE_RADIUS = float(config["CIRCLE_RADIUS"])
            AIM_SMOOTHING = float(config["AIM_SMOOTHING"])
            AIM_STEP_DELAY = float(config["AIM_STEP_DELAY"])
            recoil_enabled = bool(config["recoil_enabled"])
            aimbot_enabled = bool(config["aimbot_enabled"])
            aimbot_move_enabled = bool(config["aimbot_move_enabled"])

    except Exception as e:
        print(f"❌ 加载配置文件失败: {e}")
        # 使用默认值
        SERIAL_PORT = default_config["serial_port"]
        BAUD_RATE = default_config["baud_rate"]
        SHOOT_DELAY_MIN = default_config["shoot_delay_min"]
        SHOOT_DELAY_MAX = default_config["shoot_delay_max"]
        SHOOT_INTERVAL_MIN = default_config["shoot_interval_min"]
        SHOOT_INTERVAL_MAX = default_config["shoot_interval_max"]
        recoil_sensitivity = default_config["recoil_sensitivity"]
        CIRCLE_RADIUS = default_config["CIRCLE_RADIUS"]
        AIM_SMOOTHING = default_config["AIM_SMOOTHING"]
        AIM_STEP_DELAY = default_config["AIM_STEP_DELAY"]
        recoil_enabled = default_config["recoil_enabled"]
        aimbot_enabled = default_config["aimbot_enabled"]
        aimbot_move_enabled = default_config["aimbot_move_enabled"]

# **打开串口**
def open_serial_port():
    global ser, SERIAL_PORT, BAUD_RATE, device_initialized
    if ser and ser.is_open:
        print("❌ 串口已打开")
        return True  # 如果串口已经打开，就不重新打开
    try:
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUD_RATE,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=1
        )
        print(f"✅ 串口已打开: {SERIAL_PORT} @ {BAUD_RATE} baud")
        device_initialized = True
        return True
    except serial.SerialException as e:
        print(f"❌ 串口打开失败: {e}")
        device_initialized = False
        return False

# **关闭串口**
def close_serial_port():
    global ser, device_initialized
    if ser and ser.is_open:
        ser.close()
        print("🔌 串口已关闭")
    device_initialized = False

# **发送数据**
def send_data(ser, data):
    try:
        ser.write(data)
        print(f"📤 Sent: {data.hex()}")
    except serial.SerialException as e:
        print(f"❌ 发送数据失败: {e}")


# 构建 CH9329 相对移动数据包
def build_mouse_move_packet(dx, dy, left_down=False):
    head = [0x57, 0xAB]
    addr = 0x00
    cmd = 0x05  # ✅ CMD_SEND_MS_REL_DATA
    length = 0x05
    data = [
        0x01,  # 固定值
        0x01 if left_down else 0x00,
        dx & 0xFF,
        dy & 0xFF,
        0x00  # 无滚轮
    ]
    checksum = (sum(head) + addr + cmd + length + sum(data)) & 0xFF
    return bytes(head + [addr, cmd, length] + data + [checksum])



def build_mouse_click_packet(left_down: bool):
    # 固定在当前位置，X/Y设为 0
    head = [0x57, 0xAB]
    addr = 0x00
    cmd = 0x04
    length = 0x07
    data = [
        0x02,                 # 固定值：必须为 0x02
        0x01 if left_down else 0x00,  # 左键按下 or 抬起
        0x00, 0x00,           # X 位置（无移动）
        0x00, 0x00,           # Y 位置（无移动）
        0x00                  # 滚轮
    ]
    checksum = (sum(head) + addr + cmd + length + sum(data)) & 0xFF
    packet = head + [addr, cmd, length] + data + [checksum]
    return bytes(packet)



# 假设你有一个压枪数据文件，比如 recoil_data.json
RECOIL_DATA_FILE = './XiaoPanSetting/recoil.json'

# **加载武器压枪数据**
def load_recoil_data(weapon_name):
    try:
        with open(RECOIL_DATA_FILE, 'r') as file:
            recoil_data = json.load(file)
            return recoil_data.get(weapon_name, None)
    except FileNotFoundError:
        print(f"压枪数据文件 {RECOIL_DATA_FILE} 找不到")
        return None
    except json.JSONDecodeError:
        print("压枪数据文件格式错误")
        return None


recoil_thread_running = False


# 压枪控制
def do_recoil_control(weapon_name, pattern):
    global recoil_thread_running, auto_aim_total_dx, auto_aim_total_dy
    try:
        print("开始压枪线程")
        compensated = False  # 是否已补偿过自瞄

        for x, y, d in pattern:
            _, _, _, recoil, _, = get_output_data()
            if recoil == 0:
                print("左键松开，停止压枪")
                break

            # 首次压枪时进行补偿
            if not compensated:
                print(f"🛠️ 压枪补偿: 修正({auto_aim_total_dx}, {auto_aim_total_dy})")
                x += auto_aim_total_dx
                y += auto_aim_total_dy
                auto_aim_total_dx = 0
                auto_aim_total_dy = 0
                compensated = True

            # 加入轻微扰动
            rx = x + random.choice([0, 0, -1, 0, 1])
            ry = y + random.choice([0, 0, -1, 0, 1])

            mx = round(rx / recoil_sensitivity)
            my = round(ry / recoil_sensitivity)
            rd = d + random.choice([-1, 0, 1])

            print(f"压枪移动: x={mx}, y={my}, 延迟={rd:.0f}ms")
            packet = build_mouse_move_packet(mx, my, left_down=False)
            ser.write(packet)
            time.sleep(rd / 1130)

    finally:
        recoil_thread_running = False

def process_recoil():
    global aim_thread_running, recoil_thread_running

    if not device_initialized:
        return

    aim_check, _, _, recoil, _, = get_output_data()

    # 🎯 自瞄命中，开启自动射击线程
    if aim_check == 1 and not aim_thread_running:
        aim_thread_running = True
        threading.Thread(target=do_auto_fire, daemon=True).start()

    # 获取玩家数据和武器名
    player_data = get_player_data()
    local_player = player_data.get("localPlayer", {})
    local_weapon_id = local_player.get("localWeaponID", 0)

    # 武器 ID 到名称映射
    weapon_names = {
        7: "ak47", 8: "aug", 10: "famas", 13: "galil", 60: "m4a1", 16: "m4a4", 17: "mac10",
        19: "p90", 23: "mp5sd", 24: "ump45", 33: "mp7", 34: "mp9", 39: "sg553",
        263151: "ak47", 263152: "aug", 263154: "famas", 263157: "galil", 263160: "m4a4",
        263161: "mac10", 263163: "p90", 263167: "mp5sd", 263183: "sg553", 263168: "ump45",
        263204: "m4a1", 263177: "mp7", 263178: "mp9",
    }

    current_weapon_name = weapon_names.get(local_weapon_id)
    if not current_weapon_name:
        return

    recoil_data = load_recoil_data(current_weapon_name)
    if not recoil_data:
        return

    # 合并压枪步伐
    merged_pattern = []
    for i in range(0, len(recoil_data), 2):
        x1, y1, d1 = recoil_data[i]
        x2, y2, d2 = recoil_data[i + 1] if i + 1 < len(recoil_data) else (0, 0, 0)
        merged_pattern.append((x1 + x2, y1 + y2, d1 + d2))

    # 启动压枪线程
    if recoil_enabled and recoil == 1 and not recoil_thread_running:
        recoil_thread_running = True
        threading.Thread(target=do_recoil_control, args=(current_weapon_name, merged_pattern), daemon=True).start()

def process_aimbot():
    global aim_thread_running, aim_target

    if not device_initialized:
        return

    if not aimbot_enabled:
        return

    # 获取输入状态
    aim_check, esp, radar, recoil, aim_move,= get_output_data()
    print(f"[DEBUG] recoil={recoil}, aim_check={aim_check}, esp={esp}, aim_move={aim_move}")

    if recoil == 1 or (aimbot_move_enabled and aim_move == 1):
        if not aim_target:
            return
        elif aim_thread_running:
            return
        else:
            aim_thread_running = True
            threading.Thread(target=do_auto_aim, args=(aim_target,), daemon=True).start()
    else:
        return


# 全局变量：自瞄偏移记录
auto_aim_total_dx = 0
auto_aim_total_dy = 0

def ease_out_quad(t):
    return 1 - (1 - t) * (1 - t)

def do_auto_aim(target):
    global aim_thread_running, auto_aim_total_dx, auto_aim_total_dy
    try:
        dx = target['dx']
        dy = target['dy']
        distance = target['distance']

        steps = max(3, int(distance * AIM_SMOOTHING / 15))
        print(f"📈 平滑移动：{steps} 步")

        # 重置累计自瞄偏移
        auto_aim_total_dx = 0
        auto_aim_total_dy = 0

        for i in range(steps):
            t = (i + 1) / steps
            eased_t = ease_out_quad(t)

            move_x = int(dx * eased_t) - int(dx * ease_out_quad(i / steps))
            move_y = int(dy * eased_t) - int(dy * ease_out_quad(i / steps))

            # 添加小扰动
            move_x += random.randint(-1, 1)
            move_y += random.randint(-1, 1)

            # 累加总偏移
            auto_aim_total_dx += move_x
            auto_aim_total_dy += move_y

            if not recoil_thread_running:
                send_data(ser, build_mouse_move_packet(move_x, move_y))
                print(f"\n🔫 [自瞄启动] 目标: {target['bone_name']} | "
                      f"距离: {distance:.1f}px | 偏移: ({dx:.1f},{dy:.1f})")
                print(f"  步 {i + 1}/{steps}: 移动({move_x},{move_y})")

            # 累加自瞄的实际偏移
            auto_aim_total_dx += move_x
            auto_aim_total_dy += move_y

            def clamp_auto_aim_offset(value):
                if value == 0:
                    return 0
                elif value < 0:
                    return max(value, -13) if value <= -2 else -2
                elif value > 0:
                    return min(value, 13) if value >= 2 else 2

            # 应用限制
            auto_aim_total_dx = clamp_auto_aim_offset(auto_aim_total_dx)
            auto_aim_total_dy = clamp_auto_aim_offset(auto_aim_total_dy)

            print(f"  当前累计自瞄偏移: dx={auto_aim_total_dx}, dy={auto_aim_total_dy}")

            time.sleep(AIM_STEP_DELAY)

        print("🎯 自瞄完成")
    except Exception as e:
        print(f"💥 自瞄异常: {str(e)}")
    finally:
        aim_thread_running = False

aim_thread_running = False

def do_auto_fire():
    global aim_thread_running
    try:
        print("🎯 自瞄命中，模拟左键点击")
        time.sleep(random.uniform(SHOOT_DELAY_MIN, SHOOT_DELAY_MAX))
        press_packet = build_mouse_click_packet(left_down=True)
        send_data(ser, press_packet)

        time.sleep(random.uniform(0.05, 0.06))  # 将固定0.04改为0.05-0.06秒随机延迟

        release_packet = build_mouse_click_packet(left_down=False)
        send_data(ser, release_packet)
        time.sleep(random.uniform(SHOOT_INTERVAL_MIN, SHOOT_INTERVAL_MAX))

        time.sleep(0.02)  # 短暂延迟


    finally:
        aim_thread_running = False


# 在全局添加一个标志位，用于控制是否自动保存
AUTO_SAVE_CONFIG = True  # 设为False可禁用自动保存

def save_device_config():
    """保存当前配置到JSON文件"""
    config = {
        "serial_port": SERIAL_PORT,
        "baud_rate": BAUD_RATE,
        "shoot_delay_min": round(SHOOT_DELAY_MIN, 4),  # 保留4位小数
        "shoot_delay_max": round(SHOOT_DELAY_MAX, 4),
        "shoot_interval_min": round(SHOOT_INTERVAL_MIN, 4),
        "shoot_interval_max": round(SHOOT_INTERVAL_MAX, 4),
        "recoil_sensitivity": round(recoil_sensitivity, 2),
        "CIRCLE_RADIUS": round(CIRCLE_RADIUS, 2),
        "AIM_SMOOTHING": round(AIM_SMOOTHING, 2),
        "AIM_STEP_DELAY": round(AIM_STEP_DELAY, 4),
        "recoil_enabled": recoil_enabled,
        "aimbot_enabled": aimbot_enabled,
        "aimbot_move_enabled": aimbot_move_enabled
    }

    try:
        with open(device_config_path, "w", encoding="utf-8") as file:
            json.dump(config, file, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"❌ 自动保存配置失败: {e}")


# JSON 文件路径
SETTINGS_JSON_PATH = "./XiaoPanSetting/setting.json"

# 默认配置
DEFAULT_SETTINGS = {
    "is_paused": True,
    "is_box_enabled": True,
    "is_skeleton_enabled": True,
    "is_money_enabled": True,
    "is_weapon_enabled": True,
    "is_status_enabled": True,
    "is_health_enabled": True,
    "is_armor_enabled": True,
    "is_c4time_enabled": True,
    "is_scoped_enabled": True,
    "is_player_enabled": True,
    "is_radar_enabled": True
}

# 加载配置
def load_settings():
    try:
        with open(SETTINGS_JSON_PATH, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        print("配置文件不存在，使用默认配置")
        return DEFAULT_SETTINGS
    except json.JSONDecodeError:
        print("配置文件格式错误，使用默认配置")
        return DEFAULT_SETTINGS

def save_settings(
    is_paused, is_box_enabled, is_skeleton_enabled, is_money_enabled,
    is_weapon_enabled, is_status_enabled, is_health_enabled, is_armor_enabled,
    is_c4time_enabled, is_scoped_enabled, is_player_enabled, is_radar_enabled,
    is_headbox_enabled, is_grenade_points_enabled, is_grenade_throw_enabled,
    is_round_test_enabled
):
    try:
        # 将当前变量状态保存到字典
        current_settings = {
            "is_paused": is_paused,
            "is_box_enabled": is_box_enabled,
            "is_skeleton_enabled": is_skeleton_enabled,
            "is_money_enabled": is_money_enabled,
            "is_weapon_enabled": is_weapon_enabled,
            "is_status_enabled": is_status_enabled,
            "is_health_enabled": is_health_enabled,
            "is_armor_enabled": is_armor_enabled,
            "is_c4time_enabled": is_c4time_enabled,
            "is_scoped_enabled": is_scoped_enabled,
            "is_player_enabled": is_player_enabled,
            "is_radar_enabled": is_radar_enabled,
            "is_headbox_enabled": is_headbox_enabled,
            "is_grenade_points_enabled": is_grenade_points_enabled,
            "is_grenade_throw_enabled": is_grenade_throw_enabled,
            "is_round_test_enabled": is_round_test_enabled

        }

        # 保存到 JSON 文件
        with open(SETTINGS_JSON_PATH, "w", encoding="utf-8") as file:
            json.dump(current_settings, file, indent=4, ensure_ascii=False)
        print("配置已保存")
    except Exception as e:
        print(f"保存配置失败: {e}")

# 初始化开关状态
settings = load_settings()

# 初始化雷达窗口几何设置变量
radar_window_x = 0
radar_window_y = 0
radar_window_width = 500
radar_window_height = 500


def main():
    global key_pause_start, key_pause_end, key_radar_start, key_radar_end
    global waiting_for_key, AUTO_SAVE_CONFIG, current_map
    global SHOOT_DELAY_MIN, SHOOT_DELAY_MAX, SHOOT_INTERVAL_MIN, SHOOT_INTERVAL_MAX
    global local_leg_X, local_leg_Y, local_leg_Z
    global local_pitch, local_yaw, current_weapon
    global CIRCLE_RADIUS, AIM_SMOOTHING, AIM_STEP_DELAY
    global radar_window_x, radar_window_y, radar_window_width, radar_window_height  # 添加这行



    # 确保变量已初始化
    load_default_device_config()

    # 尝试从配置文件加载初始值
    try:
        window_geometry = load_window_geometry("./XiaoPanSetting/radarResolution.json")
        if window_geometry:
            radar_window_x = window_geometry.get('x', 0)
            radar_window_y = window_geometry.get('y', 0)
            radar_window_width = window_geometry.get('width', 500)
            radar_window_height = window_geometry.get('height', 500)
    except:
        pass

    # 开关状态
    is_paused = settings["is_paused"]
    is_box_enabled = settings["is_box_enabled"]
    is_skeleton_enabled = settings["is_skeleton_enabled"]
    is_money_enabled = settings["is_money_enabled"]
    is_weapon_enabled = settings["is_weapon_enabled"]
    is_status_enabled = settings["is_status_enabled"]
    is_health_enabled = settings["is_health_enabled"]
    is_armor_enabled = settings["is_armor_enabled"]
    is_c4time_enabled = settings["is_c4time_enabled"]
    is_scoped_enabled = settings["is_scoped_enabled"]
    is_player_enabled = settings["is_player_enabled"]
    is_radar_enabled = settings["is_radar_enabled"]
    is_headbox_enabled = settings["is_headbox_enabled"]
    is_grenade_points_enabled = settings["is_grenade_points_enabled"]
    is_grenade_throw_enabled = settings["is_grenade_throw_enabled"]
    is_round_test_enabled = settings["is_round_test_enabled"]


    # 确保 current_menu 被初始化
    current_menu = '透视'  # 默认菜单

    global menu_visible
    # 设置是否显示菜单的标志
    menu_visible = True

    if not glfw.init():
        print("Could not initialize OpenGL context")
        exit(1)

    glfw.window_hint(glfw.TRANSPARENT_FRAMEBUFFER, glfw.TRUE)
    glfw_window = glfw.create_window(WINDOW_WIDTH, WINDOW_HEIGHT, "小潘潘", None, None)

    hwnd = glfw.get_win32_window(glfw_window)
    # 设置窗口样式以实现透明效果
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    style &= ~(win32con.WS_CAPTION | win32con.WS_THICKFRAME)
    win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)

    #窗口置顶
    #ex_style = win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT
    #win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)

    #win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, -2, -2, 0, 0,
    #                      win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)

    glfw.make_context_current(glfw_window)
    imgui.create_context()

    # 加载中文字体
    io = imgui.get_io()
    io.fonts.clear()  # 清空字体缓存

    # 加载字体设置的 JSON 文件
    json_path = "./XiaoPanSetting/fontsetting.json"
    if not os.path.exists(json_path):
        print(f"Font settings JSON not found: {json_path}")
        exit(1)

    with open(json_path, "r", encoding="utf-8") as file:
        font_settings = json.load(file)

    # 获取字体路径和大小
    font_path = font_settings["font_path"]
    font_size = font_settings["font_size"]

    # 获取中文字符范围
    glyph_ranges = io.fonts.get_glyph_ranges_chinese_full()

    # 添加字体
    font = io.fonts.add_font_from_file_ttf(font_path, font_size, None, glyph_ranges)

    impl = GlfwRenderer(glfw_window)

    # 加载颜色配置
    color_file = './XiaoPanSetting/color.json'  # 你的颜色配置文件路径

    player_radar_color = 0x00000000 if not is_radar_enabled else load_color_config(color_file, "player_radar_color")
    enemy_radar_color = 0x00000000 if not is_radar_enabled else load_color_config(color_file, "enemy_radar_color")
    player_angle_color = 0x00000000 if not is_radar_enabled else load_color_config(color_file, "player_angle_color")
    enemy_angle_color = 0x00000000 if not is_radar_enabled else load_color_config(color_file, "enemy_angle_color")

    def start_qt_window():
        global qt_app, qt_window

        # 确保 `QApplication` 只创建一次
        if QApplication.instance() is None:
            qt_app = QApplication(sys.argv)

        # 从配置文件加载初始几何设置
        window_geometry = load_window_geometry("./XiaoPanSetting/radarResolution.json")
        x = window_geometry.get('x', 0)
        y = window_geometry.get('y', 0)
        width = window_geometry.get('width', 500)
        height = window_geometry.get('height', 500)

        # 创建窗口
        global qt_window
        qt_window = TransparentMapWindow(player_radar_color, enemy_radar_color, player_angle_color,
                                         enemy_angle_color, is_radar_enabled,
                                         x=x, y=y, width=width, height=height)
        qt_window.show()
        qt_window.raise_()  # 将窗口置于最前面
        qt_window.activateWindow()  # 激活窗口

        # 正确启动 Qt 事件循环
        qt_app.exec_()

    # **创建独立线程运行 Qt**
    qt_thread = threading.Thread(target=start_qt_window, daemon=True)
    qt_thread.start()


    last_time = glfw.get_time()
    frame_count = 0

    while not glfw.window_should_close(glfw_window):
        process_recoil()
        process_aimbot()
        current_time = glfw.get_time()
        frame_count += 1

        if current_time - last_time >= 1.0:  # 每秒更新一次
            #print(f"FPS: {frame_count}")
            frame_count = 0
            last_time = current_time

        aim_check, esp, radar, recoil, aim_move = get_output_data()

        # 根据 esp 的值动态修改 is_paused
        if esp == 1:
            is_paused = True
        elif esp == 2:
            is_paused = False

        # 根据 radar 的值动态修改 is_radar_enabled
        if radar == 1:
            is_radar_enabled = True
            qt_window.set_radar_enabled(is_radar_enabled)  # 同步到窗口
        elif radar == 2:
            is_radar_enabled = False
            qt_window.set_radar_enabled(is_radar_enabled)  # 同步到窗口

        glfw.poll_events()
        impl.process_inputs()
        imgui.new_frame()

        # 设置覆盖窗口大小和位置
        imgui.set_next_window_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        imgui.set_next_window_position(0, 0)

        imgui.begin("overlay", flags=imgui.WINDOW_NO_TITLE_BAR | imgui.WINDOW_NO_RESIZE |
                    imgui.WINDOW_NO_SCROLLBAR | imgui.WINDOW_NO_COLLAPSE | imgui.WINDOW_NO_BACKGROUND)

        # 获取颜色，按开关的状态决定是否加载颜色配置
        player_color = load_color_config(color_file, "player_color") if is_player_enabled else 0x00000000
        weapon_color = load_color_config(color_file, "weapon_color") if is_weapon_enabled else 0x00000000
        bones_color = load_color_config(color_file, "bones_color") if is_skeleton_enabled else 0x00000000
        esp_color = load_color_config(color_file, "esp_color") if is_box_enabled else 0x00000000
        hp_color = load_color_config(color_file, "hp_color") if is_health_enabled else 0x00000000
        armor_color = load_color_config(color_file, "armor_color") if is_armor_enabled else 0x00000000
        money_color = load_color_config(color_file, "money_color") if is_money_enabled else 0x00000000
        state_color = load_color_config(color_file, "state_color") if is_status_enabled else 0x00000000
        scoped_color = load_color_config(color_file, "scoped_color") if is_scoped_enabled else 0x00000000
        c4time_color = load_color_config(color_file, "c4time_color") if is_c4time_enabled else 0x00000000
        head_bones_color = load_color_config(color_file, "head_bones_color") if is_headbox_enabled else 0x00000000
        grenade_points_color = load_color_config(color_file, "grenade_points_color") if is_grenade_points_enabled else 0x00000000
        grenade_throw_color = load_color_config(color_file, "grenade_throw_color") if is_grenade_throw_enabled else 0x00000000
        round_test_color = load_color_config(color_file,"round_test_color") if is_round_test_enabled else 0x00000000



        if is_paused:
            # 只有未暂停时才绘制 ESP
            esp_data = get_esp_data()
            bones_data = get_bones_data()
            view_matrix = get_view_matrix()
            player_data = get_player_data()

            draw_list = imgui.get_window_draw_list()
            draw_boxes_batch(draw_list, esp_data, bones_data, view_matrix, esp_color,player_color, bones_color,
                             hp_color, armor_color, weapon_color, money_color, state_color, c4time_color, scoped_color,
                             head_bones_color,grenade_points_color,grenade_throw_color,round_test_color,
                             WINDOW_WIDTH, WINDOW_HEIGHT, font,is_c4time_enabled,is_health_enabled,is_armor_enabled)

        gl.glClearColor(0, 0, 0, 0)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)

        if glfw.get_key(glfw_window, glfw.KEY_LEFT_ALT) == glfw.PRESS or glfw.get_key(glfw_window,glfw.KEY_RIGHT_ALT) == glfw.PRESS:
            if not is_alt_pressed:
                is_alt_pressed = True
                menu_visible = not menu_visible  # 切换菜单显示状态
        else:
            is_alt_pressed = False

        if menu_visible:
            # ✅ **设置 UI 风格**
            imgui.push_style_var(imgui.STYLE_WINDOW_ROUNDING, 12)  # 窗口圆角
            imgui.push_style_var(imgui.STYLE_FRAME_ROUNDING, 6)  # 按钮圆角
            imgui.push_style_var(imgui.STYLE_WINDOW_PADDING, (20, 20))  # 内边距
            imgui.push_style_var(imgui.STYLE_ITEM_SPACING, (12, 16))  # 项目间距
            imgui.push_style_var(imgui.STYLE_FRAME_PADDING, (10, 6))  # 按钮填充

            # 🎨 标题栏颜色（深灰色 + 轻微透明感）
            imgui.push_style_color(imgui.COLOR_TITLE_BACKGROUND, 1, 1, 1, 1)  # 深灰色标题栏
            imgui.push_style_color(imgui.COLOR_TITLE_BACKGROUND_ACTIVE, 1, 1, 1, 1)  # 激活状态稍微亮一点
            imgui.push_style_color(imgui.COLOR_TITLE_BACKGROUND_COLLAPSED, 1, 1, 1, 1)  # 收起状态与展开状态一致

            # 🏢 窗口背景（浅灰色 + 轻微透明）
            imgui.push_style_color(imgui.COLOR_WINDOW_BACKGROUND, 0.95, 0.95, 0.95, 1)  # 浅灰色背景，98% 透明度

            # 📝 文本颜色（深灰色）
            imgui.push_style_color(imgui.COLOR_TEXT, 0.1, 0.1, 0.1, 1)  # 深灰色文本

            # 🔘 按钮（浅灰色 + 精致边框）
            imgui.push_style_color(imgui.COLOR_BUTTON, 0.7, 0.7, 0.7, 1.0)  # 浅灰色按钮
            imgui.push_style_color(imgui.COLOR_BUTTON_HOVERED, 0.65, 0.65, 0.65, 1.0)  # 悬停时稍微深一点
            imgui.push_style_color(imgui.COLOR_BUTTON_ACTIVE, 0.55, 0.55, 0.55, 1.0)  # 按下时更深

            # 🔲 输入框背景（纯白色 + 悬停效果）
            imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND, 0.85, 0.85, 0.85, 1.0)  # 纯白输入框
            imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND_HOVERED, 0.75, 0.75, 0.75, 1.0)  # 悬停时淡灰色
            imgui.push_style_color(imgui.COLOR_FRAME_BACKGROUND_ACTIVE, 0.65, 0.65, 0.65, 1.0)  # 选中时更深一点

            # 🚀 分割线（浅灰色）
            imgui.push_style_color(imgui.COLOR_SEPARATOR, 0.1, 0.1, 0.1, 1.0)  # 浅灰色分割线

            # ✅ 复选框勾选颜色（科技感蓝色）
            imgui.push_style_color(imgui.COLOR_CHECK_MARK, 0.0, 0.6, 1.0, 1.0)  # 科技感蓝色

            # ✨ 滑动条（轻微的立体层次感）
            imgui.push_style_color(imgui.COLOR_SLIDER_GRAB, 0.3, 0.3, 0.3, 1.0)  # 滑动条手柄
            imgui.push_style_color(imgui.COLOR_SLIDER_GRAB_ACTIVE, 0.1, 0.1, 0.1, 1.0)  # 按住时变黑



            # 🖥️ **创建主窗口**
            imgui.begin("小潘潘 - 驱动透视")
            imgui.set_window_size(700, 440)  # 设置窗口大小为 600x400

            # 🟢 **UI 标题**
            imgui.text_colored("井底之蛙，不知海之宽阔，却知晓天空之蓝。", 0, 0.6, 1, 1.0)  # 霓虹蓝色标题
            # 🟢 **UI 标题**
            imgui.text_colored("开挂从来，都不是你目的，而是你一种手段。", 1, 0, 0, 1.0)  # 霓虹蓝色标题

            imgui.separator()  # 分割线

            # 检查窗口是否失去焦点
            if not imgui.is_window_focused():
                # 强制当前窗口保持焦点
                imgui.set_window_focus()  # 注意：这里不需要传递参数

            # 侧边菜单栏 (竖排)
            imgui.begin_child("Side Menu", width=120, height=280, border=True)  # 创建一个侧边菜单栏
            imgui.text("菜  单  栏")
            if imgui.button("透   视"):
                print("透视菜单被点击")
                current_menu = '透视'
            if imgui.button("自   瞄"):
                print("自瞄菜单被点击")
                current_menu = '自瞄'
            if imgui.button("雷   达"):
                print("雷达菜单被点击")
                current_menu = '雷达'
            if imgui.button("颜   色"):
                print("颜色菜单被点击")
                current_menu = '颜色'
            if imgui.button("杂   项"):
                print("杂项菜单被点击")
                current_menu = '杂项'
            imgui.end_child()  # 结束侧边栏

            # 主区域：透视菜单
            imgui.same_line()
            imgui.begin_child("Main Area", width=550, height=280, border=True)  # 主显示区域

            # 根据当前选择的菜单显示内容
            if current_menu == '透视':
                # 透视开关
                if imgui.button("透视开关"):
                    is_paused = not is_paused  # 切换透视开关
                imgui.same_line()
                changed, is_paused = imgui.checkbox("##", is_paused)  # 显示透视状态勾选框

                # 设置透视开启按键
                imgui.same_line()
                if imgui.button(f"开启按键: {key_pause_start if key_pause_start else '未设置'}"):
                    waiting_for_key = 'pause start'  # 开始设置透视开启按键

                # 设置透视关闭按键
                imgui.same_line()
                if imgui.button(f"关闭按键: {key_pause_end if key_pause_end else '未设置'}"):
                    waiting_for_key = 'pause end'  # 开始设置透视关闭按键

                # 显示当前按键设置状态
                if waiting_for_key and waiting_for_key.startswith('pause'):
                    imgui.text(f"请按下键盘键来设置{waiting_for_key}按键...")

                # 方框开关
                if imgui.button("方框开关"):
                    is_box_enabled = not is_box_enabled  # 切换开关状态
                imgui.same_line()
                changed, is_box_enabled = imgui.checkbox("##人物方框", is_box_enabled)  # 通过复选框显示状态

                # 骨骼开关
                if imgui.button("骨骼开关"):
                    is_skeleton_enabled = not is_skeleton_enabled
                imgui.same_line()
                changed, is_skeleton_enabled = imgui.checkbox("##人物骨骼", is_skeleton_enabled)

                # 名字开关
                if imgui.button("名字开关"):
                    is_player_enabled = not is_player_enabled
                imgui.same_line()
                changed, is_player_enabled = imgui.checkbox("##人物名字", is_player_enabled)

                # 金钱开关
                if imgui.button("金钱开关"):
                    is_money_enabled = not is_money_enabled
                imgui.same_line()
                changed, is_money_enabled = imgui.checkbox("##人物金钱", is_money_enabled)

                # 武器开关
                if imgui.button("武器开关"):
                    is_weapon_enabled = not is_weapon_enabled
                imgui.same_line()
                changed, is_weapon_enabled = imgui.checkbox("##人物武器", is_weapon_enabled)

                # 状态开关
                if imgui.button("状态开关"):
                    is_status_enabled = not is_status_enabled
                imgui.same_line()
                changed, is_status_enabled = imgui.checkbox("##人物状态", is_status_enabled)

                # 血量开关
                if imgui.button("血量开关"):
                    is_health_enabled = not is_health_enabled
                imgui.same_line()
                changed, is_health_enabled = imgui.checkbox("##人物血量", is_health_enabled)

                # 护甲开关
                if imgui.button("护甲开关"):
                    is_armor_enabled = not is_armor_enabled
                imgui.same_line()
                changed, is_armor_enabled = imgui.checkbox("##人物护甲", is_armor_enabled)

                # 瞄准镜开关
                if imgui.button("瞄准镜开关"):
                    is_scoped_enabled = not is_scoped_enabled  # 切换瞄准镜开关状态
                imgui.same_line()
                changed, is_scoped_enabled = imgui.checkbox("##瞄准镜", is_scoped_enabled)  # 通过复选框显示瞄准镜状态

                # C4计时开关
                if imgui.button("C4计时开关"):
                    is_c4time_enabled = not is_c4time_enabled  # 切换C4计时开关状态
                imgui.same_line()
                changed, is_c4time_enabled = imgui.checkbox("##C4计时", is_c4time_enabled)  # 通过复选框显示C4计时状态

                # 骨骼头部开关
                if imgui.button("骨骼头部开关"):
                    is_headbox_enabled = not is_headbox_enabled  # 切换骨骼头部开关状态
                imgui.same_line()
                changed, is_headbox_enabled = imgui.checkbox("##骨骼头部", is_headbox_enabled)  # 通过复选框显示C4计时状态

                # 投掷站立点开关
                if imgui.button("投掷点开关"):
                    is_grenade_points_enabled = not is_grenade_points_enabled  # 切换状态
                imgui.same_line()
                changed, is_grenade_points_enabled = imgui.checkbox("##投掷点", is_grenade_points_enabled)

                # 投掷点开关
                if imgui.button("投掷轨迹开关"):
                    is_grenade_throw_enabled = not is_grenade_throw_enabled  # 切换状态
                imgui.same_line()
                changed, is_grenade_throw_enabled = imgui.checkbox("##投掷轨迹", is_grenade_throw_enabled)

                # 自瞄调试开关
                if imgui.button("自瞄调试开关"):
                    is_round_test_enabled = not is_round_test_enabled  # 切换状态
                imgui.same_line()
                changed, is_round_test_enabled = imgui.checkbox("##自瞄调试", is_round_test_enabled)

            # --- 在你的 ImGui 渲染循环里添加这一段 ---
            if current_menu == '自瞄':
                global SERIAL_PORT, BAUD_RATE, device_initialized, ser
                global SHOOT_DELAY_MIN, SHOOT_DELAY_MAX, SHOOT_INTERVAL_MIN, SHOOT_INTERVAL_MAX
                global recoil_sensitivity, recoil_enabled
                global CIRCLE_RADIUS, AIM_SMOOTHING, AIM_STEP_DELAY
                global aimbot_enabled, aimbot_move_enabled

                imgui.separator()
                imgui.text("请输入串口配置:")

                # 串口号输入
                changed, SERIAL_PORT = imgui.input_text("串口号", SERIAL_PORT, 32)

                # 波特率输入
                changed, baudrate_input = imgui.input_text("波特率", str(BAUD_RATE), 32)
                try:
                    BAUD_RATE = int(baudrate_input)
                except ValueError:
                    BAUD_RATE = 9600  # 默认波特率

                # 连接设备
                if imgui.button("连接设备"):
                    close_serial_port()
                    if open_serial_port():
                        device_initialized = True
                    else:
                        device_initialized = False
                imgui.same_line()

                # 默认连接按钮
                if imgui.button("载入默认连接"):
                    close_serial_port()
                    SERIAL_PORT = "COM5"
                    BAUD_RATE = 9600
                    if open_serial_port():
                        device_initialized = True
                    else:
                        device_initialized = False

                imgui.separator()

                # 状态显示
                if device_initialized:
                    imgui.text("状态: 已连接")
                else:
                    imgui.text("状态: 未连接")

                imgui.separator()
                imgui.text("扳机参数调整:")

                # 开枪延迟 & 间隔参数
                changed, SHOOT_DELAY_MIN = imgui.input_float("开枪延迟最小值 (秒)", SHOOT_DELAY_MIN, 0.001, 0.01,
                                                             "%.3f")
                changed, SHOOT_DELAY_MAX = imgui.input_float("开枪延迟最大值 (秒)", SHOOT_DELAY_MAX, 0.001, 0.01,
                                                             "%.3f")
                changed, SHOOT_INTERVAL_MIN = imgui.input_float("开枪间隔最小值 (秒)", SHOOT_INTERVAL_MIN, 0.01, 0.1,
                                                                "%.3f")
                changed, SHOOT_INTERVAL_MAX = imgui.input_float("开枪间隔最大值 (秒)", SHOOT_INTERVAL_MAX, 0.01, 0.1,
                                                                "%.3f")

                # 自动保存（如果需要）
                if AUTO_SAVE_CONFIG and (
                        SHOOT_DELAY_MIN or SHOOT_DELAY_MAX or SHOOT_INTERVAL_MIN or SHOOT_INTERVAL_MAX):
                    save_device_config()

                # 显示当前数值
                imgui.text(f"当前延迟: {SHOOT_DELAY_MIN:.3f} ~ {SHOOT_DELAY_MAX:.3f} 秒")
                imgui.text(f"当前间隔: {SHOOT_INTERVAL_MIN:.3f} ~ {SHOOT_INTERVAL_MAX:.3f} 秒")

                # 加在 imgui.text("扳机参数调整:") 下面
                imgui.separator()
                imgui.text("压枪参数:")

                # 添加压枪灵敏度输入
                changed, recoil_sensitivity = imgui.input_float("压枪灵敏度", recoil_sensitivity, 0.1, 0.2, "%.2f")
                recoil_sensitivity = max(0.1, min(recoil_sensitivity, 5.0))  # 限制范围

                # 添加压枪开关（true/false）
                changed, recoil_enabled = imgui.checkbox("启用压枪", recoil_enabled)

                # 加在 imgui.text("扳机参数调整:") 下面
                imgui.separator()
                imgui.text("自瞄参数:")

                # 自瞄总开关
                changed, aimbot_enabled = imgui.checkbox("启用自瞄", aimbot_enabled)

                # 磁性扳机总开关
                changed, aimbot_move_enabled = imgui.checkbox("启用磁性扳机", aimbot_move_enabled)

                # 自瞄圆圈半径
                changed, CIRCLE_RADIUS = imgui.input_int("锁定圆圈半径 (像素)", CIRCLE_RADIUS)
                CIRCLE_RADIUS = max(10, min(CIRCLE_RADIUS, 1000))  # 限制范围

                # 在输入框上方添加提示文字
                imgui.text("平滑度范围: 0.1 到 20.0 (越高越平滑速度越慢，越低越不平滑速度越快)")

                # 平滑系数
                changed, AIM_SMOOTHING = imgui.input_float("平滑度", AIM_SMOOTHING, 0.1, 0.5, "%.2f")
                AIM_SMOOTHING = max(0.1, min(AIM_SMOOTHING, 20.0))  # 限制范围

                # 在输入框上方添加提示文字
                imgui.text("移动延迟，非必要不要调，只调平滑度")

                # 每步延迟
                changed, AIM_STEP_DELAY = imgui.input_float("移动延迟 (秒)", AIM_STEP_DELAY, 0.001, 0.01, "%.3f")
                AIM_STEP_DELAY = max(0.0, min(AIM_STEP_DELAY, 0.1))  # 限制范围

                # 自动保存压枪配置（可选）
                if AUTO_SAVE_CONFIG and changed:
                    save_device_config()

            elif current_menu == '雷达':

                # 正确处理 imgui.checkbox 的返回值
                changed, is_radar_enabled = imgui.checkbox("##雷达", is_radar_enabled)
                if changed:  # 如果复选框的状态发生变化
                    if qt_window:  # 如果窗口已创建
                        qt_window.set_radar_enabled(is_radar_enabled)  # 同步到窗口

                # 设置雷达开启按键
                imgui.same_line()
                if imgui.button(f"开启按键: {key_radar_start if key_radar_start else '未设置'}"):
                    waiting_for_key = 'radar start'  # 开始设置雷达开启按键

                # 设置雷达关闭按键
                imgui.same_line()
                if imgui.button(f"关闭按键: {key_radar_end if key_radar_end else '未设置'}"):
                    waiting_for_key = 'radar end'  # 开始设置雷达关闭按键

                # 显示当前按键设置状态
                if waiting_for_key and waiting_for_key.startswith('radar'):
                    imgui.text(f"请按下键盘键来设置{waiting_for_key}按键...")

                imgui.separator()
                imgui.text("雷达窗口几何设置:")


                # 宽度输入
                changed_width, radar_window_width = imgui.input_int("宽度", radar_window_width)
                # 高度输入
                changed_height, radar_window_height = imgui.input_int("高度", radar_window_height)

                # 限制最小尺寸
                radar_window_width = max(100, radar_window_width)
                radar_window_height = max(100, radar_window_height)

                # 应用按钮
                if imgui.button("应用几何设置"):
                    if qt_window:
                        # 使用信号/槽机制安全地更新Qt窗口
                        qt_window.update_geometry_signal.emit(
                            radar_window_x, radar_window_y,
                            radar_window_width, radar_window_height
                        )
                        imgui.text("几何设置已发送!")
                    else:
                        imgui.text("雷达窗口未创建!")

                imgui.same_line()

                # 保存当前按钮
                if imgui.button("保存当前窗口位置"):
                    if qt_window:
                        # 更新变量为当前窗口的实际值
                        radar_window_x = qt_window.x()
                        radar_window_y = qt_window.y()
                        radar_window_width = qt_window.width()
                        radar_window_height = qt_window.height()

                        # 保存到文件
                        geometry = {
                            'x': radar_window_x,
                            'y': radar_window_y,
                            'width': radar_window_width,
                            'height': radar_window_height
                        }
                        save_window_geometry("./XiaoPanSetting/radarResolution.json", geometry)
                        imgui.text("当前窗口位置已保存!")
                    else:
                        imgui.text("雷达窗口未创建!")

                # 显示当前窗口信息
                if qt_window:
                    imgui.text(f"当前: X={qt_window.x()}, Y={qt_window.y()}, "
                               f"宽={qt_window.width()}, 高={qt_window.height()}")

            elif current_menu == '颜色':
                # 颜色设置的内容
                imgui.text("颜色设置功能的内容")

                # 玩家颜色
                player_color_rgba = argb_to_rgba_list(player_color)
                normalized_player_color = normalize_color(player_color_rgba)
                changed, new_player_color = imgui.color_edit4("玩家颜色", *normalized_player_color)
                if changed:
                    new_player_color_rgba = [int(c * 255) for c in new_player_color]
                    # 交换 R 和 B
                    new_player_color_rgba[0], new_player_color_rgba[2] = new_player_color_rgba[2], \
                    new_player_color_rgba[0]
                    player_color = rgba_list_to_argb(new_player_color_rgba)
                    update_color_config(color_file, "player_color", new_player_color_rgba)

                # 武器颜色
                weapon_color_rgba = argb_to_rgba_list(weapon_color)
                normalized_weapon_color = normalize_color(weapon_color_rgba)
                changed, new_weapon_color = imgui.color_edit4("武器颜色", *normalized_weapon_color)
                if changed:
                    new_weapon_color_rgba = [int(c * 255) for c in new_weapon_color]
                    new_weapon_color_rgba[0], new_weapon_color_rgba[2] = new_weapon_color_rgba[2], \
                    new_weapon_color_rgba[0]
                    weapon_color = rgba_list_to_argb(new_weapon_color_rgba)
                    update_color_config(color_file, "weapon_color", new_weapon_color_rgba)

                # 骨骼颜色
                bones_color_rgba = argb_to_rgba_list(bones_color)
                normalized_bones_color = normalize_color(bones_color_rgba)
                changed, new_bones_color = imgui.color_edit4("骨骼颜色", *normalized_bones_color)
                if changed:
                    new_bones_color_rgba = [int(c * 255) for c in new_bones_color]
                    new_bones_color_rgba[0], new_bones_color_rgba[2] = new_bones_color_rgba[2], \
                    new_bones_color_rgba[0]
                    bones_color = rgba_list_to_argb(new_bones_color_rgba)
                    update_color_config(color_file, "bones_color", new_bones_color_rgba)

                # 骨骼头部颜色
                head_bones_color_rgba = argb_to_rgba_list(head_bones_color)
                normalized_head_bones_color = normalize_color(head_bones_color_rgba)
                changed, new_head_bones_color = imgui.color_edit4("骨骼头部颜色", *normalized_head_bones_color)
                if changed:
                    new_head_bones_color_rgba = [int(c * 255) for c in new_head_bones_color]
                    new_head_bones_color_rgba[0], new_head_bones_color_rgba[2] = new_head_bones_color_rgba[2], \
                        new_head_bones_color_rgba[0]
                    head_bones_color = rgba_list_to_argb(new_head_bones_color_rgba)
                    update_color_config(color_file, "head_bones_color", new_head_bones_color_rgba)

                # 血量颜色
                hp_color_rgba = argb_to_rgba_list(hp_color)
                normalized_hp_color = normalize_color(hp_color_rgba)
                changed, new_hp_color = imgui.color_edit4("血量颜色", *normalized_hp_color)
                if changed:
                    new_hp_color_rgba = [int(c * 255) for c in new_hp_color]
                    new_hp_color_rgba[0], new_hp_color_rgba[2] = new_hp_color_rgba[2], \
                    new_hp_color_rgba[0]
                    hp_color = rgba_list_to_argb(new_hp_color_rgba)
                    update_color_config(color_file, "hp_color", new_hp_color_rgba)

                # 护甲颜色
                armor_color_rgba = argb_to_rgba_list(armor_color)
                normalized_armor_color = normalize_color(armor_color_rgba)
                changed, new_armor_color = imgui.color_edit4("护甲颜色", *normalized_armor_color)
                if changed:
                    new_armor_color_rgba = [int(c * 255) for c in new_armor_color]
                    new_armor_color_rgba[0], new_armor_color_rgba[2] = new_armor_color_rgba[2], \
                    new_armor_color_rgba[0]
                    armor_color = rgba_list_to_argb(new_armor_color_rgba)
                    update_color_config(color_file, "armor_color", new_armor_color_rgba)

                # 方框颜色
                esp_color_rgba = argb_to_rgba_list(esp_color)
                normalized_esp_color = normalize_color(esp_color_rgba)
                changed, new_esp_color = imgui.color_edit4("方框颜色", *normalized_esp_color)
                if changed:
                    new_esp_color_rgba = [int(c * 255) for c in new_esp_color]
                    new_esp_color_rgba[0], new_esp_color_rgba[2] = new_esp_color_rgba[2], \
                    new_esp_color_rgba[0]
                    esp_color = rgba_list_to_argb(new_esp_color_rgba)
                    update_color_config(color_file, "esp_color", new_esp_color_rgba)

                # 金钱颜色
                money_color_rgba = argb_to_rgba_list(money_color)
                normalized_money_color = normalize_color(money_color_rgba)
                changed, new_money_color = imgui.color_edit4("金钱颜色", *normalized_money_color)
                if changed:
                    new_money_color_rgba = [int(c * 255) for c in new_money_color]
                    new_money_color_rgba[0], new_money_color_rgba[2] = new_money_color_rgba[2], \
                    new_money_color_rgba[0]
                    money_color = rgba_list_to_argb(new_money_color_rgba)
                    update_color_config(color_file, "money_color", new_money_color_rgba)

                # 状态颜色
                state_color_rgba = argb_to_rgba_list(state_color)
                normalized_state_color = normalize_color(state_color_rgba)
                changed, new_state_color = imgui.color_edit4("状态颜色", *normalized_state_color)
                if changed:
                    new_state_color_rgba = [int(c * 255) for c in new_state_color]
                    new_state_color_rgba[0], new_state_color_rgba[2] = new_state_color_rgba[2], \
                    new_state_color_rgba[0]
                    state_color = rgba_list_to_argb(new_state_color_rgba)
                    update_color_config(color_file, "state_color", new_state_color_rgba)

                # 瞄准镜颜色
                scoped_color_rgba = argb_to_rgba_list(scoped_color)
                normalized_scoped_color = normalize_color(scoped_color_rgba)
                changed, new_scoped_color = imgui.color_edit4("瞄准镜颜色", *normalized_scoped_color)
                if changed:
                    new_scoped_color_rgba = [int(c * 255) for c in new_scoped_color]
                    new_scoped_color_rgba[0], new_scoped_color_rgba[2] = new_scoped_color_rgba[2], \
                    new_scoped_color_rgba[0]
                    scoped_color = rgba_list_to_argb(new_scoped_color_rgba)
                    update_color_config(color_file, "scoped_color", new_scoped_color_rgba)

                # C4计时颜色
                c4time_color_rgba = argb_to_rgba_list(c4time_color)
                normalized_c4time_color = normalize_color(c4time_color_rgba)
                changed, new_c4time_color = imgui.color_edit4("C4计时颜色", *normalized_c4time_color)
                if changed:
                    new_c4time_color_rgba = [int(c * 255) for c in new_c4time_color]
                    new_c4time_color_rgba[0], new_c4time_color_rgba[2] = new_c4time_color_rgba[2], \
                    new_c4time_color_rgba[0]
                    c4time_color = rgba_list_to_argb(new_c4time_color_rgba)
                    update_color_config(color_file, "c4time_color", new_c4time_color_rgba)

                # 站立点颜色
                grenade_points_color_rgba = argb_to_rgba_list(grenade_points_color)
                normalized_grenade_points_color = normalize_color(grenade_points_color_rgba)
                changed, new_grenade_points_color = imgui.color_edit4("站立点颜色", *normalized_grenade_points_color)
                if changed:
                    new_grenade_points_color_rgba = [int(c * 255) for c in new_grenade_points_color]
                    new_grenade_points_color_rgba[0], new_grenade_points_color_rgba[2] = new_grenade_points_color_rgba[
                        2], new_grenade_points_color_rgba[0]

                    grenade_points_color = rgba_list_to_argb(new_grenade_points_color_rgba)
                    update_color_config(color_file, "grenade_points_color", new_grenade_points_color_rgba)

                # 投掷点颜色
                grenade_throw_color_rgba = argb_to_rgba_list(grenade_throw_color)
                normalized_grenade_throw_color = normalize_color(grenade_throw_color_rgba)
                changed, new_grenade_throw_color = imgui.color_edit4("投掷点颜色", *normalized_grenade_throw_color)
                if changed:
                    new_grenade_throw_color_rgba = [int(c * 255) for c in new_grenade_throw_color]
                    new_grenade_throw_color_rgba[0], new_grenade_throw_color_rgba[2] = new_grenade_throw_color_rgba[2], \
                    new_grenade_throw_color_rgba[0]

                    grenade_throw_color = rgba_list_to_argb(new_grenade_throw_color_rgba)
                    update_color_config(color_file, "grenade_throw_color", new_grenade_throw_color_rgba)

                # 自瞄调试颜色
                round_test_color_rgba = argb_to_rgba_list(round_test_color)
                normalized_round_test_color = normalize_color(round_test_color_rgba)
                changed, new_round_test_color = imgui.color_edit4("自瞄调试颜色", *normalized_round_test_color)
                if changed:
                    new_round_test_color_rgba = [int(c * 255) for c in new_round_test_color]
                    new_round_test_color_rgba[0], new_round_test_color_rgba[2] = new_round_test_color_rgba[2], \
                    new_round_test_color_rgba[0]

                    round_test_color = rgba_list_to_argb(new_round_test_color_rgba)
                    update_color_config(color_file, "round_test_color", new_round_test_color_rgba)

                # 玩家雷达颜色
                player_radar_color_rgba = argb_to_rgba_list(player_radar_color)
                normalized_player_radar_color = normalize_color(player_radar_color_rgba)
                changed, new_player_radar_color = imgui.color_edit4("玩家雷达颜色", *normalized_player_radar_color)
                if changed:
                    new_player_radar_color_rgba = [int(c * 255) for c in new_player_radar_color]
                    new_player_radar_color_rgba[0], new_player_radar_color_rgba[2] = new_player_radar_color_rgba[2], \
                    new_player_radar_color_rgba[0]
                    player_radar_color = rgba_list_to_argb(new_player_radar_color_rgba)
                    update_color_config(color_file, "player_radar_color", new_player_radar_color_rgba)
                    if qt_window:  # 如果窗口已创建
                        qt_window.update_colors(player_radar_color, enemy_radar_color, player_angle_color,
                                                enemy_angle_color)

                # 敌人雷达颜色
                enemy_radar_color_rgba = argb_to_rgba_list(enemy_radar_color)
                normalized_enemy_radar_color = normalize_color(enemy_radar_color_rgba)
                changed, new_enemy_radar_color = imgui.color_edit4("敌人雷达颜色", *normalized_enemy_radar_color)
                if changed:
                    new_enemy_radar_color_rgba = [int(c * 255) for c in new_enemy_radar_color]
                    new_enemy_radar_color_rgba[0], new_enemy_radar_color_rgba[2] = new_enemy_radar_color_rgba[2], \
                    new_enemy_radar_color_rgba[0]
                    enemy_radar_color = rgba_list_to_argb(new_enemy_radar_color_rgba)
                    update_color_config(color_file, "enemy_radar_color", new_enemy_radar_color_rgba)
                    if qt_window:  # 如果窗口已创建
                        qt_window.update_colors(player_radar_color, enemy_radar_color, player_angle_color,
                                                enemy_angle_color)

                # 玩家角度颜色
                player_angle_color_rgba = argb_to_rgba_list(player_angle_color)
                normalized_player_angle_color = normalize_color(player_angle_color_rgba)
                changed, new_player_angle_color = imgui.color_edit4("玩家角度颜色", *normalized_player_angle_color)
                if changed:
                    new_player_angle_color_rgba = [int(c * 255) for c in new_player_angle_color]
                    new_player_angle_color_rgba[0], new_player_angle_color_rgba[2] = new_player_angle_color_rgba[2], \
                    new_player_angle_color_rgba[0]
                    player_angle_color = rgba_list_to_argb(new_player_angle_color_rgba)
                    update_color_config(color_file, "player_angle_color", new_player_angle_color_rgba)
                    if qt_window:  # 如果窗口已创建
                        qt_window.update_colors(player_radar_color, enemy_radar_color, player_angle_color,
                                                enemy_angle_color)

                # 敌人角度颜色
                enemy_angle_color_rgba = argb_to_rgba_list(enemy_angle_color)
                normalized_enemy_angle_color = normalize_color(enemy_angle_color_rgba)
                changed, new_enemy_angle_color = imgui.color_edit4("敌人角度颜色", *normalized_enemy_angle_color)
                if changed:
                    new_enemy_angle_color_rgba = [int(c * 255) for c in new_enemy_angle_color]
                    new_enemy_angle_color_rgba[0], new_enemy_angle_color_rgba[2] = new_enemy_angle_color_rgba[2], \
                    new_enemy_angle_color_rgba[0]
                    enemy_angle_color = rgba_list_to_argb(new_enemy_angle_color_rgba)
                    update_color_config(color_file, "enemy_angle_color", new_enemy_angle_color_rgba)
                    if qt_window:  # 如果窗口已创建
                        qt_window.update_colors(player_radar_color, enemy_radar_color, player_angle_color,
                                                enemy_angle_color)

            elif current_menu == '杂项':
                imgui.text("杂项功能的内容")

                if imgui.button("保存点位"):
                    # 获取玩家数据
                    player_data = get_player_data()
                    local_player = player_data.get("localPlayer", {})
                    local_weapon_id = local_player.get("localWeaponID", 0)
                    current_map = local_player.get("mapName", "unknown").lower()  # 统一转为小写

                    # 获取自身位置坐标（locallegX, locallegY, locallegZ）
                    local_leg_X = local_player.get("locallegX", 0.0)
                    local_leg_Y = local_player.get("locallegY", 0.0)
                    local_leg_Z = local_player.get("locallegZ", 0.0)

                    # 获取玩家视角信息（pitch 和 yaw）
                    local_pitch = local_player.get("viewAngles", [0.0, 0.0, 0.0])[0]  # 获取俯仰角度
                    local_yaw = local_player.get("viewAngles", [0.0, 0.0, 0.0])[1]  # 获取偏航角度

                    weapon_name_map = {
                        43: "闪", 45: "烟", 46: "火", 48: "火",
                        263187: "闪", 263189: "烟", 263190: "火", 263192: "火"
                    }

                    current_weapon = weapon_name_map.get(local_weapon_id, None)  # 获取武器名称，默认为 None

                    # 保存点位到 CSV
                    save_point_to_csv(
                        current_map,
                        local_leg_X, local_leg_Y,
                        local_leg_Z,
                        local_pitch, local_yaw,  # 使用已经定义的 local_pitch 和 local_yaw
                        grenade=current_weapon,
                        description="自定义点位",  # 可以让用户输入
                        throw_type="站投"  # 也可以做成下拉选择
                    )

                # 保存按钮
                if imgui.button("保存配置"):
                    save_settings(is_paused, is_box_enabled, is_skeleton_enabled, is_money_enabled,
                                  is_weapon_enabled, is_status_enabled, is_health_enabled, is_armor_enabled,
                                  is_c4time_enabled, is_scoped_enabled, is_player_enabled, is_radar_enabled,
                                  is_headbox_enabled, is_grenade_points_enabled, is_grenade_throw_enabled,
                                  is_round_test_enabled)

                # 退出程序按钮
                if imgui.button("退出程序"):
                    os._exit(0)

            imgui.end_child()  # 结束主区域
            imgui.end()  # **结束 UI 窗口**

            # ✅ **恢复默认样式**
            imgui.pop_style_color(15)  # **正确弹出 2 个颜色**
            imgui.pop_style_var(5)  # **正确弹出 5 个样式**

        # 设置GLFW键盘按键回调函数
        glfw.set_key_callback(glfw_window, handle_key_press)
        imgui.end()  # 结束 overlay 窗口
        imgui.end_frame()
        imgui.render()
        impl.render(imgui.get_draw_data())
        glfw.swap_buffers(glfw_window)
        glfw.swap_interval(0)  # 禁用V-Sync，允许无限制帧率

        # 监听开启按键
        if key_pause_start and glfw.get_key(glfw_window, key_pause_start) == glfw.PRESS:
            is_paused = True  # 按下开启按键时设置为开启

        # 监听关闭按键
        if key_pause_end and glfw.get_key(glfw_window, key_pause_end) == glfw.PRESS:
            is_paused = False  # 按下关闭按键时设置为恢复

        # 监听开启按键
        if key_radar_start and glfw.get_key(glfw_window, key_radar_start) == glfw.PRESS:
            is_radar_enabled = True  # 按下开启按键时设置为开启

        # 监听关闭按键
        if key_radar_end and glfw.get_key(glfw_window, key_radar_end) == glfw.PRESS:
            is_radar_enabled = False  # 按下关闭按键时设置为恢复

    impl.shutdown()
    glfw.terminate()

def on_quit(icon):
    os._exit(0)
    icon.stop()

# 托盘图标点击事件
def setup_tray_icon(icon):
    icon.visible = True
    icon.update_menu()

# 创建托盘图标
icon = pystray.Icon("test_icon", Image.open("./XiaoPanSetting/favicon.ico"), "托盘程序", menu=pystray.Menu(
    item('退出', on_quit)
))

# 启动托盘图标线程
def start_tray_icon():
    icon.run(setup_tray_icon)

if __name__ == "__main__":
    tray_thread = threading.Thread(target=start_tray_icon)
    tray_thread.daemon = True
    tray_thread.start()
    main()
