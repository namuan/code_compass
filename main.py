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
from PyQt6.QtGui import QBrush
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QFont
from PyQt6.QtGui import QPainter
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtWidgets import QGraphicsObject
from PyQt6.QtWidgets import QGraphicsProxyWidget
from PyQt6.QtWidgets import QGraphicsScene
from PyQt6.QtWidgets import QGraphicsView
from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QWidget

FONT = QFont("Fantasque Sans Mono", 12)


class ExplanationWorker(QThread):
    chunk_received = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, code):
        super().__init__()
        self.code = code

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
                if "choices" in chunk and len(chunk["choices"]) > 0:
                    delta = chunk["choices"][0].get("delta", {})
                    if "content" in delta:
                        self.chunk_received.emit(delta["content"])

            self.finished.emit()

        except Exception as e:
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

        # Create stack layout for text edits
        from PyQt6.QtWidgets import QStackedLayout

        self.stack_layout = QStackedLayout()
        self.stack_layout.setContentsMargins(0, 0, 0, 0)

        # Create text edits
        from PyQt6.QtWidgets import QTextEdit

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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = ""
        self.padding = 5
        self.height = 25
        self.font = FONT
        self.text_color = Qt.GlobalColor.black
        self.drag_start_pos = None
        self.is_showing_explanation = False

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
        self.proxy_widget.widget().hide()

        # Position the button to the right edge of the label
        self.update_button_position()

        self.explanation_worker = None
        self.explain_button.setEnabled(True)
        self.accumulated_markdown = ""

        # Initialize mark down parser
        self.markdown = mistune.create_markdown(
            plugins=["table", "url", "strikethrough", "footnotes", "task_lists"]
        )

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
        # Use the same background color and alpha as the parent node
        parent_color = self.parentItem().background_color
        painter.setBrush(QBrush(parent_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.boundingRect(), 5, 5)

        painter.setPen(QPen(self.text_color))
        painter.setFont(self.font)
        text_rect = self.boundingRect().adjusted(self.padding, 0, -self.padding, 0)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.text,
        )

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
            if not self.is_showing_explanation:
                parent_node.text_widget.switch_to_second_text_edit("")
                if self.accumulated_markdown:
                    html_content = self.markdown(self.accumulated_markdown)
                    parent_node.text_widget.second_text_edit.setHtml(html_content)
                    self.explain_button.setText("Code")
                    self.explain_button.setEnabled(True)
                    self.is_showing_explanation = True
                else:
                    # Disable button during API call
                    self.explain_button.setEnabled(False)
                    self.explain_button.setText("...")

                    # Clear previous text and switch to second text edit
                    self.accumulated_markdown = ""

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
        self.explain_button.setText("Code")
        self.explain_button.setEnabled(True)
        self.is_showing_explanation = True

        # Clean up worker
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

        # Create filename label
        self.filename_label = FilenameLabelWidget(self)
        # Initially show the full path
        self.filename_label.set_text(str(Path(filename).absolute()))

        # Rest of the initialization code remains the same
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)

        self.background_color = QColor(background_color)

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
        self.proxy.setVisible(expanded)

        # Update the label text based on state
        self.filename_label.set_text(str(Path(self.filename).absolute()))
        self.filename_label.setPos(0, -self.filename_label.height - 5)
        if expanded:
            self.filename_label.proxy_widget.widget().show()
        else:
            self.filename_label.proxy_widget.widget().hide()

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
            rect.right() - self.expander.circle_radius * 2 + 5, rect.top() - 5
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
        self.setMinimumSize(800, 600)
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
        from PyQt6.QtGui import QShortcut, QKeySequence

        # Reset zoom shortcut
        self.reset_zoom_shortcut = QShortcut(QKeySequence("Ctrl+0"), self)
        self.reset_zoom_shortcut.activated.connect(self.fit_in_view)

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
        x_position = 0
        spacing = 20  # Space between nodes

        for file_path in self.file_paths:
            try:
                with open(file_path) as file:
                    content = file.read()
            except Exception as e:
                content = f"Error reading file: {str(e)}"

            # Create the node
            node = TextNodeItem(
                filename=str(file_path),
                content=content,
                width=600,
                height=400,
                background_color="#E8E8E8",
            )

            # Add to scene
            self.scene.addItem(node)
            node.setPos(x_position, 0)
            self.nodes.append(node)

            # Update x_position for next node
            x_position += node.expanded_width + spacing

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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Viewer")

        file_paths = self.get_file_paths()
        self.diagram = ClusterDiagramWidget(file_paths)
        self.setCentralWidget(self.diagram)
        self.showMaximized()

    def get_file_paths(self):
        from PyQt6.QtWidgets import QFileDialog

        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Files to View",
            str(Path.home()),  # Start in home directory
            "All Files (*.*)",
        )

        if file_paths:
            return file_paths
        else:
            # Default path if user cancels
            return [
                "/Users/nnn/workspace/scramble/background.js",
                # "/Users/nnn/workspace/scramble/content.js",
                # "/Users/nnn/workspace/scramble/manifest.json",
                # "/Users/nnn/workspace/scramble/options.html",
                "/Users/nnn/workspace/scramble/options.js",
                # "/Users/nnn/workspace/scramble/popup.html",
                # "/Users/nnn/workspace/scramble/popup.js",
            ]


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
