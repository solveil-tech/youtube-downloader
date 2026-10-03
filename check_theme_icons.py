import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QColor
import ytdl

app = QApplication([])
app.setStyle('Fusion')
window = ytdl.YoutubeDownloader()
for dark in (False, True):
    window.dark_mode = dark
    window.apply_style()
    window.deep_menu.show()
    app.processEvents()
    for checked in (False, True):
        box = window.keyword_actions['date']
        box.setChecked(checked)
        pixels = box.grab().toImage()
        colors = {pixels.pixelColor(x, y).name() for x in range(8, 21)
                  for y in range(max(0, (box.height()-13)//2), min(box.height(), (box.height()+13)//2))}
        assert ('#7987ff' if dark else ytdl.ACCENT) in colors if checked else len(colors) > 3
        if checked:
            assert '#ffffff' in colors
    assert not window.deep_btn.icon().isNull()
    window.deep_menu.hide()
print('THEME_ICONS_OK')
# Avoid unrelated Qt worker teardown during this isolated rendering test.
os._exit(0)
