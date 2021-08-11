import cv2
import numpy as np


# TODO: try simplejpeg for faster encoding
def encode_frame_to_bytes(frame):
    ret, buffer = cv2.imencode(".jpg", frame)
    return buffer.tobytes()


def reshape_np_array(buffer, height, width):
    if len(buffer) < height * width * 3:
        return np.empty((height, width, 3), dtype=np.uint8)
    return np.reshape(__make_np_array_from_buffer(buffer), (height, width, 3))


def __make_np_array_from_buffer(buffer):
    return np.frombuffer(buffer, dtype=np.uint8)
