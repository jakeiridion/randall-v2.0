import time
from flask import Flask, render_template, Response
from flask.logging import default_handler
import multiprocessing as mp
from src.server.Webserver.BufferFormatter import encode_frame_to_bytes, reshape_np_array
from src.shared.Logger import create_logger
from src.server.Config import config
import sys
import os
from file_read_backwards import FileReadBackwards


# TODO:add flask logging to filehandler
class Webserver:
    def __init__(self):
        self.__logger = create_logger(__name__, config.DebugMode, "server.log")
        self.__logger.debug("[Server]: Initializing Webserver Class...")
        self.frames = mp.Manager().dict()
        self.resolutions = mp.Manager().dict()
        self.__number_of_columns = config.WebserverTableWidth
        self.__logger.debug("[Server]: Webserver Class Initialized.")

    def run_webserver(self):
        self.__logger.debug("[Server]: starting Webserver...")
        _app = Flask(__name__, template_folder="./templates")

        @_app.route("/video_feed/<string:ip>")
        def _video_feed(ip):
            if ip in self.frames.keys():
                return Response(self._generate_frame(ip), mimetype='multipart/x-mixed-replace; boundary=frame')
            return "NO CAMERA CONNECTED!"

        @_app.route("/log")
        def _log():
            return Response(self._generate_log(), mimetype="text/plain")

        @_app.route("/")
        def _index():
            return render_template("index.html", camera_ips=sorted(list(self.frames.keys())),
                                   noc=self.__number_of_columns,
                                   nor=self.__calculate_row_number(self.__number_of_columns, len(self.frames)))

        # p = mp.Process(target=_app.run, kwargs={"debug": False, "host": "0.0.0.0", "port": 8080})
        # p.start()
        _app.run(host=config.WebserverHost, port=config.WebserverPort, threaded=True)

    def _generate_frame(self, ip):
        height, width = self.resolutions[ip]
        prev_frame = b""
        self.__logger.debug(f"[{ip}]: Webserver started displaying frames...")
        try:
            while ip in self.frames.keys():
                if self.frames[ip] == prev_frame:
                    time.sleep(0.05)
                    continue
                frame = encode_frame_to_bytes(reshape_np_array(self.frames[ip], height, width))
                prev_frame = self.frames[ip]
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        except KeyError:
            self.__logger.exception(f"[{ip}]: Caused KeyError Exception.")
        finally:
            self.__logger.debug(f"[{ip}]: Webserver stopped displaying frames.")

    def _generate_log(self):
        log_path = os.path.join(sys.path[-1], "logs")
        with FileReadBackwards(os.path.join(log_path, "server.log"), encoding="utf-8") as log_file:
            for line in log_file:
                yield (line.strip() + "\n").encode()
                if "STARTING RANDALL-V2.0" in line:
                    break

    def __calculate_row_number(self, columns, cams, x=0):
        if columns >= cams:
            return 1 + x
        result = cams - columns
        return self.__calculate_row_number(columns, result, x + 1)

    def delete_camera(self, ip):
        self.__logger.debug(f"[{ip}]: deleting Camera entries...")
        del self.frames[ip]
        self.__logger.debug(f"[{ip}]: frames entry deleted.")
        del self.resolutions[ip]
        self.__logger.debug(f"[{ip}]: resolutions entry deleted.")
        self.__logger.debug(f"[{ip}]: Camera entries deleted.")

    def delete_all_cameras(self):
        self.__logger.debug("[Server]: deleting all Camera entries...")
        self.frames.clear()
        self.__logger.debug("[Server]: all frames entries deleted.")
        self.resolutions.clear()
        self.__logger.debug("[Server]: all resolutions entries deleted.")
        self.__logger.debug("[Server]: All Camera entries deleted.")
