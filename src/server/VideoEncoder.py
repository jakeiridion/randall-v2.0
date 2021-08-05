import os
import struct
from FolderStructure import FolderStructure
from Config import config


class VideoEncoder:
    @staticmethod
    def get_ffmpeg_command(input_path, width, height, fps):
        final_output_path = input_path.rstrip(".raw") + ".mp4"
        ffmpeg_command = f"ffmpeg " \
                         f"-y " \
                         f"-f rawvideo " \
                         f"-vcodec rawvideo " \
                         f"-video_size {width}x{height} " \
                         f"-pixel_format bgr24 " \
                         f"-framerate {str(fps)} " \
                         f"-i {input_path} " \
                         f"{config.FFMPEGOutputFileOptions} " \
                         f"{final_output_path} " \
                         f"&& rm {input_path}"
        return ffmpeg_command

    @staticmethod
    def encode_rename_and_delete_all_unfinished_raw_files(to_be_encoded_pipe_in, log):
        raw_files = []
        to_be_renamed = []
        log.debug("[Server]: looking for leftover unfinished or unencoded files...")
        for root, dirs, files in os.walk(os.path.join(os.path.dirname(os.path.dirname(os.getcwd())), "cams")):
            for name in files:
                path = os.path.join(root, name)
                if path.endswith(".raw"):
                    log.debug(f"[Server]: leftover raw file found: {path}")
                    raw_files.append(path)
                elif FolderStructure.was_renamed(path):
                    log.debug(f"[Server]: not renamed video file found: {path}")
                    to_be_renamed.append(path)

        for raw_file in raw_files:
            log.debug(f"[Server]: unpacking metadata from {raw_file}")
            width, height, fps = tuple(struct.unpack(">H", os.getxattr(raw_file, attr))[0]
                                       for attr in os.listxattr(raw_file))
            log.debug(f"[Server]: sending {raw_file} to be encoded.")
            to_be_encoded_pipe_in.send(VideoEncoder.get_ffmpeg_command(raw_file, width, height, fps))

        for unnamed_file_path in to_be_renamed:
            if unnamed_file_path.replace(".mp4", ".raw") not in raw_files:
                FolderStructure.rename_file_if_not_renamed(unnamed_file_path, log)
        log.debug("[Server]: handled unfinished files.")
