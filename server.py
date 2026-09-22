"""Local server for selecting and downloading English mock exam answers."""
import json
import re
import sys
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Timer
from urllib.parse import parse_qs, quote, urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor"))
from extractor import find_answer_sets  # noqa: E402
from extractor import fetch  # noqa: E402
from pdf_download import find_pdfs  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        request = urlparse(self.path)
        if request.path in ("/", "/index.html"):
            self.send_bytes(200, (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8")
            return
        if request.path not in ("/api/answers", "/api/pdfs", "/api/pdf"):
            self.send_bytes(404, b"Not found", "text/plain; charset=utf-8")
            return
        try:
            query = parse_qs(request.query)
            year = int(query["year"][0])
            month = int(query["month"][0])
            grade = int(query["grade"][0])
            if not (2002 <= year <= date.today().year and 1 <= month <= 12 and 1 <= grade <= 3):
                raise ValueError("학년, 시행 연도 또는 월이 선택 범위를 벗어났습니다.")
            if request.path == "/api/answers":
                result = find_answer_sets(year, month, grade)
            else:
                entries = find_pdfs(year, month, grade)
                if request.path == "/api/pdfs":
                    result = {"results": [{"title": entry["title"], "variant": entry["variant"],
                                           "available": list(entry["files"])} for entry in entries]}
                else:
                    kind = query["kind"][0]
                    variant = query.get("variant", [""])[0]
                    if kind not in ("q", "a") or not re.fullmatch(r"[AB]?", variant):
                        raise ValueError("PDF 종류 또는 유형이 올바르지 않습니다.")
                    matches = [entry for entry in entries if (entry["variant"] or "") == variant]
                    if len(matches) != 1 or kind not in matches[0]["files"]:
                        raise ValueError("선택한 PDF가 EBSi 목록에 없습니다.")
                    body = fetch(matches[0]["files"][kind])
                    if not body.startswith(b"%PDF-"):
                        raise ValueError("EBSi에서 유효한 PDF를 받지 못했습니다.")
                    name = f"고{grade}-[{year}-{month:02d}]" + (f"-{variant}" if variant else "") + ("-A" if kind == "a" else "") + ".pdf"
                    self.send_response(200)
                    self.send_header("Content-Type", "application/pdf")
                    self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(name))
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
            status = 200
        except (KeyError, ValueError) as error:
            result = {"error": str(error) or "선택값을 확인하세요."}
            status = 422
        except Exception:
            result = {"error": "인터넷 자료를 가져오지 못했습니다. 잠시 후 다시 시도하세요."}
            status = 502
        body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self.send_bytes(status, body, "application/json; charset=utf-8")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        print(f"{port}번 포트가 사용 중이어서 다른 포트로 실행합니다.")
    address = f"http://localhost:{server.server_port}"
    print(f"브라우저에서 {address} 을 여세요.")
    Timer(0.5, lambda: webbrowser.open(address)).start()
    server.serve_forever()
