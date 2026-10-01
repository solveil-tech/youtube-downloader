"""Pixel scrolling, 70% wheel distance and both slider orientations."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtCore import QPoint, QPointF, QSize, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QListWidget, QListWidgetItem, QScrollArea, QWidget
from ytdl import install_smooth_scroll, MinimalVerticalScrollBar

app = QApplication([])
view = QListWidget()
view.resize(400, 250)
for index in range(30):
    item = QListWidgetItem(str(index))
    item.setSizeHint(QSize(150, 100))
    view.addItem(item)
install_smooth_scroll(view)
view.show()
app.processEvents()

def wheel(widget, angle):
    event = QWheelEvent(QPointF(30, 30), QPointF(widget.mapToGlobal(QPoint(30, 30))),
                        QPoint(), angle, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)
    assert event.isAccepted()

bar = view.verticalScrollBar()
expected = round(100 * QApplication.wheelScrollLines() * 0.7)
wheel(view.viewport(), QPoint(0, -120))
assert bar.value() == 0, "Wheel jumped directly to target"
QTest.qWait(60)
assert 0 < bar.value() < expected, "No intermediate smooth position"
wheel(view.viewport(), QPoint(0, -120))
QTest.qWait(240)
assert bar.value() == expected * 2, (bar.value(), expected * 2)
assert isinstance(bar, MinimalVerticalScrollBar) and bar.handle_color.alpha() < 255

area = QScrollArea()
area.resize(300, 200)
host = QWidget()
host.setFixedSize(2000, 1000)
area.setWidget(host)
install_smooth_scroll(area)
area.show()
app.processEvents()
horizontal = area.horizontalScrollBar()
expected_x = round(horizontal.singleStep() * QApplication.wheelScrollLines() * 0.7)
wheel(area.viewport(), QPoint(-120, 0))
QTest.qWait(240)
assert horizontal.value() == expected_x
horizontal.setValue(horizontal.maximum() // 2)
position = horizontal.handle_rect().center().toPoint()
QTest.mousePress(horizontal, Qt.MouseButton.LeftButton, pos=position)
QTest.mouseMove(horizontal, position + QPoint(20, 0))
QTest.mouseRelease(horizontal, Qt.MouseButton.LeftButton, pos=position + QPoint(20, 0))
assert horizontal.value() > horizontal.maximum() // 2, "Horizontal handle cannot be dragged"
bar.set_theme(True)
assert bar.handle_color.alpha() < 255
view.close()
area.close()
print("SCROLL_OK: intermediate pixel motion, 70% distance, repeated wheel accumulation, horizontal drag and translucent handles")
