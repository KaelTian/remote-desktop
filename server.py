import sys
import socket
import json
import logging
import threading
import time
import pyautogui
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QImage, QPixmap

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ServerThread(QThread):
    status_signal = pyqtSignal(str)
    frame_ready = pyqtSignal(QImage)
    client_connected = pyqtSignal(str)  # 新增客户端连接信号
    client_disconnected = pyqtSignal()  # 新增客户端断开信号

    def __init__(self):
        super().__init__()
        self.running = True
        self.server_socket = None
        self.client_socket = None
        self.client_address = None
        self.last_heartbeat = 0
        self.heartbeat_timeout = 5  # 心跳超时时间（秒）
        self.heartbeat_check_timer = None

    def run(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', 5000))
            self.server_socket.listen(1)
            self.status_signal.emit("服务器启动，等待连接...")
            logger.info("服务器启动，等待连接...")

            while self.running:
                try:
                    if not self.client_socket:
                        self.client_socket, self.client_address = self.server_socket.accept()
                        self.client_socket.settimeout(1)  # 设置接收超时
                        self.last_heartbeat = time.time()
                        self.client_connected.emit(f"{self.client_address[0]}:{self.client_address[1]}")
                        logger.info(f"客户端已连接: {self.client_address}")
                        self.start_heartbeat_check()

                    # 接收命令类型
                    try:
                        command_type = self.client_socket.recv(1)
                        if not command_type:
                            raise ConnectionError("连接已断开")

                        if command_type == b'C':  # Command
                            self.handle_command()
                        elif command_type == b'F':  # Frame
                            self.handle_frame()
                        elif command_type == b'P':  # Heartbeat
                            self.handle_heartbeat()
                    except socket.timeout:
                        continue  # 超时继续循环
                    except Exception as e:
                        raise

                except Exception as e:
                    error_msg = f"客户端连接错误: {str(e)}"
                    logger.error(error_msg)
                    self.handle_client_error()
                    time.sleep(1)  # 等待一秒后继续监听

        except Exception as e:
            error_msg = f"服务器错误: {str(e)}"
            logger.error(error_msg)
            self.status_signal.emit(error_msg)
        finally:
            self.stop()

    def handle_command(self):
        try:
            # 接收命令数据
            data = self.client_socket.recv(1024).decode('utf-8')
            if not data:
                raise ConnectionError("连接已断开")

            command = json.loads(data)
            self.execute_command(command)
        except Exception as e:
            logger.error(f"处理命令错误: {str(e)}")
            raise

    def handle_frame(self):
        try:
            # 接收帧大小
            size_bytes = self.client_socket.recv(4)
            if not size_bytes:
                raise ConnectionError("连接已断开")
            frame_size = int.from_bytes(size_bytes, 'big')

            # 接收帧数据
            frame_data = b''
            while len(frame_data) < frame_size:
                chunk = self.client_socket.recv(min(frame_size - len(frame_data), 4096))
                if not chunk:
                    raise ConnectionError("连接已断开")
                frame_data += chunk

            if len(frame_data) == frame_size:
                # 创建QImage
                qimg = QImage(frame_data, 800, 600, 800 * 3, QImage.Format.Format_RGB888)
                self.frame_ready.emit(qimg)
        except Exception as e:
            logger.error(f"处理帧错误: {str(e)}")
            raise

    def handle_heartbeat(self):
        self.last_heartbeat = time.time()
        try:
            self.client_socket.send(b'P')  # 回复心跳
        except:
            pass

    def start_heartbeat_check(self):
        if self.heartbeat_check_timer:
            self.heartbeat_check_timer.stop()
        self.heartbeat_check_timer = QTimer()
        self.heartbeat_check_timer.timeout.connect(self.check_heartbeat)
        self.heartbeat_check_timer.start(1000)  # 每秒检查一次

    def check_heartbeat(self):
        if self.client_socket and time.time() - self.last_heartbeat > self.heartbeat_timeout:
            logger.warning("心跳超时，客户端可能已断开")
            self.handle_client_error()

    def handle_client_error(self):
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None
            self.client_address = None
            self.client_disconnected.emit()
            self.status_signal.emit("客户端断开连接")
            logger.info("客户端断开连接")

    def execute_command(self, command):
        try:
            if command['type'] == 'mouse_click':
                pyautogui.click(x=command['x'], y=command['y'])
                logger.debug(f"执行鼠标点击: x={command['x']}, y={command['y']}")
            elif command['type'] == 'mouse_move':
                pyautogui.moveTo(x=command['x'], y=command['y'])
                logger.debug(f"执行鼠标移动: x={command['x']}, y={command['y']}")
            elif command['type'] == 'key_press':
                pyautogui.press(command['key'])
                logger.debug(f"执行按键按下: {command['key']}")
            elif command['type'] == 'key_release':
                pyautogui.keyUp(command['key'])
                logger.debug(f"执行按键释放: {command['key']}")
        except Exception as e:
            error_msg = f"执行命令时出错: {str(e)}"
            logger.error(error_msg)
            raise

    def stop(self):
        self.running = False
        if self.heartbeat_check_timer:
            self.heartbeat_check_timer.stop()
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        logger.info("服务器已停止")

class ServerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("远程控制服务器")
        self.setGeometry(100, 100, 800, 600)
        
        # 创建主窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 状态标签
        self.status_label = QLabel("正在启动服务器...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        # 客户端信息标签
        self.client_label = QLabel("等待客户端连接...")
        self.client_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.client_label)
        
        # 屏幕预览
        self.screen_preview = QLabel()
        self.screen_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen_preview.setMinimumSize(800, 600)
        self.screen_preview.setStyleSheet("border: 1px solid black;")
        layout.addWidget(self.screen_preview)
        
        # 添加操作说明
        instruction_label = QLabel("使用说明：\n1. 服务器已启动，等待客户端连接\n2. 客户端连接后，将显示远程屏幕内容\n3. 客户端可以控制本机的鼠标和键盘")
        instruction_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instruction_label.setStyleSheet("background-color: #f0f0f0; padding: 10px; border-radius: 5px;")
        layout.addWidget(instruction_label)
        
        # 启动服务器线程
        self.server_thread = ServerThread()
        self.server_thread.status_signal.connect(self.update_status)
        self.server_thread.frame_ready.connect(self.update_screen)
        self.server_thread.client_connected.connect(self.handle_client_connected)
        self.server_thread.client_disconnected.connect(self.handle_client_disconnected)
        self.server_thread.start()
        
        logger.info("服务器界面初始化完成")

    def update_status(self, message):
        self.status_label.setText(message)
        logger.info(f"状态更新: {message}")

    def handle_client_connected(self, address):
        self.client_label.setText(f"客户端已连接: {address}")
        self.client_label.setStyleSheet("color: green;")

    def handle_client_disconnected(self):
        self.client_label.setText("等待客户端连接...")
        self.client_label.setStyleSheet("")
        self.screen_preview.clear()

    def update_screen(self, qimg):
        pixmap = QPixmap.fromImage(qimg)
        self.screen_preview.setPixmap(pixmap)

    def closeEvent(self, event):
        if self.server_thread:
            self.server_thread.stop()
        logger.info("应用程序关闭")
        event.accept()

if __name__ == '__main__':
    logger.info("启动远程控制服务器")
    app = QApplication(sys.argv)
    window = ServerWindow()
    window.show()
    sys.exit(app.exec()) 