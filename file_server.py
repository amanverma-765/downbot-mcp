import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler


def start_file_server(
        file_server_port: int,
        output_dir: str = "files"
):
    class FilesHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=output_dir, **kwargs)

    server_address = ("", file_server_port)
    httpd = ThreadingHTTPServer(server_address, FilesHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd

