import sys
import socket
import json
import logging
import threading
import time
from datetime import datetime
from PIL import Image, ImageTk
from PyQt6.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, 
                            QWidget, QLineEdit, QPushButton, QMessageBox,
                            QHBoxLayout, QScrollArea)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QImage, QPixmap
from pynput import mouse, keyboard
from mss import mss

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('client.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ScreenCaptureThread(QThread):
    frame_ready = pyqtSignal(QImage)
    error_signal = pyqtSignal(str)

    def __init__(self, socket):
        super().__init__()
        self.socket = socket
        self.running = True
        self.sct = None  # 将在run方法中初始化
        self.last_send_time = 0
        self.frame_interval = 1/30  # 30 FPS

    def run(self):
        try:
            # 在线程中初始化mss
            self.sct = mss()
            logger.info("屏幕捕获线程启动")
            
            while self.running:
                try:
                    current_time = time.time()
                    if current_time - self.last_send_time >= self.frame_interval:
                        # 捕获屏幕
                        monitor = self.sct.monitors[1]  # 主显示器
                        screenshot = self.sct.grab(monitor)
                        
                        # 转换为PIL Image
                        img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
                        
                        # 压缩图像
                        img = img.resize((800, 600), Image.Resampling.LANCZOS)
                        
                        # 转换为QImage
                        qimg = QImage(img.tobytes(), img.width, img.height, img.width * 3, QImage.Format.Format_RGB888)
                        
                        # 发送帧
                        self.frame_ready.emit(qimg)
                        
                        # 发送到服务器
                        self.send_frame(img)
                        
                        self.last_send_time = current_time
                    
                    time.sleep(0.001)  # 防止CPU过载
                    
                except Exception as e:
                    logger.error(f"屏幕捕获循环错误: {str(e)}")
                    time.sleep(1)  # 发生错误时等待一秒再继续
                    continue
                    
        except Exception as e:
            error_msg = f"屏幕捕获线程错误: {str(e)}"
            logger.error(error_msg)
            self.error_signal.emit(error_msg)
        finally:
            self.stop()

    def send_frame(self, img):
        try:
            # 将图像转换为字节
            img_bytes = img.tobytes()
            # 发送帧类型标识
            self.socket.send(b'F')
            # 发送图像大小
            self.socket.send(len(img_bytes).to_bytes(4, 'big'))
            # 发送图像数据
            self.socket.send(img_bytes)
        except Exception as e:
            logger.error(f"发送帧错误: {str(e)}")
            raise

    def stop(self):
        self.running = False
        if self.sct:
            self.sct.close()
        logger.info("屏幕捕获线程已停止")

class ClientThread(QThread):
    status_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    frame_ready = pyqtSignal(QPixmap)

    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.running = True
        self.socket = None
        self.mouse_listener = None
        self.keyboard_listener = None
        self.screen_capture = None

    def run(self):
        try:
            logger.info(f"正在连接到服务器 {self.host}:{self.port}")
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.status_signal.emit("已连接到服务器")
            logger.info("成功连接到服务器")

            # 设置鼠标监听器
            self.mouse_listener = mouse.Listener(
                on_click=self.on_click,
                on_move=self.on_move)
            self.mouse_listener.start()
            logger.info("鼠标监听器已启动")

            # 设置键盘监听器
            self.keyboard_listener = keyboard.Listener(
                on_press=self.on_press,
                on_release=self.on_release)
            self.keyboard_listener.start()
            logger.info("键盘监听器已启动")

            # 启动屏幕捕获
            self.screen_capture = ScreenCaptureThread(self.socket)
            self.screen_capture.frame_ready.connect(self.handle_frame)
            self.screen_capture.error_signal.connect(self.error_signal)
            self.screen_capture.start()
            logger.info("屏幕捕获已启动")

            while self.running:
                pass

        except Exception as e:
            error_msg = f"连接错误: {str(e)}"
            logger.error(error_msg)
            self.error_signal.emit(error_msg)
        finally:
            self.stop()

    def handle_frame(self, qimg):
        # 更新预览窗口
        pixmap = QPixmap.fromImage(qimg)
        self.frame_ready.emit(pixmap)

    def on_click(self, x, y, button, pressed):
        if pressed:
            command = {
                'type': 'mouse_click',
                'x': x,
                'y': y
            }
            self.send_command(command)
            logger.debug(f"发送鼠标点击事件: x={x}, y={y}")

    def on_move(self, x, y):
        command = {
            'type': 'mouse_move',
            'x': x,
            'y': y
        }
        self.send_command(command)
        logger.debug(f"发送鼠标移动事件: x={x}, y={y}")

    def on_press(self, key):
        try:
            key_char = key.char
            command = {
                'type': 'key_press',
                'key': key_char
            }
            self.send_command(command)
            logger.debug(f"发送按键按下事件: {key_char}")
        except AttributeError:
            pass

    def on_release(self, key):
        try:
            key_char = key.char
            command = {
                'type': 'key_release',
                'key': key_char
            }
            self.send_command(command)
            logger.debug(f"发送按键释放事件: {key_char}")
        except AttributeError:
            pass

    def send_command(self, command):
        try:
            if self.socket:
                # 发送命令类型标识
                self.socket.send(b'C')
                # 发送命令数据
                self.socket.send(json.dumps(command).encode('utf-8'))
        except Exception as e:
            error_msg = f"发送命令错误: {str(e)}"
            logger.error(error_msg)
            self.error_signal.emit(error_msg)

    def stop(self):
        self.running = False
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        if self.screen_capture:
            self.screen_capture.stop()
        if self.socket:
            self.socket.close()
        logger.info("客户端已停止")

class ClientWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("远程控制客户端")
        self.setGeometry(100, 100, 1000, 800)
        
        # 创建主窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 创建连接控制区域
        control_layout = QHBoxLayout()
        
        # 服务器地址输入
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("服务器IP地址")
        self.host_input.setText("localhost")
        control_layout.addWidget(self.host_input)
        
        # 连接按钮
        self.connect_button = QPushButton("连接到服务器")
        self.connect_button.clicked.connect(self.toggle_connection)
        control_layout.addWidget(self.connect_button)
        
        # 状态标签
        self.status_label = QLabel("未连接")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        control_layout.addWidget(self.status_label)
        
        layout.addLayout(control_layout)
        
        # 创建预览区域
        preview_layout = QHBoxLayout()
        
        # 本地预览
        local_preview = QVBoxLayout()
        local_label = QLabel("本地预览")
        local_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        local_preview.addWidget(local_label)
        
        self.local_screen = QLabel()
        self.local_screen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.local_screen.setMinimumSize(400, 300)
        self.local_screen.setStyleSheet("border: 1px solid black;")
        local_preview.addWidget(self.local_screen)
        
        preview_layout.addLayout(local_preview)
        
        # 远程预览
        remote_preview = QVBoxLayout()
        remote_label = QLabel("远程预览")
        remote_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        remote_preview.addWidget(remote_label)
        
        self.remote_screen = QLabel()
        self.remote_screen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.remote_screen.setMinimumSize(400, 300)
        self.remote_screen.setStyleSheet("border: 1px solid black;")
        remote_preview.addWidget(self.remote_screen)
        
        preview_layout.addLayout(remote_preview)
        
        layout.addLayout(preview_layout)
        
        self.client_thread = None
        logger.info("客户端界面初始化完成")

    def toggle_connection(self):
        if self.client_thread is None:
            # 连接到服务器
            host = self.host_input.text()
            self.client_thread = ClientThread(host, 5000)
            self.client_thread.status_signal.connect(self.update_status)
            self.client_thread.error_signal.connect(self.show_error)
            self.client_thread.frame_ready.connect(self.update_remote_screen)
            self.client_thread.start()
            self.connect_button.setText("断开连接")
            logger.info(f"正在连接到服务器: {host}")
        else:
            # 断开连接
            self.client_thread.stop()
            self.client_thread = None
            self.connect_button.setText("连接到服务器")
            self.status_label.setText("未连接")
            logger.info("已断开与服务器的连接")

    def update_status(self, message):
        self.status_label.setText(message)
        logger.info(f"状态更新: {message}")

    def show_error(self, message):
        QMessageBox.critical(self, "错误", message)
        logger.error(f"错误: {message}")

    def update_remote_screen(self, pixmap):
        self.remote_screen.setPixmap(pixmap)

    def closeEvent(self, event):
        if self.client_thread:
            self.client_thread.stop()
        logger.info("应用程序关闭")
        event.accept()

if __name__ == '__main__':
    logger.info("启动远程控制客户端")
    app = QApplication(sys.argv)
    window = ClientWindow()
    window.show()
    sys.exit(app.exec()) 