from src.shared.Logger import create_logger
from Config import config
import multiprocessing as mp
import ctypes
import cv2
from threading import Thread
from datetime import datetime
import time


class Capture:
    def __init__(self, resolution):
        self.logger = create_logger(__name__, config.DebugMode, "client.log")
        self.logger.debug("Initializing Capture Class...")
        self.is_running = mp.Value(ctypes.c_bool, False)
        self.height, self.width = resolution  # frame.shape = (height, width, 3)
        self.fps = self.__get_camera_fps()
        self.__record_timer = mp.Manager().Value(ctypes.c_wchar_p, "00:00:00:00")
        self.__processes_threads = []
        self.logger.debug("Capture Class initialized.")

    def __get_camera_fps(self):
        cap = cv2.VideoCapture(config.CaptureDevice)
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        return fps

    def start(self, pipe_in):
        frame_pipe_out, frame_pipe_in = mp.Pipe(False)
        self.__start_capture_thread(frame_pipe_in)
        self.__start_record_timer_process()
        self.__start_frame_formatting_process(frame_pipe_out, pipe_in)

    def __start_capture_thread(self, pipe_in):
        def loop(log, is_running, capture_device, width, height, pipe):
            log.debug("starting Video Capture...")
            is_running.value = True
            cap = cv2.VideoCapture(capture_device)
            while is_running.value:
                ret, frame = cap.read()
                frame = cv2.flip(frame, 1)
                frame = cv2.resize(frame, (width, height))
                pipe.send(frame)
            cap.release()
            log.debug("Video Capture stopped.")

        t = Thread(target=loop,
                   args=[self.logger, self.is_running, config.CaptureDevice, self.width, self.height, pipe_in],
                   daemon=True)
        t.start()
        self.__processes_threads.append(t)

    def __start_record_timer_process(self):
        def loop(log, is_running, record_timer):
            log.debug("starting record timer.")
            start_time = datetime.now()
            while is_running.value:
                rc = datetime.now() - start_time
                days = rc.days
                hours, rem = divmod(rc.seconds, 3600)
                minutes, seconds = divmod(rem, 60)
                record_timer.value = f"{days:02d}:{hours:02d}:{minutes:02d}:{seconds:02d}"
                if rc == "99:23:59:59":  # max REC timer value
                    break
                time.sleep(1)
            log.debug("stop record timer.")

        p = mp.Process(target=loop, args=(self.logger, self.is_running, self.__record_timer))
        p.start()
        self.__processes_threads.append(p)

    def __start_frame_formatting_process(self, pipe_out, pipe_in):
        def loop(log, is_running, pipe_o, pipe_i, height, width, record_timer):
            log.debug("starting frame formatting.")
            while is_running.value:
                frame = pipe_o.recv()
                # Current day:
                frame = cv2.rectangle(frame, (10, height - 5), (195, height - 25), (0, 0, 0), -1)
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                frame = cv2.putText(frame, now, (10, height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                    (255, 255, 255), 1)

                # Record time:
                frame = cv2.rectangle(frame, ((width - 10) - 95, height - 5),
                                      (width - 10, height - 25), (0, 0, 0), -1)
                frame = cv2.putText(frame, record_timer.value, ((width - 10) - 95, height - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                pipe_i.send_bytes(frame.tobytes())
            log.debug("stop frame formatting.")

        p = mp.Process(
            target=loop,
            args=(self.logger, self.is_running, pipe_out, pipe_in, self.height, self.width, self.__record_timer),
            daemon=True)
        p.start()
        self.__processes_threads.append(p)

    def stop(self):
        self.logger.debug("stopping Video Capture...")
        self.is_running.value = False

    def get_processes_threads(self):
        return self.__processes_threads
