import math
import os
import random
import sys
import threading
import time
from pathlib import Path
from queue import Queue

import numpy as np
from PyQt6.QtCore import pyqtProperty
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtCore import QEasingCurve
from PyQt6.QtCore import QObject
from PyQt6.QtCore import QPointF
from PyQt6.QtCore import QPropertyAnimation
from PyQt6.QtCore import QRectF
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QBrush
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QFont
from PyQt6.QtGui import QKeySequence
from PyQt6.QtGui import QPainter
from PyQt6.QtGui import QPainterPath
from PyQt6.QtGui import QPen
from PyQt6.QtGui import QShortcut
from PyQt6.QtGui import QTextDocument
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtWidgets import QGraphicsLineItem
from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtWidgets import QGraphicsTextItem
from PyQt6.QtWidgets import QGraphicsView
from PyQt6.QtWidgets import QLabel
from PyQt6.QtWidgets import QMainWindow


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
            "Authentication mechanisms",
        ]

    def process_file(self, file_path, prompt):
        # Simulate API delay
        # time.sleep(0.5)

        # Generate random response
        base_response = random.choice(self.responses)
        file_type = os.path.splitext(file_path)[1]
        return f"{base_response} [{file_type}] - {random.randint(1000, 9999)}"

    def read_file_content(self, file_path, max_size=10000):
        """Read file content if it's a text file"""
        # List of text file extensions
        text_extensions = {
            ".txt",
            ".py",
            ".js",
            ".html",
            ".css",
            ".json",
            ".xml",
            ".yaml",
            ".yml",
            ".md",
            ".rst",
            ".ini",
            ".conf",
            ".sh",
            ".bat",
            ".ps1",
            ".java",
            ".cpp",
            ".c",
            ".h",
            ".hpp",
            ".cs",
            ".go",
            ".rb",
            ".php",
            ".pl",
            ".swift",
        }

        file_ext = os.path.splitext(file_path)[1].lower()

        if file_ext in text_extensions:
            try:
                # Check file size first
                if os.path.getsize(file_path) > max_size:
                    return (
                        "File too large to display (showing first 10000 bytes)...\n\n"
                    )

                with open(file_path, encoding="utf-8") as f:
                    content = f.read(max_size)
                    return content
            except Exception as e:
                return f"Error reading file: {str(e)}"

        return None


class FileSystemEmitter(QObject):
    new_data = pyqtSignal(
        str, str, str, str, str
    )  # signals for (topic_type, parent, content, api_response, file_content)

    def __init__(self):
        super().__init__()
        self.running = True
        self.data_queue = Queue()
        self.processed_items = set()
        self.api_handler = FakeAPIHandler()

    def file_system_generator(self, root_dir):
        # List of directories to exclude
        exclude_dirs = {".git", ".idea", "__pycache__", "node_modules", "venv", "env"}

        for root, dirs, files in os.walk(root_dir):
            # Remove excluded directories from dirs list to prevent descending into them
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            rel_path = os.path.relpath(root, root_dir)
            if rel_path == ".":
                parent = "Main Topic"
            else:
                parent = os.path.basename(os.path.dirname(root))

            current_dir = os.path.basename(root)
            if current_dir and current_dir != "." and current_dir not in exclude_dirs:
                yield ("subtopic", parent, current_dir, None, None)

            for file in files:
                file_path = os.path.join(root, file)
                if os.path.dirname(file_path).split("/")[-1] not in exclude_dirs:
                    api_response = self.api_handler.process_file(
                        file_path, "dummy_prompt"
                    )
                    file_content = self.api_handler.read_file_content(file_path)
                    yield (
                        "detail",
                        current_dir if current_dir != "." else "Main Topic",
                        file,
                        api_response,
                        file_content,
                    )

            time.sleep(0.2)

    def start_monitoring(self, directory):
        self.directory = directory
        self.thread = threading.Thread(target=self.process_directory)
        self.thread.daemon = True
        self.thread.start()

    def process_directory(self):
        while self.running:
            for (
                topic_type,
                parent,
                content,
                api_response,
                file_content,
            ) in self.file_system_generator(self.directory):
                item_key = f"{topic_type}:{parent}:{content}"
                if item_key not in self.processed_items:
                    print(f"Processing {topic_type=}, {item_key=}")
                    self.processed_items.add(item_key)
                    self.new_data.emit(
                        topic_type, parent, content, api_response, file_content
                    )

            time.sleep(2)

    def stop(self):
        self.running = False


