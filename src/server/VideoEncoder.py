import os
import struct
from FolderStructure import FolderStructure


class VideoEncoder:
    @staticmethod
    def get_ffmpeg_command(input_path, width, height, fps):
        final_output_path = input_path.rstrip(".raw") + ".mp4"
        ffmpeg_command = [
            "ffmpeg",
            "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-video_size", f"{width}x{height}",
            "-pixel_format", "bgr24",
            "-framerate", str(fps),
            "-i", input_path,
            "-c:v", "libx265",
            "-preset", "superfast",
            "-crf", "30",
            "-b:v", "3000k",
            "-an",
            final_output_path,
            "&&",
            "rm", input_path
        ]
        return ffmpeg_command

    @staticmethod
    def encode_rename_and_delete_all_unfinished_raw_files(to_be_encoded_pipe_in, log):
        raw_files = []
        log.debug("[Server]: looking for leftover unfinished or unencoded files...")
        for root, dirs, files in os.walk(os.path.join(os.path.dirname(os.path.dirname(os.getcwd())), "cams")):
            for name in files:
                path = os.path.join(root, name)
                if path.endswith(".raw"):
                    raw_files.append(path)
                elif FolderStructure.was_renamed(path):
                    FolderStructure.rename_file_if_not_renamed(path, log)

        for raw_file in raw_files:
            log.debug(f"[Server]: unpacking metadata from {raw_file}")
            width, height, fps = tuple(struct.unpack(">H", os.getxattr(raw_file, attr))[0]
                                       for attr in os.listxattr(raw_file))
            log.debug(f"[Server]: sending {raw_file} to be encoded.")
            to_be_encoded_pipe_in.send(VideoEncoder.get_ffmpeg_command(raw_file, width, height, fps))
        log.debug("[Server]: handled unfinished files.")
