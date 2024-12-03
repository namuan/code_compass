import sys
import os
import random
from pathlib import Path

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QFileDialog)
from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush
import time
from queue import Queue
import threading
import numpy as np

class FakeAPIHandler:
    def __init__(self):
        self.responses = [
            "This file contains important data structures",
            "Multiple function definitions found",
            "Appears to be a configuration file",
            "Complex algorithms detected",
            "Database interactions present",
            "Network communication code",
            "User interface components",
            "Testing framework implementation",
            "Data processing routines",
            "Authentication mechanisms"
        ]

    def process_file(self, file_path, prompt):
        # Simulate API delay
        time.sleep(0.5)

        # Generate random response
        base_response = random.choice(self.responses)
        file_type = os.path.splitext(file_path)[1]
        return f"{base_response} [{file_type}] - {random.randint(1000, 9999)}"

class FileSystemEmitter(QObject):
    new_data = pyqtSignal(str, str, str, str)  # signals for (topic_type, parent, content, api_response)

    def __init__(self):
        super().__init__()
        self.running = True
        self.data_queue = Queue()
        self.processed_items = set()
        self.api_handler = FakeAPIHandler()

    def file_system_generator(self, root_dir):
        for root, dirs, files in os.walk(root_dir):
            rel_path = os.path.relpath(root, root_dir)
            if rel_path == '.':
                parent = "Main Topic"
            else:
                parent = os.path.basename(os.path.dirname(root))

            current_dir = os.path.basename(root)
            if current_dir and current_dir != '.':
                yield ("subtopic", parent, current_dir, None)

            for file in files:
                file_path = os.path.join(root, file)
                api_response = self.api_handler.process_file(file_path, "dummy_prompt")
                yield ("detail", current_dir if current_dir != '.' else "Main Topic",
                       file, api_response)

            time.sleep(0.2)

    def start_monitoring(self, directory):
        self.directory = directory
        self.thread = threading.Thread(target=self.process_directory)
        self.thread.daemon = True
        self.thread.start()

    def process_directory(self):
        while self.running:
            for topic_type, parent, content, api_response in self.file_system_generator(self.directory):
                item_key = f"{topic_type}:{parent}:{content}"
                if item_key not in self.processed_items:
                    self.processed_items.add(item_key)
                    self.new_data.emit(topic_type, parent, content, api_response)

            time.sleep(2)

    def stop(self):
        self.running = False

class ClusterDiagramWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(800, 600)

        self.central_topic = "Main Topic"
        self.subtopics = {}
        self.api_responses = {}

        self.file_emitter = FileSystemEmitter()
        self.file_emitter.new_data.connect(self.handle_new_data)

        # Remove animation-related attributes
        # self.select_directory()
        hard_coded_directory = Path.home() / "workspace" / "scramble"
        self.file_emitter.start_monitoring(hard_coded_directory.as_posix())

    def select_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Directory to Monitor")
        if directory:
            self.file_emitter.start_monitoring(directory)

    def handle_new_data(self, topic_type, parent, content, api_response):
        if topic_type == "subtopic":
            if content not in self.subtopics:
                self.subtopics[content] = []
        else:  # detail
            if parent in self.subtopics:
                if len(self.subtopics[parent]) < 8:
                    self.subtopics[parent].append(content)
                    if api_response:
                        self.api_responses[content] = api_response
            elif parent == "Main Topic":
                if "Root Files" not in self.subtopics:
                    self.subtopics["Root Files"] = []
                if len(self.subtopics["Root Files"]) < 8:
                    self.subtopics["Root Files"].append(content)
                    if api_response:
                        self.api_responses[content] = api_response

        if len(self.subtopics) > 8:
            oldest_topic = list(self.subtopics.keys())[0]
            del self.subtopics[oldest_topic]

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        central_font = QFont("Arial", 14, QFont.Weight.Bold)
        subtopic_font = QFont("Arial", 12)
        detail_font = QFont("Arial", 9)

        center = QPoint(self.width() // 2, self.height() // 2)

        # Draw central topic with fixed size
        painter.setFont(central_font)
        central_radius = 80
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        painter.setBrush(QBrush(QColor(255, 255, 200)))
        painter.drawEllipse(center, central_radius, central_radius)

        painter.drawText(
            center.x() - central_radius,
            center.y() - central_radius,
            central_radius * 2,
            central_radius * 2,
            Qt.AlignmentFlag.AlignCenter,
            self.central_topic
        )

        if self.subtopics:
            num_subtopics = len(self.subtopics)
            angle_step = 360 / num_subtopics
            distance_from_center = 200
            subtopic_radius = 60

            for i, (subtopic, details) in enumerate(self.subtopics.items()):
                angle = i * angle_step * (3.14159 / 180)
                x = center.x() + distance_from_center * np.cos(angle)
                y = center.y() + distance_from_center * np.sin(angle)
                subtopic_pos = QPoint(int(x), int(y))

                painter.setPen(QPen(Qt.GlobalColor.black, 2))
                painter.drawLine(center, subtopic_pos)

                painter.setBrush(QBrush(QColor(200, 255, 200)))
                painter.drawEllipse(subtopic_pos, subtopic_radius, subtopic_radius)

                painter.setFont(subtopic_font)
                text_rect = painter.boundingRect(
                    int(x - subtopic_radius),
                    int(y - subtopic_radius),
                    subtopic_radius * 2,
                    subtopic_radius * 2,
                    Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                    subtopic
                )
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                    subtopic
                )

                if details:
                    detail_radius = 40
                    num_details = len(details)
                    detail_angle_step = 60 / max(num_details - 1, 1)
                    base_angle = angle * (180 / 3.14159) - 30

                    for j, detail in enumerate(details):
                        detail_angle = (base_angle + j * detail_angle_step) * (3.14159 / 180)
                        detail_distance = 120
                        dx = x + detail_distance * np.cos(detail_angle)
                        dy = y + detail_distance * np.sin(detail_angle)
                        detail_pos = QPoint(int(dx), int(dy))

                        painter.setPen(QPen(Qt.GlobalColor.black, 1))
                        painter.drawLine(subtopic_pos, detail_pos)

                        painter.setBrush(QBrush(QColor(200, 200, 255)))
                        painter.drawEllipse(detail_pos, detail_radius, detail_radius)

                        painter.setFont(detail_font)
                        text = detail
                        if detail in self.api_responses:
                            api_text = str(self.api_responses[detail])[:30] + "..."
                            text = f"{detail}\n{api_text}"

                        text_rect = painter.boundingRect(
                            int(dx - detail_radius),
                            int(dy - detail_radius),
                            detail_radius * 2,
                            detail_radius * 2,
                            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                            text
                        )
                        painter.drawText(
                            text_rect,
                            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                            text
                        )

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('CodeConstellation')
        self.setGeometry(100, 100, 1200, 900)

        self.diagram_widget = ClusterDiagramWidget()
        self.setCentralWidget(self.diagram_widget)

    def closeEvent(self, event):
        self.diagram_widget.file_emitter.stop()
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()