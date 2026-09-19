import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor


def test_worker_accepts_utf8_paths_under_a_legacy_windows_code_page(video, tmp_path):
    process = subprocess.Popen(
        [sys.executable, "-m", "local_cutout", "--data-dir", str(tmp_path / "data")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )

    def receive():
        for line in process.stdout:
            message = json.loads(line)
            if message.get("id") == "unicode-import":
                return message
        raise AssertionError("Worker exited without a response")

    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            response = executor.submit(receive)
            request = {"v": 1, "id": "unicode-import", "action": "import_video", "params": {"path": str(video)}}
            process.stdin.write((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
            process.stdin.flush()
            message = response.result(timeout=30)
            assert "error" not in message, message
            assert message["result"]["source"] == str(video.resolve())
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stdout.close()
            process.stderr.close()
