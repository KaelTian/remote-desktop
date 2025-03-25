import sys
import socket
import json
from PyQt6.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, 
                            QWidget, QLineEdit, QPushButton, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from pynput import mouse, keyboard

class ClientThread(QThread):
    status_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.running = True
        self.socket = None
        self.mouse_listener = None
        self.keyboard_listener = None

    def run(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.status_signal.emit("已连接到服务器")

            # 设置鼠标监听器
            self.mouse_listener = mouse.Listener(
                on_click=self.on_click,
                on_move=self.on_move)
            self.mouse_listener.start()

            # 设置键盘监听器
            self.keyboard_listener = keyboard.Listener(
                on_press=self.on_press,
                on_release=self.on_release)
            self.keyboard_listener.start()

            while self.running:
                pass

        except Exception as e:
            self.error_signal.emit(f"连接错误: {str(e)}")
        finally:
            self.stop()

    def on_click(self, x, y, button, pressed):
        if pressed:
            command = {
                'type': 'mouse_click',
                'x': x,
                'y': y
            }
            self.send_command(command)

    def on_move(self, x, y):
        pass  # 可以在这里添加鼠标移动事件的处理

    def on_press(self, key):
        try:
            key_char = key.char
            command = {
                'type': 'key_press',
                'key': key_char
            }
            self.send_command(command)
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
        except AttributeError:
            pass

    def send_command(self, command):
        try:
            if self.socket:
                self.socket.send(json.dumps(command).encode('utf-8'))
        except Exception as e:
            self.error_signal.emit(f"发送命令错误: {str(e)}")

    def stop(self):
        self.running = False
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        if self.socket:
            self.socket.close()

class ClientWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("远程控制客户端")
        self.setGeometry(100, 100, 400, 200)
        
        # 创建主窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 服务器地址输入
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("服务器IP地址")
        self.host_input.setText("localhost")
        layout.addWidget(self.host_input)
        
        # 连接按钮
        self.connect_button = QPushButton("连接到服务器")
        self.connect_button.clicked.connect(self.toggle_connection)
        layout.addWidget(self.connect_button)
        
        # 状态标签
        self.status_label = QLabel("未连接")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        self.client_thread = None

    def toggle_connection(self):
        if self.client_thread is None:
            # 连接到服务器
            host = self.host_input.text()
            self.client_thread = ClientThread(host, 5000)
            self.client_thread.status_signal.connect(self.update_status)
            self.client_thread.error_signal.connect(self.show_error)
            self.client_thread.start()
            self.connect_button.setText("断开连接")
        else:
            # 断开连接
            self.client_thread.stop()
            self.client_thread = None
            self.connect_button.setText("连接到服务器")
            self.status_label.setText("未连接")

    def update_status(self, message):
        self.status_label.setText(message)

    def show_error(self, message):
        QMessageBox.critical(self, "错误", message)

    def closeEvent(self, event):
        if self.client_thread:
            self.client_thread.stop()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ClientWindow()
    window.show()
    sys.exit(app.exec()) 