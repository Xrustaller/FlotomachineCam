import json
import os
from sys import platform

import io
import logging
import socketserver
from http import server
from threading import Condition

from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
import cgi

settings_file_name = "settings.json"

default_settings = {
    # "restart": False,
    "port": 8000,
    "camera": {
        "rotation": 90,
        "resolution": "640x480",
        "framerate": 24
    }

}


def load_settings() -> dict:
    f_temp = open(settings_file_name, 'r', encoding='utf-8')
    result = json.loads(f_temp.read())
    f_temp.close()
    return result


def save_settings(input_json: dict) -> None:
    f_res = open(settings_file_name, 'w', encoding='utf-8')
    f_res.write(json.dumps(input_json))
    f_res.close()


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


class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


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
        elif self.path == '/photo':
            with output_stream.condition:
                output_stream.condition.wait()
                frame = output_stream.frame
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', str(len(frame)))
            self.end_headers()
            self.wfile.write(frame)
        elif self.path == "/get_info":
            content = {"sensor_resolution": picam2.sensor_resolution}
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/settings':
            if self.headers.get_content_type() != 'application/json':
                self.send_error(400)
                self.end_headers()
                return

            # read the message and convert it into a python dictionary
            cl_val, cl_key = self.headers.get_params(header='content-length')[0]
            length = int(cl_val)
            message = json.loads(self.rfile.read(length))
            need_save = False
            # print("POST Settings", message)
            if "port" in message.keys() and message["port"]:
                settings["port"] = message["port"]
                need_save = True
            if "camera" in message.keys() and message["camera"]:
                if "rotation" in message.keys() and message["rotation"]:
                    settings["camera"]["rotation"] = message["camera"]["rotation"]
                    need_save = True
                if "resolution" in message.keys() and message["resolution"] and \
                        "x" in message["resolution"].keys() and "y" in message["resolution"].keys() and \
                        isinstance(message["resolution"]["x"], int) and isinstance(message["resolution"]["y"], int):
                    settings["camera"]["resolution"]["x"] = message["camera"]["resolution"]["x"]
                    settings["camera"]["resolution"]["y"] = message["camera"]["resolution"]["y"]
                    need_save = True
                if "framerate" in message.keys() and message["framerate"]:
                    settings["camera"]["framerate"] = message["camera"]["framerate"]
                    need_save = True

            if need_save:
                save_settings(settings)
                print("Settings saved", settings)
            response = {"CODE": "OK", "DATA": load_settings()}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode(encoding='utf_8'))
            if "restart" in message.keys() and message["restart"]:
                stream_server.shutdown()
        else:
            self.send_error(404)
            self.end_headers()


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


settings = load_settings()
stream_server = StreamingServer(("", settings["port"]), StreamingHandler)

output_stream = StreamingOutput()

camera2 = Picamera2()  # resolution=settings["camera"]["resolution"], framerate=settings["camera"]["framerate"]
# Uncomment the next line to change your Pi's Camera rotation (in degrees)
camera2.configure(camera2.create_video_configuration(main={"size": (settings["camera"]["resolution"]["x"], settings["camera"]["resolution"]["y"])}))
camera2.rotation = settings["camera"]["rotation"]
camera2.start_recording(JpegEncoder(), FileOutput(output_stream))


def main():
    print("Server start\nThis path:", get_root_path())
    while True:
        try:
            stream_server.serve_forever()
        finally:
            camera2.stop_recording()
            pass
        print("Server restart")


if __name__ == "__main__":
    main()