class TextNodeItem(QGraphicsTextItem):
    def __init__(
        self, text, width, height, background_color, parent=None, is_detail=False
    ):
        super().__init__()

        self.is_detail = is_detail
        self.full_text = text

        # For detail nodes, extract filename from the full text
        if self.is_detail:
            self.display_text = text.split("\n")[0]  # First line contains filename
        else:
            self.display_text = text

        self.setPlainText(self.display_text)

        self.min_width = width
        self.min_height = height
        self.collapsed_width = min(width, height) * 0.8  # Collapsed rectangle width
        self.collapsed_height = min(width, height) * 0.4  # Collapsed rectangle height

        # Remove padding since we're not using an outer rectangle
        self.padding = 0

        # Animation properties
        self.animation_progress = 1.0  # 0.0 = collapsed, 1.0 = expanded
        self.target_progress = 1.0
        self.animation_speed = 0.15
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.update_animation)
        self.animation_timer.setInterval(16)  # ~60 FPS

        # Store connectors
        self.incoming_connectors = []
        self.outgoing_connectors = []

        # Set up text properties
        self.setDefaultTextColor(Qt.GlobalColor.black)
        self.setFont(QFont("Arial", 10))

        # Set semi-transparent background color
        self.background_color = QColor(background_color)
        self.background_color.setAlpha(200)  # Make background slightly transparent

        # Calculate expanded dimensions based on content
        self.updateExpandedDimensions()

        # Make items draggable and selectable
        self.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        # Store the current view scale
        self.current_scale = 1.0

        # Threshold for switching between collapsed and expanded view
        self.scale_threshold = 0.5

    def updateExpandedDimensions(self):
        # Create a new document for measurement
        measure_doc = QTextDocument()
        measure_doc.setDefaultFont(self.font())
        measure_doc.setPlainText(self.full_text)

        # Set initial text width for word wrapping
        measure_doc.setTextWidth(self.min_width - self.padding * 2)

        # Get text size with word wrap
        content_size = measure_doc.size()

        # If content height is too large, increase width to reduce height
        max_height = self.min_height * 3  # Allow up to 3 times the minimum height
        if content_size.height() > max_height:
            # Gradually increase width until height is acceptable or max width is reached
            test_width = self.min_width
            max_width = self.min_width * 3  # Allow up to 3 times the minimum width

            while content_size.height() > max_height and test_width < max_width:
                test_width += 50  # Increment width by 50 pixels
                measure_doc.setTextWidth(test_width - self.padding * 2)
                content_size = measure_doc.size()

        # Calculate final dimensions
        self.expanded_width = max(
            self.min_width, content_size.width() + self.padding * 2
        )
        self.expanded_height = max(
            self.min_height, content_size.height() + self.padding * 2
        )

        # Reset to display text
        self.setPlainText(self.display_text)

    def add_connector(self, connector, is_incoming=True):
        if is_incoming:
            self.incoming_connectors.append(connector)
        else:
            self.outgoing_connectors.append(connector)

    def update_connectors(self):
        # Update incoming connectors
        for connector in self.incoming_connectors:
            if isinstance(connector, QGraphicsLineItem):
                start_pos = connector.line().p1()
                end_pos = self.get_connection_point(start_pos)
                connector.setLine(
                    start_pos.x(), start_pos.y(), end_pos.x(), end_pos.y()
                )

        # Update outgoing connectors
        for connector in self.outgoing_connectors:
            if isinstance(connector, QGraphicsLineItem):
                end_pos = connector.line().p2()
                start_pos = self.get_connection_point(end_pos)
                connector.setLine(
                    start_pos.x(), start_pos.y(), end_pos.x(), end_pos.y()
                )

    def paint(self, painter, option, widget):
        # Get the current view scale
        view = self.scene().views()[0]
        self.current_scale = view.transform().m11()

        # Update target progress based on scale
        new_target = (
            0.0
            if (self.current_scale < self.scale_threshold and self.is_detail)
            else 1.0
        )
        if new_target != self.target_progress:
            self.target_progress = new_target
            if not self.animation_timer.isActive():
                self.animation_timer.start()

        # Calculate interpolated dimensions
        current_width = (
            self.collapsed_width
            + (self.expanded_width - self.collapsed_width) * self.animation_progress
        )
        current_height = (
            self.collapsed_height
            + (self.expanded_height - self.collapsed_height) * self.animation_progress
        )

        # Calculate center-aligned rectangle for positioning
        rect = self.boundingRect()
        center = rect.center()
        current_rect = QRectF(
            center.x() - current_width / 2,
            center.y() - current_height / 2,
            current_width,
            current_height,
        )

        # Set up text area with semi-transparent background
        text_rect = current_rect

        # Draw background with rounded corners
        painter.setBrush(QBrush(self.background_color))
        painter.setPen(Qt.PenStyle.NoPen)  # No border
        painter.drawRoundedRect(text_rect, 10, 10)  # 10 pixel corner radius

        # Draw text
        if self.animation_progress < 0.5:
            # Draw collapsed text (filename only)
            font = painter.font()
            font_size = int(8 + 2 * self.animation_progress)
            font.setPointSize(font_size)
            painter.setFont(font)
            painter.setPen(Qt.GlobalColor.black)
            display_text = self.display_text
            if len(display_text) > 15:
                display_text = display_text[:12] + "..."
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, display_text)
        else:
            # Draw expanded text
            self.setPlainText(self.full_text)
            self.setTextWidth(text_rect.width())

            # Calculate vertical position to center the text if it's shorter than the rectangle
            doc_height = self.document().size().height()
            if doc_height < text_rect.height():
                y_offset = (text_rect.height() - doc_height) / 2
            else:
                y_offset = 0

            painter.save()
            painter.translate(text_rect.topLeft() + QPointF(0, y_offset))

            # Create clip path for text with rounded corners
            clip_path = QPainterPath()
            clip_path.addRoundedRect(
                QRectF(0, -y_offset, text_rect.width(), text_rect.height()), 10, 10
            )
            painter.setClipPath(clip_path)

            # Draw the text
            super().paint(painter, option, widget)
            painter.restore()

    def shape(self):
        path = QPainterPath()
        if self.current_scale < self.scale_threshold:
            # Circular shape when zoomed out
            diameter = min(self.expanded_width, self.expanded_height)
            path.addEllipse(-diameter / 2, -diameter / 2, diameter, diameter)
        else:
            # Rectangle shape when zoomed in
            path.addRect(self.boundingRect())
        return path

    def boundingRect(self):
        # Return a fixed-size bounding rect for stable layout
        max_width = max(self.expanded_width, self.collapsed_width)
        max_height = max(self.expanded_height, self.collapsed_height)
        return QRectF(-max_width / 2, -max_height / 2, max_width, max_height)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.setZValue(1)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.setZValue(0)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self.update_connectors()

    def update_animation(self):
        if abs(self.animation_progress - self.target_progress) < 0.01:
            self.animation_progress = self.target_progress
            self.animation_timer.stop()
        else:
            self.animation_progress += (
                self.target_progress - self.animation_progress
            ) * self.animation_speed

        self.update()
        self.update_connectors()

    def get_connection_point(self, target_pos):
        """Get the point on the edge closest to the target position"""
        if self.current_scale < self.scale_threshold and self.is_detail:
            # Use collapsed rectangle connection points
            rect = self.sceneBoundingRect()
            center = rect.center()
            target = target_pos

            # Calculate current interpolated dimensions
            current_width = (
                self.collapsed_width
                + (self.expanded_width - self.collapsed_width) * self.animation_progress
            )
            current_height = (
                self.collapsed_height
                + (self.expanded_height - self.collapsed_height)
                * self.animation_progress
            )

            # Calculate intersection with current rectangle size
            if abs(target.x() - center.x()) > abs(target.y() - center.y()):
                x = (
                    center.x() - current_width / 2
                    if target.x() < center.x()
                    else center.x() + current_width / 2
                )
                y = center.y()
            else:
                x = center.x()
                y = (
                    center.y() - current_height / 2
                    if target.y() < center.y()
                    else center.y() + current_height / 2
                )

            return QPointF(x, y)
        else:
            # Use regular rectangle connection points when expanded
            rect = self.sceneBoundingRect()
            center = rect.center()
            target = target_pos

            # Calculate current interpolated dimensions
            current_width = (
                self.collapsed_width
                + (self.expanded_width - self.collapsed_width) * self.animation_progress
            )
            current_height = (
                self.collapsed_height
                + (self.expanded_height - self.collapsed_height)
                * self.animation_progress
            )

            if target.x() == center.x():
                x = center.x()
                y = (
                    center.y() - current_height / 2
                    if target.y() < center.y()
                    else center.y() + current_height / 2
                )
            else:
                slope = (target.y() - center.y()) / (target.x() - center.x())
                if abs(slope) < current_height / current_width:
                    x = (
                        center.x() - current_width / 2
                        if target.x() < center.x()
                        else center.x() + current_width / 2
                    )
                    y = center.y() + slope * (x - center.x())
                else:
                    y = (
                        center.y() - current_height / 2
                        if target.y() < center.y()
                        else center.y() + current_height / 2
                    )
                    x = center.x() + (y - center.y()) / slope

            return QPointF(x, y)


