import os
import struct
from FolderStructure import FolderStructure
from src.server.Config import config
import ntpath
import subprocess


class VideoEncoder:
    @staticmethod
    def get_ffmpeg_command(input_path, width, height, fps):
        final_output_path = os.path.join(os.path.dirname(input_path), os.path.splitext(ntpath.basename(input_path))[0] +
                                         f".{config.OutputFileExtension}")
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
    def encode_rename_and_delete_all_unfinished_raw_files(encoding_queue, log):
        raw_files = []
        to_be_renamed = []
        log.debug("[Server]: looking for leftover unfinished or unencoded files...")
        for root, dirs, files in os.walk(os.path.join(os.path.dirname(os.path.dirname(os.getcwd())), "cams")):
            for name in files:
                path = os.path.join(root, name)
                if path.endswith(".raw"):
                    log.debug(f"[Server]: leftover raw file found: {path}")
                    raw_files.append(path)
                elif not FolderStructure.was_renamed(path) and not FolderStructure.is_temp_file(path):
                    log.debug(f"[Server]: not renamed video file found: {path}")
                    to_be_renamed.append(path)

        for raw_file in raw_files:
            log.debug(f"[Server]: unpacking metadata from {raw_file}")
            width, height, fps = tuple(struct.unpack(">H", os.getxattr(raw_file, attr))[0]
                                       for attr in os.listxattr(raw_file))
            log.debug(f"[Server]: sending {raw_file} to be encoded.")
            encoding_queue.put((2, VideoEncoder.get_ffmpeg_command(raw_file, width, height, fps)))

        for unnamed_file_path in to_be_renamed:
            if unnamed_file_path.replace(".mp4", ".raw") not in raw_files:
                FolderStructure.rename_file_if_not_renamed(unnamed_file_path, log)
        log.debug("[Server]: handled unfinished files.")

    @staticmethod
    def concat_mp4s(concat_file_path, output_path, log):
        command = ["sudo", "ffmpeg",
                   "-f", "concat",
                   "-safe", "0",
                   "-i", concat_file_path,
                   "-c", "copy",
                   output_path]
        proc = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        rc = proc.returncode
        if rc != 0:
            log.error(proc.stderr)
        return rc
