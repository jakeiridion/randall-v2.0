import os
from src.server.Config import config
import ntpath
import subprocess


class VideoEncoder:
    @staticmethod
    def get_ffmpeg_command(input_path, width, height, fps):
        final_output_path = os.path.join(os.path.dirname(input_path), os.path.splitext(ntpath.basename(input_path))[0] +
                                         config.OutputFileExtension)
        ffmpeg_command = ["ffmpeg",
                          "-y",
                          "-f", "rawvideo",
                          "-vcodec", "rawvideo",
                          "-video_size", f"{width}x{height}",
                          "-pixel_format", "bgr24",
                          "-framerate", "5",
                          "-i", input_path]
        ffmpeg_command += config.FFMPEGOutputFileOptions.split(" ")
        ffmpeg_command.append(final_output_path)
        return ffmpeg_command

    @staticmethod
    def concat_video_files(concat_file_path, output_path, log):
        command = ["sudo", "ffmpeg",
                   "-f", "concat",
                   "-safe", "0",
                   "-i", concat_file_path,
                   "-c", "copy",
                   output_path]
        proc = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        rc = proc.returncode
        log.debug(f"[Server]: Concat Process complete with exit code {rc}")
        if rc != 0:
            log.error(proc.stderr)
        return rc

    @staticmethod
    def get_video_length(file_path, log):
        get_video_length_command = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-sexagesimal",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        log.debug("[Server]: starting ffprobe process...")
        proc = subprocess.run(get_video_length_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        rc = proc.returncode
        log.debug(f"[Server]: ffprobe process finished with exit code {rc}.")
        if rc != 0:
            log.error(proc.stderr)
        return proc
