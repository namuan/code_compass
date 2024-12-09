import math
import os
import sys
from pathlib import Path

import mistune
from litellm import completion
from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_lexer_for_filename
from pygments.lexers.special import TextLexer
from pygments.util import ClassNotFound
from PyQt6.QtCore import pyqtProperty
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtCore import QEasingCurve
from PyQt6.QtCore import QPointF
from PyQt6.QtCore import QPropertyAnimation
from PyQt6.QtCore import QRectF
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QThread
from PyQt6.QtGui import QAction
from PyQt6.QtGui import QBrush
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QFont
from PyQt6.QtGui import QIcon
from PyQt6.QtGui import QKeySequence
from PyQt6.QtGui import QPainter
from PyQt6.QtGui import QPen
from PyQt6.QtGui import QShortcut
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtWidgets import QGraphicsObject
from PyQt6.QtWidgets import QGraphicsProxyWidget
from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtWidgets import QGraphicsView
from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QStackedLayout
from PyQt6.QtWidgets import QTextEdit
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QWidget

FONT = QFont("Fantasque Sans Mono", 12)


class ExplanationWorker(QThread):
    chunk_received = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, code):
        super().__init__()
        self.code = code
        self.is_running = True  # Flag to control execution

    def stop(self):
        """Stop the worker"""
        self.is_running = False

    def run(self):
        try:
            messages = [
                {
                    "role": "user",
                    "content": f"Please explain this code and return response in Markdown:\n\n{self.code}",
                }
            ]

            response = completion(
                model="ollama_chat/llama3.1:latest",
                messages=messages,
                api_base="http://localhost:11434",
                stream=True,
            )

            for chunk in response:
                if not self.is_running:
                    break  # Exit if stopped

                if "choices" in chunk and len(chunk["choices"]) > 0:
                    delta = chunk["choices"][0].get("delta", {})
                    if "content" in delta:
                        self.chunk_received.emit(delta["content"])

            self.finished.emit()

        except Exception as e:
            if self.is_running:  # Only emit error if not manually stopped
                error_md = f"**Error:** {str(e)}"
                self.chunk_received.emit(error_md)
            self.finished.emit()


class ScrollableTextWidget(QWidget):
    def __init__(self, filename, text, width, height, parent=None):
        super().__init__(parent)
        self.setMinimumSize(width, height)

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.stack_layout = QStackedLayout()
        self.stack_layout.setContentsMargins(0, 0, 0, 0)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)

        self.second_text_edit = QTextEdit()
        self.second_text_edit.setReadOnly(True)

        try:
            lexer = get_lexer_for_filename(filename) if filename else TextLexer()
        except ClassNotFound:
            lexer = TextLexer()

        formatter = HtmlFormatter(full=False, noclasses=True)

        # Combine filename and text for display
        html_content = highlight(text, lexer, formatter)

        self.text_edit.setHtml(html_content)

        style = f"""
            QTextEdit {{
                border: none;
                font-family: {FONT.family()};
                font-size: {FONT.pointSize()}pt;
            }}
        """
        self.text_edit.setStyleSheet(style)
        self.second_text_edit.setStyleSheet(style)

        # Add text edits to stack layout
        self.stack_layout.addWidget(self.text_edit)
        self.stack_layout.addWidget(self.second_text_edit)

        # Add stack layout to main layout
        layout.addLayout(self.stack_layout)

    def switch_to_second_text_edit(self, content=None):
        """Switch to second text edit and optionally set its content."""
        if content is not None:
            self.second_text_edit.setHtml(content)
        self.stack_layout.setCurrentWidget(self.second_text_edit)

    def switch_to_first_text_edit(self):
        """Switch back to first text edit."""
        self.stack_layout.setCurrentWidget(self.text_edit)


class UIConstants:
    # Circle properties
    CIRCLE_RADIUS = 8
    CIRCLE_PADDING = 0

    # Colors
    EXPANDER_COLOR = QColor(0, 0, 139)
    SYMBOL_COLOR = QColor(200, 200, 200)

    # Animation
    HOVER_SCALE_FACTOR = 1.5
    HOVER_ANIMATION_DURATION = 200  # milliseconds


