"""Cut each scene to its narration, lay the voice over it, and join everything into one MP4.

    python tools/demo_video/assemble.py [output.mp4]

Uses the ffmpeg binary bundled with imageio-ffmpeg. No music: nothing to license.
"""
import json
import subprocess
import sys
import wave
from pathlib import Path

import imageio_ffmpeg

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
TAIL = 0.8  # a breath of silence after each line


def audio_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def run(*args: str) -> None:
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def main() -> None:
    spec = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))
    timings = json.loads((OUT / "timings.json").read_text())
    scenes = [s["id"] for s in spec["scenes"]]
    clips = OUT / "clips"
    clips.mkdir(exist_ok=True)
    total = 0.0
    for i, scene in enumerate(scenes):
        audio = OUT / "audio" / f"{scene}.wav"
        length = audio_seconds(audio) + TAIL
        vf = "fps=30,scale=1280:720:flags=lanczos,format=yuv420p"
        af = "aresample=48000,apad"
        if i == 0:
            vf += ",fade=t=in:st=0:d=0.6"
        if i == len(scenes) - 1:
            vf += f",fade=t=out:st={length - 0.8:.2f}:d=0.8"
            af += f",afade=t=out:st={length - 0.8:.2f}:d=0.8"
        run("-ss", str(timings[scene]["start"]), "-i", timings[scene]["video"], "-i", str(audio),
            "-t", f"{length:.2f}", "-vf", vf, "-af", af, "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-c:a", "aac", "-b:a", "160k",
            str(clips / f"{i:02d}-{scene}.mp4"))
        total += length
        print(f"{scene:10} {length:5.1f}s", flush=True)

    listing = clips / "list.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in sorted(clips.glob("[0-9][0-9]-*.mp4"))))
    final = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT / "kindtrail-demo.mp4"
    joined = clips / "joined.mp4"
    run("-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(joined))

    # Two-pass loudness normalisation to -14 LUFS (YouTube's playback level), peaks under -1.5 dBTP.
    target = "I=-14:TP=-1.5:LRA=11"
    probe = subprocess.run([FFMPEG, "-hide_banner", "-i", str(joined), "-af", f"loudnorm={target}:print_format=json",
                            "-vn", "-f", "null", "-"], capture_output=True, text=True, check=True).stderr
    m = json.loads(probe[probe.rindex("{"):probe.rindex("}") + 1])
    measured = (f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
                f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}")
    run("-i", str(joined), "-c:v", "copy", "-af", f"loudnorm={target}:{measured},aresample=48000",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(final))
    print(f"loudness {m['input_i']} LUFS -> -14")
    print(f"total {total:.1f}s ({int(total // 60)}:{total % 60:04.1f}) -> {final}")


if __name__ == "__main__":
    main()
