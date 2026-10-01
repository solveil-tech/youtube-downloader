"""Headless source UI checks; isolate settings and avoid actual network requests."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import tempfile
from pathlib import Path
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
import ytdl
from media_library import media_record, fingerprint
from idol_search import make_search_plan, rank_results

app = QApplication([])
app.setStyle("Fusion")
with tempfile.TemporaryDirectory(dir=Path(__file__).parent / ".checkenv") as temporary:
    isolated = QSettings(str(Path(temporary) / "settings.ini"), QSettings.Format.IniFormat)
    ytdl.QSettings = lambda *args: isolated
    window = ytdl.YoutubeDownloader()
    window.start_library_scan = lambda *args, **kwargs: None
    window.request_search_thumbnail = lambda entry: None
    window.show()
    app.processEvents()
    duplicate_file = Path(temporary) / "renamed.mp4"
    duplicate_file.touch()
    window.library_records = [media_record(duplicate_file,
        {"format": {"duration": "10", "tags": {"comment": "https://youtu.be/AAAAAAAAAAA"}},
         "streams": [{"codec_type": "video", "width": 3840, "height": 2160, "avg_frame_rate": "60/1", "codec_name": "vp9"}]}, fingerprint(duplicate_file))]
    window.info = {"id": "AAAAAAAAAAA", "duration": 10}
    window.refresh_duplicate_indicator()
    assert not window.duplicate_indicator.isHidden(), "Same-source advisory not shown"
    assert "3840×2160" in window.duplicate_indicator.toolTip()
    assert "vp9" in window.duplicate_indicator.toolTip()
    window.info = None
    window.library_records = []
    window.refresh_duplicate_indicator()
    assert window.duplicate_indicator.isHidden(), "Stale advisory remains visible"
    window.group_edit.clear()
    window.idol_edit.setFocus()
    QTest.keyClicks(window.idol_edit, "kyujin")
    window.update_member_candidates(show=True)
    app.processEvents()
    completion = window.member_completer.popup()
    model = completion.model()
    index = next(model.index(row, 0) for row in range(model.rowCount())
                 if model.index(row, 0).data() == "Jang Kyujin · NMIXX")
    completion.scrollTo(index)
    QTest.mouseClick(completion.viewport(), Qt.MouseButton.LeftButton,
                     pos=completion.visualRect(index).center())
    app.processEvents()
    print("REAL_COMPLETION", window.idol_edit.text(), window.group_edit.text(), window.selected_idol_id)
    assert window.selected_idol_id == "nmixx:kyujin", "Actual dropdown selection lost identity"
    heights = [completion.sizeHintForRow(row) for row in range(model.rowCount())]
    assert len(set(heights)) == 1, "Completion row heights differ"
    assert completion.width() == window.idol_edit.width(), "Completion width does not match input"
    window.member_model.setStringList(["Jang Kyujin · NMIXX", "Another much longer candidate · Group"])
    window.member_completer.complete()
    app.processEvents()
    model = completion.model()
    hover_index = model.index(1, 0)
    completion.scrollTo(hover_index)
    QTest.mouseMove(completion.viewport(), completion.rect().bottomRight())
    app.processEvents()
    hover_rect = completion.visualRect(hover_index)
    color_point = hover_rect.topLeft()
    color_point.setX(hover_rect.right() - 12)
    color_point.setY(hover_rect.center().y())
    before_hover = completion.viewport().grab().toImage().pixelColor(color_point)
    before_text = window.idol_edit.text()
    QTest.mouseMove(completion.viewport(), completion.visualRect(hover_index).center())
    app.processEvents()
    after_hover = completion.viewport().grab().toImage().pixelColor(color_point)
    assert after_hover != before_hover, "Mouse hover did not change candidate background"
    assert window.idol_edit.text() == before_text, "Hover changed selected identity"
    completion.hide()
    window.update_member_candidates()
    assert window.search_card.layout().indexOf(window.search_results_arrow) + 1 == window.search_card.layout().indexOf(window.search_clear_btn)
    assert window.search_card.layout().indexOf(window.search_clear_btn) + 1 == window.search_card.layout().indexOf(window.search_btn)
    assert window.group_edit.text() == "NMIXX", "Actual dropdown selection did not fill group"
    assert window.idol_edit.text() == "Jang Kyujin", "Completion label leaked into input"

    def replace_input(edit, text):
        QTest.mouseClick(edit, Qt.MouseButton.LeftButton)
        QTest.keyClick(edit, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(edit, Qt.Key.Key_Backspace)
        QTest.keyClicks(edit, text)
        app.processEvents()

    window.member_completer.popup().hide()
    window.group_completer.popup().hide()
    window.group_user_selected = False
    window.group_edit.clear()
    replace_input(window.idol_edit, "kyujin")
    QTest.qWait(300)
    assert window.group_edit.text() == "NMIXX", "Typing an exact member did not auto-fill group"
    assert window.selected_idol_id == "nmixx:kyujin"
    window.member_completer.popup().hide()
    replace_input(window.group_edit, "nmixx")
    replace_input(window.idol_edit, "kyu")
    window.update_member_candidates(show=True)
    app.processEvents()
    model = completion.model()
    index = next(model.index(row, 0) for row in range(model.rowCount())
                 if model.index(row, 0).data() == "Jang Kyujin · NMIXX")
    QTest.mouseClick(completion.viewport(), Qt.MouseButton.LeftButton,
                     pos=completion.visualRect(index).center())
    app.processEvents()
    assert window.selected_idol_id == "nmixx:kyujin", "Group-first dropdown selection lost identity"
    plans, warnings = [], []
    original_worker = ytdl.IdolSearchWorker
    original_warning = ytdl.QMessageBox.warning

    class OfflineSearchWorker(original_worker):
        def run(self):
            plans.append(self.plan)
            self.results.emit([])

    ytdl.IdolSearchWorker = OfflineSearchWorker
    ytdl.QMessageBox.warning = lambda *args: warnings.append(args[2])
    window.search_date_edit.setText("260919")
    QTest.mouseClick(window.search_btn, Qt.MouseButton.LeftButton)
    QTest.qWait(100)
    assert not warnings, warnings
    assert plans and plans[-1]["member_id"] == "nmixx:kyujin", "Search rejected chosen identity"
    assert window.search_worker is None
    window.results_popup.hide()
    ytdl.IdolSearchWorker = original_worker
    ytdl.QMessageBox.warning = original_warning
    print("NAME_FIRST_AND_GROUP_FIRST_SEARCH_OK")
    window.group_edit.setText("fro")
    window.resolve_search_group()
    assert window.group_edit.text() == "fromis_9"
    window.idol_edit.setText("nakyung")
    window.idol_input_alias = "nakyung"
    window.choose_search_member("fromis9:nagyung")
    assert not hasattr(window, "chinese_name_label")
    assert window.search_btn.parentWidget() is window.search_card
    window.selected_idol_id = None
    window.group_edit.clear()
    window.idol_edit.setText("nakyung")
    window.resolve_remembered_member()
    assert window.selected_idol_id == "fromis9:nagyung"
    assert window.idol_edit.text() == "Lee Nagyung"
    window.update_member_candidates(show=True)
    app.processEvents()
    popup = window.member_completer.popup()
    assert popup.parentWidget() is window
    assert not popup.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert popup.width() <= window.idol_edit.width()
    window.completion_application_state(Qt.ApplicationState.ApplicationInactive)
    assert not popup.isVisible()
    window.update_member_candidates(show=True)
    QTest.mouseClick(window.search_date_edit, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert not popup.isVisible(), "Completion remains over other controls"
    window.set_language("en")
    assert window.search_btn.text() == "Search"
    window.set_language("zh")
    assert window.search_btn.text() == "搜索"
    member = window.idol_catalogue.by_id["fromis9:nagyung"]
    plan = make_search_plan(member, window.idol_catalogue.resolve_group("fro"), "nagyung", "260919")
    window.search_entries = rank_results([{"id": "U3BDivTAlpo", "title": "nagyung 260919", "duration": 180, "channel": "Test"}], plan)
    window.search_results_arrow.show()
    window.render_search_results()
    assert window.results_list.count() == 1
    window.toggle_search_results()
    assert window.results_popup.isVisible()
    window.toggle_search_results()
    assert not window.results_popup.isVisible()
    window._suppress_results_reopen = False
    QTest.mouseClick(window.search_results_arrow, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert window.results_popup.isVisible()
    QTest.mouseClick(window.search_results_arrow, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert not window.results_popup.isVisible(), "Arrow reopened on release"
    parsed = []
    window.parse_current_url = lambda: parsed.append(window.url_edit.text())
    window.parse_search_result("https://www.youtube.com/watch?v=U3BDivTAlpo")
    assert window.url_edit.text().endswith("U3BDivTAlpo")
    assert parsed == ["https://www.youtube.com/watch?v=U3BDivTAlpo"]
    for width, height in ((860, 700), (1020, 830)):
        window.resize(width, height)
        app.processEvents()
        QTest.qWait(50)
        print("LAYOUT", width, height, "actual", window.width(), window.height(), "minimum", window.centralWidget().minimumSizeHint().height(), "bottom", window.page_layout.itemAt(window.page_layout.count()-1).geometry().bottom())
        assert window.search_card.geometry().bottom() < window.cover_frame.mapTo(window.centralWidget(), window.cover_frame.rect().topLeft()).y()
        assert window.search_btn.geometry().right() < window.search_card.width()
        assert window.search_btn.geometry().left() > window.search_date_edit.geometry().right()
        last = window.page_layout.itemAt(window.page_layout.count()-1).geometry()
        assert last.bottom() < window.centralWidget().height()
        window.clip_panel.show()
        app.processEvents()
        assert window.search_card.geometry().bottom() < window.cover_frame.mapTo(window.centralWidget(), window.cover_frame.rect().topLeft()).y()
        window.clip_panel.hide()
    output = Path(__file__).parent / ".checkenv" / "search-ui-check.png"
    window.grab().save(str(output))
    print("UI_OK", window.size().width(), window.size().height(), "central_minimum", window.centralWidget().minimumSizeHint().width(), window.centralWidget().minimumSizeHint().height())
    window.close()
    app.processEvents()
    isolated.sync()
    reopened = ytdl.YoutubeDownloader()
    reopened.idol_edit.setText("nakyung")
    reopened.resolve_remembered_member()
    assert reopened.selected_idol_id == "fromis9:nagyung", "Identity preference did not survive reopening"
    reopened.search_date_edit.setText("261001")
    reopened.member_resolve_timer.start()
    reopened.search_clear_btn.click()
    QTest.qWait(300)
    assert all(not edit.text() for edit in (reopened.group_edit, reopened.idol_edit, reopened.search_date_edit))
    assert reopened.selected_idol_id is None and not reopened.idol_input_alias and not reopened.group_user_selected
    assert not reopened.member_resolve_timer.isActive()
    reopened.close()
    app.processEvents()
