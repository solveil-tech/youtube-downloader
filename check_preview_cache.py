"""Cache retries and same-target worker exclusion without network/media writes."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PyQt6.QtCore import QCoreApplication
from ytdl import PreviewCacheWorker

app = QCoreApplication([])

class Checks(unittest.TestCase):
    def test_target_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preview.mp4"
            first = PreviewCacheWorker("https://youtu.be/AAAAAAAAAAA", "v+a", path)
            second = PreviewCacheWorker(first.url, first.format_id, path)
            self.assertIs(first.target_lock, second.target_lock)
            first.target_lock.acquire()
            try:
                with patch.object(second, "download_cache") as download:
                    second.start()
                    self.assertFalse(second.wait(120))
                    second.request_stop()
                    self.assertTrue(second.wait(1000))
                    download.assert_not_called()
            finally:
                first.target_lock.release()

    def test_transient_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = PreviewCacheWorker("https://youtu.be/AAAAAAAAAAA", "v+a", Path(folder) / "preview.mp4")
            process = Mock(returncode=1)
            process.communicate.return_value = (None, "HTTP Error 403: Forbidden")
            errors = []
            worker.failed.connect(errors.append)
            with patch("ytdl.subprocess.Popen", return_value=process) as spawn:
                worker.run()
            self.assertEqual(spawn.call_count, 3)
            self.assertEqual(len(errors), 1)
            self.assertIn("--ignore-config", spawn.call_args.args[0])
            self.assertEqual(spawn.call_args.kwargs["encoding"], "utf-8")

if __name__ == "__main__":
    unittest.main(verbosity=2)
