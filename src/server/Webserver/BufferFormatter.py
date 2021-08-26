import numpy as np
import simplejpeg


def encode_frame_to_bytes(frame):
    return simplejpeg.encode_jpeg(frame, colorspace="BGR")


def reshape_np_array(buffer, height, width):
    if len(buffer) < height * width * 3:
        return np.empty((height, width, 3), dtype=np.uint8)
    return np.reshape(__make_np_array_from_buffer(buffer), (height, width, 3))


def __make_np_array_from_buffer(buffer):
    return np.frombuffer(buffer, dtype=np.uint8)
