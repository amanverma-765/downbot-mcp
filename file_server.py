import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


def start_file_server(
        file_server_port: int,
        output_dir: str = "files"
):
    class FilesHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=output_dir, **kwargs)

        def send_head(self):
            path = self.translate_path(self.path)
            f = None
            try:
                f = open(path, 'rb')
            except OSError:
                self.send_error(404, "File not found")
                return None

            ctype = self.guess_type(path)
            self.send_response(200)
            self.send_header("Content-Type", ctype)

            # Check if the content is video or audio
            if ctype.startswith("video/") or ctype.startswith("audio/"):
                # Add header to force download
                filename = path.split("/")[-1]
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')

            fs = os.fstat(f.fileno())
            self.send_header("Content-Length", str(fs.st_size))
            self.end_headers()
            return f

    server_address = ("", file_server_port)
    httpd = ThreadingHTTPServer(server_address, FilesHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


