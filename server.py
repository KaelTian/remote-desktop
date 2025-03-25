import sys
import socket
import json
import pyautogui
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt, QThread, pyqtSignal

class ServerThread(QThread):
    status_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(('0.0.0.0', 5000))
        self.server_socket.listen(1)
        self.status_signal.emit("服务器启动，等待连接...")

    def run(self):
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                self.status_signal.emit(f"客户端已连接: {address}")
                
                while self.running:
                    data = client_socket.recv(1024).decode('utf-8')
                    if not data:
                        break
                    
                    command = json.loads(data)
                    self.handle_command(command)
                
                client_socket.close()
                self.status_signal.emit("客户端断开连接")
            except Exception as e:
                self.status_signal.emit(f"错误: {str(e)}")
                break

    def handle_command(self, command):
        try:
            if command['type'] == 'mouse_click':
                pyautogui.click(x=command['x'], y=command['y'])
            elif command['type'] == 'key_press':
                pyautogui.press(command['key'])
            elif command['type'] == 'key_release':
                pyautogui.keyUp(command['key'])
        except Exception as e:
            print(f"执行命令时出错: {str(e)}")

    def stop(self):
        self.running = False
        self.server_socket.close()

class ServerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("远程控制服务器")
        self.setGeometry(100, 100, 400, 200)
        
        # 创建主窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 状态标签
        self.status_label = QLabel("正在启动服务器...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        # 启动服务器线程
        self.server_thread = ServerThread()
        self.server_thread.status_signal.connect(self.update_status)
        self.server_thread.start()

    def update_status(self, message):
        self.status_label.setText(message)

    def closeEvent(self, event):
        self.server_thread.stop()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ServerWindow()
    window.show()
    sys.exit(app.exec()) 