class ClusterDiagramWidget(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(800, 600)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        # Enable keyboard focus for shortcuts
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.central_topic = "Main Topic"
        self.subtopics = {}
        self.api_responses = {}

        # Increase node dimensions for better text display
        self.central_width = 200
        self.central_height = 120
        self.subtopic_width = 180
        self.subtopic_height = 100
        self.detail_width = 500  # Increased from 160
        self.detail_height = 120  # Increased from 100

        # Adjust distances to accommodate larger nodes and spacing
        self.distance_from_center = 500  # Increased from 400
        self.detail_distance = 300  # Increased from 250

        # Zoom properties
        self.scale_factor = 1.0
        self.min_scale = 0.1
        self.max_scale = 3.0
        self.zoom_factor = 1.15
        self.zoom_threshold = 0.5

        # Selection zoom properties
        self.rubberband_selection = False
        self.selection_start = None
        self.is_selecting = False

        # Animation properties
        self.zoom_animation = QPropertyAnimation(self, b"zoom_scale")
        self.zoom_animation.setDuration(200)  # Animation duration in milliseconds
        self.zoom_animation.setEasingCurve(
            QEasingCurve.Type.OutCubic
        )  # Smooth easing curve
        self.zoom_animation.valueChanged.connect(self._on_zoom_changed)

        self.create_shortcuts()

        self.file_emitter = FileSystemEmitter()
        self.file_emitter.new_data.connect(self.handle_new_data)

        # Show folder selection dialog
        self.select_and_start_monitoring()

    def create_shortcuts(self):
        # Zoom in shortcuts (+ and =)
        zoom_in_plus = QShortcut(Qt.Key.Key_Plus, self)
        zoom_in_plus.activated.connect(self.zoom_in)

        zoom_in_equal = QShortcut(Qt.Key.Key_Equal, self)
        zoom_in_equal.activated.connect(self.zoom_in)

        # Zoom out shortcut (-)
        zoom_out = QShortcut(Qt.Key.Key_Minus, self)
        zoom_out.activated.connect(self.zoom_out)

        # Reset zoom shortcut (0)
        reset_zoom = QShortcut(Qt.Key.Key_0, self)
        reset_zoom.activated.connect(self.reset_zoom)

        # Fit view shortcut (F)
        fit_view = QShortcut(Qt.Key.Key_F, self)
        fit_view.activated.connect(self.auto_fit)

        # Alternative zoom shortcuts with Ctrl
        zoom_in_ctrl = QShortcut(QKeySequence.StandardKey.ZoomIn, self)
        zoom_in_ctrl.activated.connect(self.zoom_in)

        zoom_out_ctrl = QShortcut(QKeySequence.StandardKey.ZoomOut, self)
        zoom_out_ctrl.activated.connect(self.zoom_out)

    @pyqtProperty(float)
    def zoom_scale(self):
        return self.scale_factor

    @zoom_scale.setter
    def zoom_scale(self, value):
        self.scale_factor = value

    def _on_zoom_changed(self, value):
        """Handle zoom animation value changes"""
        self.setTransform(QTransform().scale(value, value))

        # Update all items to start their animations if needed
        for item in self.scene.items():
            if isinstance(item, TextNodeItem):
                item.update()

    def animate_zoom(self, target_scale):
        """Animate zoom to target scale"""
        if self.zoom_animation.state() == QPropertyAnimation.State.Running:
            self.zoom_animation.stop()

        # Clamp target scale
        target_scale = max(self.min_scale, min(self.max_scale, target_scale))

        # Set up animation
        self.zoom_animation.setStartValue(self.scale_factor)
        self.zoom_animation.setEndValue(target_scale)

        # Start animation
        self.zoom_animation.start()

    def zoom_in(self):
        self.scale_factor *= self.zoom_factor
        self.scale_factor = min(self.max_scale, self.scale_factor)
        self.update_zoom()

    def zoom_out(self):
        self.scale_factor /= self.zoom_factor
        self.scale_factor = max(self.min_scale, self.scale_factor)
        self.update_zoom()

    def reset_zoom(self):
        self.scale_factor = 1.0
        self.update_zoom()

    def update_zoom(self):
        # Update transform
        self.setTransform(QTransform().scale(self.scale_factor, self.scale_factor))

        # Update all items to start their animations if needed
        for item in self.scene.items():
            if isinstance(item, TextNodeItem):
                item.update()

    def select_and_start_monitoring(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Directory to Monitor",
            str(Path.home()),
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
        )

        if directory:
            self.file_emitter.start_monitoring(directory)
        else:
            # If no directory selected, close the application
            QApplication.instance().quit()

    def mousePressEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.rubberband_selection = True
            self.selection_start = event.pos()
            self.is_selecting = True
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.rubberband_selection and self.is_selecting:
            self.rubberband_selection = False
            self.is_selecting = False
            selection_rect = self.rubberBandRect()
            if selection_rect and not selection_rect.isEmpty():
                scene_rect = self.mapToScene(selection_rect).boundingRect()
                self.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatio)
                self.scale_factor = self.transform().m11()
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        super().mouseReleaseEvent(event)

    def calculate_optimal_scale(self):
        """Calculate the optimal scale factor to fit all items in view"""
        if not self.scene.items():
            return 1.0

        # Get the scene rect that contains all items
        scene_rect = self.scene.itemsBoundingRect()

        # Calculate the scale factors needed to fit the content
        width_ratio = (self.viewport().width() - 100) / scene_rect.width()
        height_ratio = (self.viewport().height() - 100) / scene_rect.height()

        # Use the smaller ratio to ensure everything fits
        optimal_scale = min(width_ratio, height_ratio)

        # Clamp to our min/max limits
        return max(self.min_scale, min(self.max_scale, optimal_scale))

    def auto_fit(self):
        """Automatically fit all items in view"""
        self.scale_factor = self.calculate_optimal_scale()
        self.setTransform(QTransform().scale(self.scale_factor, self.scale_factor))

        # Center the view
        self.centerOn(self.scene.itemsBoundingRect().center())
        self.update()

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        # Check for Ctrl+F (Cmd+F on macOS)
        if (
            event.key() == Qt.Key.Key_F
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.auto_fit()
        else:
            super().keyPressEvent(event)

    def handle_new_data(self, topic_type, parent, content, api_response, file_content):
        if topic_type == "subtopic":
            if content not in self.subtopics:
                self.subtopics[content] = []
        else:  # detail
            if parent in self.subtopics:
                # Remove the 8-file limit
                self.subtopics[parent].append(content)
                if api_response:
                    self.api_responses[content] = api_response
                if file_content:
                    self.api_responses[content] = f"File contents:\n\n{file_content}"
            elif parent == "Main Topic":
                if "Root Files" not in self.subtopics:
                    self.subtopics["Root Files"] = []
                # Remove the 8-file limit for root files
                self.subtopics["Root Files"].append(content)
                if api_response:
                    self.api_responses[content] = api_response
                if file_content:
                    self.api_responses[content] = f"File contents:\n\n{file_content}"

        # Increase or remove the subtopic limit
        # if len(self.subtopics) > 8:
        #     oldest_topic = list(self.subtopics.keys())[0]
        #     del self.subtopics[oldest_topic]

        self.update_scene()
        QTimer.singleShot(100, self.auto_fit)

    def update_scene(self):
        self.scene.clear()

        # Scene center
        center = QPointF(self.width() / 2, self.height() / 2)

        # Create central node
        central_node = TextNodeItem(
            self.central_topic,
            self.central_width,
            self.central_height,
            QColor(255, 255, 200),
            is_detail=False,
        )
        self.scene.addItem(central_node)

        # Position the node
        central_pos = QPointF(
            center.x() - central_node.boundingRect().width() / 2,
            center.y() - central_node.boundingRect().height() / 2,
        )
        central_node.setPos(central_pos.x(), central_pos.y())

        if self.subtopics:
            num_subtopics = len(self.subtopics)
            angle_step = -360.0 / num_subtopics
            start_angle = 90

            # Draw subtopics and their details
            for i, (subtopic, details) in enumerate(self.subtopics.items()):
                current_angle = (start_angle + i * angle_step) * (np.pi / 180)

                # Calculate subtopic position
                x = center.x() + self.distance_from_center * math.cos(current_angle)
                y = center.y() + self.distance_from_center * math.sin(current_angle)

                # Create subtopic node
                subtopic_node = TextNodeItem(
                    subtopic,
                    self.subtopic_width,
                    self.subtopic_height,
                    QColor(200, 255, 200),
                    is_detail=False,
                )
                self.scene.addItem(subtopic_node)

                # Position the node
                subtopic_pos = QPointF(
                    x - subtopic_node.boundingRect().width() / 2,
                    y - subtopic_node.boundingRect().height() / 2,
                )
                subtopic_node.setPos(subtopic_pos.x(), subtopic_pos.y())

                # Draw line from central node to subtopic
                start_pos = central_node.get_connection_point(
                    subtopic_pos
                    + QPointF(
                        subtopic_node.boundingRect().width() / 2,
                        subtopic_node.boundingRect().height() / 2,
                    )
                )
                end_pos = subtopic_node.get_connection_point(
                    central_pos
                    + QPointF(
                        central_node.boundingRect().width() / 2,
                        central_node.boundingRect().height() / 2,
                    )
                )
                line = self.scene.addLine(
                    start_pos.x(),
                    start_pos.y(),
                    end_pos.x(),
                    end_pos.y(),
                    QPen(Qt.GlobalColor.black, 2),
                )
                line.setZValue(-1)

                # Store the connector
                central_node.add_connector(line, is_incoming=False)
                subtopic_node.add_connector(line, is_incoming=True)

                # Draw detail nodes
                if details:
                    num_details = len(details)
                    detail_angle_span = 120  # Increased from 60 to 120 for more spread
                    detail_angle_step = (
                        -detail_angle_span / max(num_details - 1, 1)
                        if num_details > 1
                        else 0
                    )
                    base_angle = (current_angle * 180 / np.pi) + (detail_angle_span / 2)

                    # Calculate the horizontal spacing between detail nodes
                    horizontal_spacing = (
                        self.detail_width * 1.5
                    )  # Increased from default spacing

                    for j, detail in enumerate(details):
                        detail_angle = (base_angle + j * detail_angle_step) * (
                            np.pi / 180
                        )

                        # Adjust the distance based on the number of details
                        current_detail_distance = self.detail_distance + (
                            j * horizontal_spacing
                        )

                        # Calculate detail position
                        dx = x + current_detail_distance * math.cos(detail_angle)
                        dy = y + current_detail_distance * math.sin(detail_angle)

                        # Create detail text with full API response
                        text = detail
                        if detail in self.api_responses:
                            api_text = str(self.api_responses[detail])
                            text = f"{detail}\n{api_text}"

                        # Create detail node
                        detail_node = TextNodeItem(
                            text,
                            self.detail_width,
                            self.detail_height,
                            QColor(200, 200, 255),
                            is_detail=True,
                        )
                        self.scene.addItem(detail_node)

                        # Position the node
                        detail_pos = QPointF(
                            dx - detail_node.boundingRect().width() / 2,
                            dy - detail_node.boundingRect().height() / 2,
                        )
                        detail_node.setPos(detail_pos.x(), detail_pos.y())

                        # Draw line from subtopic to detail
                        start_pos = subtopic_node.get_connection_point(
                            detail_pos
                            + QPointF(
                                detail_node.boundingRect().width() / 2,
                                detail_node.boundingRect().height() / 2,
                            )
                        )
                        end_pos = detail_node.get_connection_point(
                            subtopic_pos
                            + QPointF(
                                subtopic_node.boundingRect().width() / 2,
                                subtopic_node.boundingRect().height() / 2,
                            )
                        )
                        line = self.scene.addLine(
                            start_pos.x(),
                            start_pos.y(),
                            end_pos.x(),
                            end_pos.y(),
                            QPen(Qt.GlobalColor.black, 1),
                        )
                        line.setZValue(-1)

                        # Store the connector
                        subtopic_node.add_connector(line, is_incoming=False)
                        detail_node.add_connector(line, is_incoming=True)

        # Ensure the scene rect includes all items with some padding
        self.scene.setSceneRect(
            self.scene.itemsBoundingRect().adjusted(-50, -50, 50, 50)
        )
        self.centerOn(center)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CodeConstellation")
        self.setGeometry(100, 100, 1200, 900)

        self.diagram_widget = ClusterDiagramWidget()
        self.setCentralWidget(self.diagram_widget)

        # Create status bar with shortcut information and zoom level
        self.status_bar = self.statusBar()

        # Create permanent widget for zoom level
        self.zoom_label = QLabel()
        self.status_bar.addPermanentWidget(self.zoom_label)

        # Show shortcuts in status bar
        self.status_bar.showMessage(
            "Shortcuts: [+/-] Zoom In/Out | [0] Reset Zoom | "
            "[F] Fit View | [Ctrl++/Ctrl+-] Alternative Zoom"
        )

        # Connect zoom animation value changed to update zoom label
        self.diagram_widget.zoom_animation.valueChanged.connect(self.update_zoom_label)
        self.update_zoom_label(1.0)  # Initial zoom level

    def update_zoom_label(self, scale):
        """Update the zoom level display in the status bar"""
        zoom_percentage = int(scale * 100)
        self.zoom_label.setText(f"Zoom: {zoom_percentage}%")

    def closeEvent(self, event):
        self.diagram_widget.file_emitter.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