class ExpanderCircle(QGraphicsObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scale = 1.0

        self.circle_radius = UIConstants.CIRCLE_RADIUS
        self.circle_padding = UIConstants.CIRCLE_PADDING
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.circle_color = UIConstants.EXPANDER_COLOR
        self.is_expanded = False

        # Animation setup
        self.scale_animation = QPropertyAnimation(self, b"scale")
        self.scale_animation.setDuration(UIConstants.HOVER_ANIMATION_DURATION)
        self.setTransformOriginPoint(self.circle_radius, self.circle_radius)

    @pyqtProperty(float)
    def scale(self):
        return self._scale

    @scale.setter
    def scale(self, value):
        self._scale = value
        self.setScale(value)

    def hoverEnterEvent(self, event):
        self.scale_animation.setStartValue(1.0)
        self.scale_animation.setEndValue(UIConstants.HOVER_SCALE_FACTOR)
        self.scale_animation.start()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.scale_animation.setStartValue(UIConstants.HOVER_SCALE_FACTOR)
        self.scale_animation.setEndValue(1.0)
        self.scale_animation.start()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if isinstance(self.parentItem(), TextNodeItem):
                self.toggle_expanded()
                self.parentItem().toggle_expanded()
            event.accept()
        else:
            event.ignore()

    def boundingRect(self):
        return QRectF(
            0,
            0,
            self.circle_radius * 2 + self.circle_padding,
            self.circle_radius * 2 + self.circle_padding,
        )

    def toggle_expanded(self):
        self.is_expanded = not self.is_expanded
        self.update()  # Trigger repaint

    def paint(self, painter, option, widget):
        # Draw the circle
        painter.setBrush(QBrush(self.circle_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            self.circle_padding,
            self.circle_padding,
            self.circle_radius * 2,
            self.circle_radius * 2,
        )

        # Draw the plus/minus symbol
        painter.setPen(QPen(UIConstants.SYMBOL_COLOR, 1.5))

        # Calculate symbol dimensions
        symbol_size = self.circle_radius * 1.2  # Size of the symbol
        center_x = self.circle_padding + self.circle_radius
        center_y = self.circle_padding + self.circle_radius
        offset = symbol_size / 2

        # Draw horizontal line using QPointF
        painter.drawLine(
            QPointF(center_x - offset, center_y), QPointF(center_x + offset, center_y)
        )

        # Draw vertical line (only if expanded)
        if not self.is_expanded:
            painter.drawLine(
                QPointF(center_x, center_y - offset),
                QPointF(center_x, center_y + offset),
            )


class FilenameLabelWidget(QGraphicsObject):
    explanation_worker_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.text = ""
        self.padding = 5
        self.height = 25
        self.font = FONT
        self.text_color = Qt.GlobalColor.black
        self.drag_start_pos = None
        self.is_showing_explanation = False
        self._glow_intensity = 0.0
        self.explanation_worker = None

        # Enable mouse tracking and set cursor
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

        self.explain_button = QPushButton("Explain")
        self.explain_button.setStyleSheet(f"""
            QPushButton {{
                padding: 4px;
                font-family: {FONT.family()};
                font-size: {FONT.pointSize()}pt;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {UIConstants.EXPANDER_COLOR.lighter(150).name()};
                color: white;
                border-radius: 8px;
            }}
            QPushButton:pressed {{
                background-color: {UIConstants.EXPANDER_COLOR.darker(150).name()};
                color: white;
                border-radius: 8px;
            }}
        """)
        self.explain_button.clicked.connect(self.on_explain_clicked)

        # Embed the button into the QGraphicsObject using QGraphicsProxyWidget
        self.proxy_widget = QGraphicsProxyWidget(self)
        self.proxy_widget.setWidget(self.explain_button)
        self.proxy_widget.widget().show()

        # Position the button to the right edge of the label
        self.update_button_position()

        self.explanation_worker = None
        self.explain_button.setEnabled(True)
        self.accumulated_markdown = ""

        # Initialize mark down parser
        self.markdown = mistune.create_markdown(
            plugins=["table", "url", "strikethrough", "footnotes", "task_lists"]
        )
        self.is_worker_running = False
        self.is_currently_explaining = False
        self.glow_color = QColor(255, 140, 0)

        # Animation for the glow effect
        self.glow_animation = QPropertyAnimation(self, b"glow_intensity")
        self.glow_animation.setDuration(1000)  # 1 second
        self.glow_animation.setStartValue(0.0)
        self.glow_animation.setEndValue(1.0)
        self.glow_animation.setLoopCount(-1)  # Infinite loop

    def stop_explanation(self):
        """Stop the current explanation if running"""
        if self.explanation_worker and self.is_worker_running:
            self.explanation_worker.stop()
            self.explanation_worker.wait()  # Wait for the thread to finish
            self.handle_explanation_finished()
            self.accumulated_markdown += "\n\n*Explanation interrupted.*"
            html_content = self.markdown(self.accumulated_markdown)
            self.parentItem().text_widget.second_text_edit.setHtml(html_content)
            self.explain_button.show()

    def set_currently_explaining(self, is_explaining):
        """Set whether this node is currently being explained."""
        self.is_currently_explaining = is_explaining
        self.update()

    @pyqtProperty(float)
    def glow_intensity(self):
        return self._glow_intensity

    @glow_intensity.setter
    def glow_intensity(self, value):
        self._glow_intensity = value
        self.update()

    def boundingRect(self):
        # Define the bounding rectangle for the label widget
        width = self.parentItem().boundingRect().width() - 20
        return QRectF(0 + 10, 0, width, self.height)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.scenePos()
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if self.drag_start_pos is not None:
            new_pos = event.scenePos()
            delta = new_pos - self.drag_start_pos
            self.parentItem().setPos(self.parentItem().pos() + delta)
            self.drag_start_pos = new_pos
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = None
            event.accept()
        else:
            event.ignore()

    def paint(self, painter, option, widget):
        # Save the painter state
        painter.save()

        # Use the same background color and alpha as the parent node
        parent_color = self.parentItem().background_color
        painter.setBrush(QBrush(parent_color))

        if self.is_worker_running:
            # Create glowing border effect
            glow_color = QColor(self.glow_color)
            glow_color.setAlphaF(0.5 * self._glow_intensity)

            # Draw multiple glowing borders with decreasing alpha
            for i in range(3):
                pen = QPen(glow_color, 2 + i * 2)
                painter.setPen(pen)
                painter.drawRoundedRect(
                    self.boundingRect().adjusted(i, i, -i, -i), 5, 5
                )
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(self.boundingRect(), 5, 5)

        # Draw the text
        painter.setPen(QPen(self.text_color))
        painter.setFont(self.font)
        text_rect = self.boundingRect().adjusted(self.padding, 0, -self.padding, 0)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.text,
        )

        # Restore the painter state
        painter.restore()

    def update_button_position(self):
        # Position the button at the right edge of the label
        button_width = self.explain_button.sizeHint().width()
        button_height = self.explain_button.sizeHint().height()
        button_x = self.boundingRect().width() - button_width
        button_y = (self.boundingRect().height() - button_height) / 2

        # Update the button's geometry within the proxy widget
        self.proxy_widget.setPos(button_x, button_y)

    def on_explain_clicked(self):
        parent_node = self.parentItem()
        if parent_node and hasattr(parent_node, "text_widget"):
            # Expand the node if it's not already expanded
            if not parent_node.is_expanded:
                parent_node.toggle_expanded()

            # Ensure node is visible
            if parent_node.scene() and parent_node.scene().views():
                view = parent_node.scene().views()[0]
                view.ensureVisible(parent_node.sceneBoundingRect())

            if not self.is_showing_explanation:
                # If there's a running worker, stop it first
                if self.is_worker_running:
                    self.stop_explanation()
                    return

                parent_node.text_widget.switch_to_second_text_edit("")
                if (
                    self.accumulated_markdown
                    and "Explanation interrupted" not in self.accumulated_markdown
                ):
                    html_content = self.markdown(self.accumulated_markdown)
                    parent_node.text_widget.second_text_edit.setHtml(html_content)
                    self.explain_button.setText("Code")
                    self.explain_button.setEnabled(True)
                    self.is_showing_explanation = True
                else:
                    # Start glow effect
                    self.is_worker_running = True
                    self.glow_animation.start()

                    # Disable button during API call
                    self.explain_button.setEnabled(False)
                    self.explain_button.setText("...")

                    # Clear previous text and switch to second text edit
                    self.accumulated_markdown = ""
                    self.explain_button.hide()

                    # Create and start worker thread
                    self.explanation_worker = ExplanationWorker(parent_node.content)
                    self.explanation_worker.chunk_received.connect(
                        self.handle_chunk_received
                    )
                    self.explanation_worker.finished.connect(
                        self.handle_explanation_finished
                    )
                    self.explanation_worker.start()
            else:
                # Switch back to code view
                parent_node.text_widget.switch_to_first_text_edit()
                self.explain_button.setText("Explain")
                self.is_showing_explanation = False

    def handle_chunk_received(self, chunk):
        parent_node = self.parentItem()
        if parent_node and hasattr(parent_node, "text_widget"):
            # Accumulate text and update display
            self.accumulated_markdown += chunk
            html_content = self.markdown(self.accumulated_markdown)
            parent_node.text_widget.second_text_edit.setHtml(html_content)

            # Scroll to the bottom to show new content
            scrollbar = parent_node.text_widget.second_text_edit.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def set_text(self, text):
        self.text = text
        self.update()

    def handle_explanation_finished(self):
        # Stop glow effect
        self.is_worker_running = False
        self.glow_animation.stop()
        self._glow_intensity = 0.0
        self.update()

        self.explain_button.show()
        self.explain_button.setText("Code")
        self.explain_button.setEnabled(True)
        self.is_showing_explanation = True
        self.explanation_worker_finished.emit()

        # Clean up worker
        if self.explanation_worker:
            self.explanation_worker.deleteLater()
            self.explanation_worker = None

    def set_geometry(self, rect):
        # Update geometry and reposition the button
        super().setGeometry(rect)
        self.update_button_position()


class TextNodeItem(QGraphicsObject):
    def __init__(self, filename, content, width, height, background_color, parent=None):
        super().__init__(parent)

        self.filename = filename
        self.content = content
        self.min_width = width
        self.min_height = height
        self.padding = 10
        self.expanded_width = width
        self.expanded_height = height
        self.collapsed_height = 40
        self.is_expanded = False

        self._current_height = self.collapsed_height

        # Create scrollable text widget
        self.text_widget = ScrollableTextWidget(
            filename=filename,
            text=content,
            width=width - 2 * self.padding,
            height=height - 2 * self.padding,
        )

        # Create proxy widget
        self.proxy = QGraphicsProxyWidget(self)
        self.proxy.setWidget(self.text_widget)
        self.proxy.setPos(self.padding, self.padding)
        self.proxy.setVisible(False)

        self.background_color = QColor(background_color)

        # Create filename label
        self.filename_label = FilenameLabelWidget(self)
        # Initially show the full path
        self.filename_label.set_text(str(Path(filename).absolute()))

        # Rest of the initialization code remains the same
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)

        self.animation = QPropertyAnimation(self, b"currentHeight")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.expander = ExpanderCircle(self)

        self.update_circle_position()

    def get_current_height(self):
        return self._current_height

    def set_current_height(self, height):
        self.prepareGeometryChange()
        self._current_height = height
        self.update_circle_position()
        self.update()

    currentHeight = pyqtProperty(
        float, fget=get_current_height, fset=set_current_height
    )

    def set_expanded(self, expanded):
        if self.is_expanded == expanded:
            return

        self.is_expanded = expanded
        # Update the expander circle's state
        self.expander.is_expanded = expanded
        self.expander.update()  # Force a repaint of the expander

        self.proxy.setVisible(expanded)

        # Update the label text based on state
        self.filename_label.set_text(str(Path(self.filename).absolute()))
        self.filename_label.setPos(0, -self.filename_label.height - 5)

        # Determine target height
        target_height = self.expanded_height if expanded else self.collapsed_height

        # Start animation
        self.animation.stop()
        self.animation.setStartValue(self._current_height)
        self.animation.setEndValue(target_height)
        self.animation.start()

    def toggle_expanded(self):
        self.set_expanded(not self.is_expanded)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Only handle selection, not dragging
            if self.isSelected():
                self.setSelected(False)
            else:
                self.setSelected(True)
            event.accept()
        else:
            super().mousePressEvent(event)

    def update_circle_position(self):
        rect = self.boundingRect()
        # Position the expander circle (top right)
        self.expander.setPos(
            rect.right() - self.expander.circle_radius * 2 + 5,
            rect.top() - 5
            if self.is_expanded
            else (rect.height() - self.expander.circle_radius * 2) / 2,
        )
        # Update filename label position
        if self.is_expanded:
            self.filename_label.setPos(0, -self.filename_label.height - 5)
        else:
            # Center vertically in collapsed state
            self.filename_label.setPos(
                0, (rect.height() - self.filename_label.height) / 2
            )

    def paint(self, painter, option, widget):
        # Draw background
        painter.setBrush(QBrush(self.background_color))

        # Change the pen based on selection state
        if self.isSelected():
            painter.setPen(QPen(Qt.GlobalColor.black, 2))
        else:
            painter.setPen(Qt.PenStyle.NoPen)

        # Draw rounded rectangle
        painter.drawRoundedRect(self.boundingRect(), 10, 10)

    def boundingRect(self):
        return QRectF(0, 0, self.expanded_width, self._current_height)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if self.scene():
                self.scene().update()
        return super().itemChange(change, value)


