import sys
import socket
import json
import logging
import pyautogui
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt, QThread, pyqtSignal
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

    def __init__(self):
        super().__init__()
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(('0.0.0.0', 5000))
        self.server_socket.listen(1)
        self.status_signal.emit("服务器启动，等待连接...")
        logger.info("服务器启动，等待连接...")

    def run(self):
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                self.status_signal.emit(f"客户端已连接: {address}")
                logger.info(f"客户端已连接: {address}")
                
                while self.running:
                    # 接收命令类型
                    command_type = client_socket.recv(1).decode('utf-8')
                    
                    if command_type == 'C':  # Command
                        # 接收命令数据
                        data = client_socket.recv(1024).decode('utf-8')
                        if not data:
                            break
                        
                        command = json.loads(data)
                        self.handle_command(command)
                    elif command_type == 'F':  # Frame
                        # 接收帧大小
                        size_bytes = client_socket.recv(4)
                        frame_size = int.from_bytes(size_bytes, 'big')
                        
                        # 接收帧数据
                        frame_data = b''
                        while len(frame_data) < frame_size:
                            chunk = client_socket.recv(min(frame_size - len(frame_data), 4096))
                            if not chunk:
                                break
                            frame_data += chunk
                        
                        if len(frame_data) == frame_size:
                            # 创建QImage
                            qimg = QImage(frame_data, 800, 600, 800 * 3, QImage.Format.Format_RGB888)
                            self.frame_ready.emit(qimg)
                
                client_socket.close()
                self.status_signal.emit("客户端断开连接")
                logger.info("客户端断开连接")
            except Exception as e:
                error_msg = f"错误: {str(e)}"
                logger.error(error_msg)
                self.status_signal.emit(error_msg)
                break

    def handle_command(self, command):
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
        self.server_socket.close()
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
        
        # 屏幕预览
        self.screen_preview = QLabel()
        self.screen_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen_preview.setMinimumSize(800, 600)
        self.screen_preview.setStyleSheet("border: 1px solid black;")
        layout.addWidget(self.screen_preview)
        
        # 启动服务器线程
        self.server_thread = ServerThread()
        self.server_thread.status_signal.connect(self.update_status)
        self.server_thread.frame_ready.connect(self.update_screen)
        self.server_thread.start()
        
        logger.info("服务器界面初始化完成")

    def update_status(self, message):
        self.status_label.setText(message)
        logger.info(f"状态更新: {message}")

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