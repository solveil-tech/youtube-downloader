import tempfile
import unittest
from pathlib import Path
from media_library import media_record, duplicate_matches, fingerprint, remember_download, read_json


class MediaLibraryTests(unittest.TestCase):
    def test_embedded_source_and_actual_stream(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent / ".checkenv") as directory:
            file = Path(directory) / "renamed.mp4"
            file.touch()
            probe = {"format": {"duration": "14.35", "tags": {"comment": "Video: A title\nVideo URL: https://www.youtube.com/watch?v=AAAAAAAAAAA"}},
                     "streams": [{"codec_type": "video", "width": 1280, "height": 720, "disposition": {"attached_pic": 1}},
                                 {"codec_type": "video", "width": 2160, "height": 3840, "avg_frame_rate": "60/1", "codec_name": "av1"}]}
            record = media_record(file, probe, fingerprint(file))
            self.assertEqual(record["width"], 2160)
            self.assertEqual(record["fps"], 60)
            probe["format"]["tags"]["description"] = "See another video https://youtu.be/BBBBBBBBBBB"
            self.assertEqual(media_record(file, probe, fingerprint(file))["source_ids"], ["AAAAAAAAAAA"])
            match = duplicate_matches([record], {"id": "AAAAAAAAAAA", "title": "Different filename", "duration": 14})
            self.assertTrue(match[0]["confirmed_source"])
            self.assertFalse(match[0]["partial"])
            self.assertEqual(duplicate_matches([record], {"id": "BBBBBBBBBBB", "duration": 14.35}), [])
            record["source_ids"] = []
            self.assertEqual(duplicate_matches([record], {"title": "Other title", "duration": 14.35}), [])
            self.assertFalse(duplicate_matches([record], {"title": "A title", "duration": 14.35})[0]["confirmed_source"])
            file.unlink()
            self.assertEqual(duplicate_matches([record], {"title": "A title", "duration": 14.35}), [])

    def test_provenance(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent / ".checkenv") as directory:
            file, ledger = Path(directory) / "test.webm", Path(directory) / "index.json"
            file.touch()
            remember_download(ledger, file, "https://youtu.be/AAAAAAAAAAA", "Original", [1, 2])
            source = read_json(ledger)[str(file.resolve())]
            probe = {"format": {"duration": "1"}, "streams": [{"codec_type": "video"}]}
            record = media_record(file, probe, fingerprint(file), source)
            self.assertEqual(record["source_ids"], ["AAAAAAAAAAA"])
            self.assertTrue(duplicate_matches([record], {"id": "AAAAAAAAAAA", "duration": 30})[0]["partial"])
            source["signature"] = [100, 100]
            self.assertEqual(media_record(file, probe, fingerprint(file), source)["source_ids"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
