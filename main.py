import io
import os

import picamera
import logging
import socketserver
from threading import Condition
from http import server
from sys import platform


def get_root_path():
    if platform == "win32":
        full_path = os.getcwd().split("\\")
        return '\\'.join(full_path[0:full_path.index("FlotomachineCam") + 1])
    else:
        full_path = os.getcwd().split("/")
        return '/'.join(full_path[0:full_path.index("FlotomachineCam") + 1])


def get_page(name: str) -> bytes:
    with open(os.path.join(get_root_path(), name), 'r', encoding='utf-8') as f_temp:  # , 'pages'
        return bytes(f_temp.read().encode('utf-8'))


class StreamingOutput(object):
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def write(self, buf):
        if buf.startswith(b'\xff\xd8'):
            # New frame, copy the existing buffer's content and notify all
            # clients it's available
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)


class StreamingHandler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            content = get_page("index.html")
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/foto.':
            content = get_page("index.html")
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output_stream.condition:
                        output_stream.condition.wait()
                        frame = output_stream.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', str(len(frame)))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                logging.warning('Removed streaming client %s: %s', self.client_address, str(e))
        else:
            self.send_error(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/photo':
            with output_stream.condition:
                output_stream.condition.wait()
                frame = output_stream.frame
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', str(len(frame)))
            self.end_headers()
            self.wfile.write(frame)
        else:
            self.send_error(404)
            self.end_headers()


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


_ADDRESS = ('', 8000)
output_stream = StreamingOutput()


def main():
    print("This path:", get_root_path())
    camera = picamera.PiCamera(resolution='640x480', framerate=24)
    # Uncomment the next line to change your Pi's Camera rotation (in degrees)
    # camera.rotation = 90
    camera.start_recording(output_stream, format='mjpeg')
    try:
        StrServer = StreamingServer(_ADDRESS, StreamingHandler)
        StrServer.serve_forever()
    finally:
        camera.stop_recording()


if __name__ == "__main__":
    main()