class ClusterDiagramWidget(QGraphicsView):
    def __init__(self, file_paths, parent=None):
        super().__init__(parent)
        self.file_paths = [Path(path) for path in file_paths]
        self.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Set up the scene
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        # Set up view properties
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Enable rubberband selection
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        # Set viewport update mode
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

        # Set zoom parameters
        self.zoom_factor = 1.15
        self.min_zoom = 0.1
        self.max_zoom = 10.0

        # Variable to track pan mode
        self.panning = False
        self.last_mouse_pos = None

        # Add method to access nodes
        self.current_explanation_index = 0
        self.previous_node = None

        # Create and display the file nodes
        self.nodes = []
        self.display_file_nodes()

        # Auto zoom to fit all nodes
        self.fit_in_view()

        # Initialize scrollbars
        self.adjust_scroll_bars()

        # Set up keyboard shortcuts
        self.setup_shortcuts()

    def setup_shortcuts(self):
        # Reset zoom shortcut
        self.reset_zoom_shortcut = QShortcut(QKeySequence("Ctrl+0"), self)
        self.reset_zoom_shortcut.activated.connect(self.fit_in_view)

    def clear_previous_highlight(self):
        """Clear highlight from the previously explained node."""
        if self.previous_node:
            self.previous_node.filename_label.set_currently_explaining(False)

    def explain_next_node(self):
        """Trigger explanation for the next node that hasn't been explained yet."""
        # Clear previous highlight
        self.clear_previous_highlight()

        if self.current_explanation_index < len(self.nodes):
            node = self.nodes[self.current_explanation_index]

            # Set highlight for current node
            node.filename_label.set_currently_explaining(True)
            self.previous_node = node

            if not node.filename_label.is_showing_explanation:
                # Directly call on_explain_clicked instead of simulating button click
                node.filename_label.on_explain_clicked()

            self.current_explanation_index += 1
            return True
        else:
            # Clear highlight when finished
            self.clear_previous_highlight()
            return False

    def adjust_scroll_bars(self):
        current_scale = self.transform().m11()

        # Adjust scrollbar step sizes based on zoom level
        self.verticalScrollBar().setSingleStep(max(1, int(20 / current_scale)))
        self.horizontalScrollBar().setSingleStep(max(1, int(20 / current_scale)))

        # Update scene rect to ensure proper scrolling
        visible_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        scene_rect = self.scene.itemsBoundingRect()

        # Add some padding around the items
        padding = 100
        scene_rect = scene_rect.adjusted(-padding, -padding, padding, padding)

        # Ensure the scene rect is at least as large as the visible area
        scene_rect = scene_rect.united(visible_rect)
        self.scene.setSceneRect(scene_rect)

    def display_file_nodes(self):
        import math

        center_x = 0
        center_y = 0
        node_width = 600
        radius = self.calculate_radius(
            len(self.file_paths), node_width
        )  # Adjust based on number of nodes
        node_height = 400

        for i, file_path in enumerate(self.file_paths):
            try:
                with open(file_path) as file:
                    content = file.read()
            except Exception as e:
                content = f"Error reading file: {str(e)}"

            # Calculate position on circle
            angle = (2 * math.pi * i) / len(self.file_paths)
            x_position = center_x + radius * math.cos(angle) - node_width / 2
            y_position = center_y + radius * math.sin(angle) - node_height / 2

            node = TextNodeItem(
                filename=str(file_path),
                content=content,
                width=node_width,
                height=node_height,
                background_color="#E8E8E8",
            )

            self.scene.addItem(node)
            node.setPos(x_position, y_position)
            self.nodes.append(node)

    def fit_in_view(self):
        # Add padding around the items
        padding = 50
        scene_rect = self.scene.itemsBoundingRect()
        scene_rect.adjust(-padding, -padding, padding, padding)

        # Fit the scene in the viewport
        self.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatio)

        # Ensure we don't zoom in too much for small scenes
        view_rect = self.viewport().rect()
        scale_factor = min(
            view_rect.width() / scene_rect.width(),
            view_rect.height() / scene_rect.height(),
        )

        # Limit the maximum zoom level
        if scale_factor > 1.0:
            scale_factor = 1.0

        # Apply the transformation
        self.resetTransform()
        self.scale(scale_factor, scale_factor)

        # Center the scene
        self.centerOn(scene_rect.center())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-fit the view when the window is resized
        self.fit_in_view()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Plus or event.key() == Qt.Key.Key_Equal:
            self.zoom_in()
        elif event.key() == Qt.Key.Key_Minus:
            self.zoom_out()
        elif event.key() == Qt.Key.Key_Space:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.panning = True
            self.last_mouse_pos = event.pos()
            event.accept()
        else:
            # Store the start position for rubber band selection
            self.rubber_band_start = event.pos()
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.panning = False
        elif (
            event.button() == Qt.MouseButton.LeftButton
            and self.dragMode() == QGraphicsView.DragMode.RubberBandDrag
        ):
            # Get the rubber band selection rectangle
            rubber_band_rect = self.rubberBandRect()
            if rubber_band_rect and not rubber_band_rect.isEmpty():
                # Convert viewport coordinates to scene coordinates
                scene_rect = self.mapToScene(rubber_band_rect).boundingRect()
                # Add some padding around the selection
                padding = 20
                scene_rect.adjust(-padding, -padding, padding, padding)
                # Zoom to the selected area
                self.zoom_to_rect(scene_rect)

        super().mouseReleaseEvent(event)

    def zoom_to_rect(self, rect):
        # Store the current centerpoint
        self.mapToScene(self.viewport().rect().center())

        # Fit the rect in the viewport
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

        # Get the new scale factor
        new_scale = self.transform().m11()

        # Check if we exceed zoom limits
        if new_scale > self.max_zoom:
            self.resetTransform()
            self.scale(self.max_zoom, self.max_zoom)
        elif new_scale < self.min_zoom:
            self.resetTransform()
            self.scale(self.min_zoom, self.min_zoom)

        # Center on the selection
        self.centerOn(rect.center())

        # Update scrollbars
        self.adjust_scroll_bars()

    def mouseMoveEvent(self, event):
        if self.panning and self.last_mouse_pos is not None:
            delta = event.pos() - self.last_mouse_pos
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            self.last_mouse_pos = event.pos()
        super().mouseMoveEvent(event)
        self.viewport().update()

    def zoom_in(self):
        self.scale_view(self.zoom_factor)

    def zoom_out(self):
        self.scale_view(1 / self.zoom_factor)

    def scale_view(self, factor):
        current_scale = self.transform().m11()
        new_scale = current_scale * factor

        if new_scale > self.max_zoom:
            factor = self.max_zoom / current_scale
        elif new_scale < self.min_zoom:
            factor = self.min_zoom / current_scale

        self.scale(factor, factor)

    def calculate_radius(self, num_files, node_width):
        desired_horizontal_spacing = 100  # Desired space between nodes
        minimum_radius = 200  # Ensure the radius doesn't get too small

        # Calculate the circumference needed to accommodate all nodes with spacing
        required_circumference = num_files * (node_width + desired_horizontal_spacing)

        # Calculate the radius based on the required circumference
        return max(minimum_radius, required_circumference / (2 * math.pi))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Code Compass")
        self.create_menus()
        file_paths = self.get_file_paths()
        self.diagram = ClusterDiagramWidget(file_paths)
        self.setCentralWidget(self.diagram)
        self.showMaximized()

        self.statusBar().showMessage("Ready")

    def update_status(self):
        """Update status bar with current progress."""
        total = len(self.diagram.nodes)
        current = self.diagram.current_explanation_index
        self.statusBar().showMessage(f"Explaining file {current}/{total}")

    def get_file_paths(self):
        # Open folder selection dialog
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Folder to View Files",
            str(Path.home()),  # Start in home directory
            QFileDialog.Option.ShowDirsOnly,
        )

        if folder_path:
            # Convert to Path object
            folder_path = Path(folder_path)
            return [str(f) for f in folder_path.iterdir() if f.is_file()]
        else:
            return []

    def create_menus(self):
        # Create menubar
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("&File")

        open_folder_action = QAction("&Open Folder...", self)
        open_folder_action.setShortcut("Ctrl+O")
        open_folder_action.setStatusTip("Open a folder to view files")
        open_folder_action.triggered.connect(self.open_new_folder)

        exit_action = QAction("&Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setStatusTip("Exit application")
        exit_action.triggered.connect(self.close)

        file_menu.addAction(open_folder_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        # View Menu
        view_menu = menubar.addMenu("&View")

        zoom_in_action = QAction("Zoom &In", self)
        zoom_in_action.setShortcut("Ctrl++")
        zoom_in_action.setStatusTip("Zoom in")
        zoom_in_action.triggered.connect(lambda: self.diagram.zoom_in())

        zoom_out_action = QAction("Zoom &Out", self)
        zoom_out_action.setShortcut("Ctrl+-")
        zoom_out_action.setStatusTip("Zoom out")
        zoom_out_action.triggered.connect(lambda: self.diagram.zoom_out())

        reset_zoom_action = QAction("&Reset Zoom", self)
        reset_zoom_action.setShortcut("Ctrl+0")
        reset_zoom_action.setStatusTip("Reset zoom level")
        reset_zoom_action.triggered.connect(lambda: self.diagram.fit_in_view())

        view_menu.addAction(zoom_in_action)
        view_menu.addAction(zoom_out_action)
        view_menu.addAction(reset_zoom_action)

        # Add Tools menu
        tools_menu = self.menuBar().addMenu("&Tools")

        explain_next_action = QAction("Explain Next File", self)
        explain_next_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
        explain_next_action.setStatusTip("Explain next file")
        explain_next_action.triggered.connect(self.explain_next)

        tools_menu.addAction(explain_next_action)

        # Add stop explanation action
        stop_explanation_action = QAction("&Stop Explanation", self)
        stop_explanation_action.setShortcut("Esc")
        stop_explanation_action.setStatusTip("Stop current explanation")
        stop_explanation_action.triggered.connect(self.stop_current_explanation)
        tools_menu.addAction(stop_explanation_action)

        # Create status bar
        self.statusBar()

    def explain_next(self):
        """Explain the next file."""
        if not self.diagram.explain_next_node():
            self.statusBar().showMessage("All files explained")
            return False
        else:
            self.update_status()
            return True

    def stop_current_explanation(self):
        """Stop the currently running explanation if any"""
        for node in self.diagram.nodes:
            if node.filename_label.is_worker_running:
                node.filename_label.stop_explanation()
                self.statusBar().showMessage("Explanation stopped")
                break

    def open_new_folder(self):
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Folder to View Files",
            str(Path.home()),
            QFileDialog.Option.ShowDirsOnly,
        )

        if folder_path:
            # Create new diagram with selected folder
            file_paths = [str(f) for f in Path(folder_path).iterdir() if f.is_file()]
            self.diagram = ClusterDiagramWidget(file_paths)
            self.setCentralWidget(self.diagram)


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path("assets/icon.png")))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
