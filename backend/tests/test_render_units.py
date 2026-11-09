"""Pure unit tests of the render engine builders (no ffmpeg run)."""
from pathlib import Path

from app.render import audio, metadata, probe, timeline, video
from app.render.fonts import escape_filter_path, quote_option


def test_pomodoro_phases_cover_duration():
    phases = timeline.pomodoro_phases(7200, 25, 5, 15, 4)
    assert phases[0].start == 0 and phases[-1].end == 7200
    for a, b in zip(phases, phases[1:]):
        assert a.end == b.start
    kinds = [p.kind for p in phases]
    assert kinds[:8] == ["focus", "short_break"] * 3 + ["focus", "long_break"]
    focus = [p for p in phases if p.kind == "focus"]
    assert [p.index for p in focus] == list(range(1, len(focus) + 1))
    assert all(p.total == len(focus) for p in focus)


def test_short_trailing_phase_is_merged():
    phases = timeline.pomodoro_phases(25 * 60 + 20, 25, 5, 15, 4)
    assert len(phases) == 1 and phases[0].end == 25 * 60 + 20


def test_chapters():
    ch = timeline.chapters(timeline.pomodoro_phases(3600, 25, 5, 15, 4), "en")
    assert ch[0]["timestamp"] == "00:00" and ch[0]["title"] == "Focus 1/2"
    assert ch[1] == {"start": 1500.0, "timestamp": "25:00", "title": "Break"}
    assert timeline.chapters(timeline.countdown_phases(3600)) == []   # < 3 chapters → none


def test_quote_option_escaping():
    assert quote_option("a:b") == "'a\\:b'"
    assert escape_filter_path(r"C:\Windows\Fonts\arial.ttf") == "'C\\:/Windows/Fonts/arial.ttf'"
    assert "'" not in quote_option("it's")[1:-1]


def test_base_loop_is_seamless_and_complete(tmp_path):
    spec = video.BaseLoopSpec(1920, 1080, 30, 60, tmp_path / "bg.png", "slow_zoom", ["rain", "vignette", "warm_flicker"],
                              video.CharacterSpec(tmp_path / "c.png", 300, 400, "bottom_right", "bob"),
                              {"rain": tmp_path / "rain.png"})
    args = video.build_base_loop(spec, tmp_path / "out.mp4", crf=22, preset="veryfast", max_bitrate_kbps=4500,
                                 threads=2)
    graph = args[args.index("-filter_complex") + 1]
    assert "on/1800" in graph                       # zoom period = whole loop (60 s × 30 fps)
    assert args[args.index("-frames:v") + 1] == "1800"
    assert "vignette" in graph and "eq=brightness" in graph and "[vout]" in graph
    # every periodic motion uses an integer number of cycles per loop → seamless
    assert "sin(2*PI*t*15/60)" in graph             # character bob ≈ 4 s period


def test_final_copy_vs_overlay(tmp_path):
    args, graph = video.build_final(tmp_path / "b.mp4", tmp_path / "a.m4a", tmp_path / "o.mp4", 3600,
                                    overlay=None, width=1920, height=1080, fps=30, crf=22, preset="veryfast",
                                    max_bitrate_kbps=4500, threads=2)
    assert graph is None and "copy" in args and "-stream_loop" in args
    phases = timeline.pomodoro_phases(3600, 25, 5, 15, 4)
    ov = video.OverlaySpec("pomodoro", phases, Path("/usr/share/fonts/x.ttf"), timeline.DEFAULT_LABELS["en"])
    args, graph = video.build_final(tmp_path / "b.mp4", tmp_path / "a.m4a", tmp_path / "o.mp4", 3600,
                                    overlay=ov, width=1920, height=1080, fps=30, crf=22, preset="veryfast",
                                    max_bitrate_kbps=4500, threads=2)
    assert graph.count("drawtext=") == 2 * len(phases)
    assert "FOCUS  1/2" in graph and "lt(t,1500.000)" in graph
    assert "__FILTER__" in args and "libx264" in args


def test_audio_graph_layers_and_chimes(tmp_path):
    layers = [audio.AudioLayer("generator", 0.7, generator="rain"),
              audio.AudioLayer("asset", 0.5, path=tmp_path / "x.wav")]
    inputs, graph = audio.build_audio_command(layers, 600, tmp_path / "a.m4a", transitions=[300, 400])
    assert inputs == ["-stream_loop", "-1", "-i", str(tmp_path / "x.wav")]
    assert "anoisesrc" in graph and "[0:a]" in graph and "amix=inputs=2" in graph
    assert "concat=n=" in graph and "alimiter" in graph and "[aout]" in graph
    for name in audio.GENERATORS:
        stmts = audio.generator_graph(name, "g", 1, 10)
        assert stmts[-1].endswith("[g]") or "[g]" in stmts[-1]


def test_chime_segments_sum_to_duration():
    stmts = audio.chime_graph([10, 20], 30)
    durations = [float(s.split("duration=")[1].split(",")[0].split("[")[0]) for s in stmts if "atrim=duration=" in s]
    assert abs(sum(durations) - 30) < 0.01


def test_probe_parsers():
    stderr = """Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'video.mp4':
  Duration: 00:30:00.02, start: 0.000000, bitrate: 2500 kb/s
  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(progressive), 1920x1080 [SAR 1:1 DAR 16:9], 2300 kb/s, 30 fps, 30 tbr, 15360 tbn (default)
  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 48000 Hz, stereo, fltp, 192 kb/s (default)"""
    info = probe.parse_ffmpeg_stderr(stderr)
    assert info["duration"] == 1800.02
    assert info["video"] == {"codec": "h264", "pix_fmt": "yuv420p", "width": 1920, "height": 1080, "fps": 30.0}
    assert info["audio"] == {"codec": "aac", "sample_rate": 48000, "channels": 2}
    js = {"format": {"format_name": "mov,mp4", "duration": "12.5", "size": "100"},
          "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720,
                       "avg_frame_rate": "30000/1001", "pix_fmt": "yuv420p"},
                      {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2}]}
    info = probe.parse_ffprobe_json(js)
    assert round(info["video"]["fps"], 2) == 29.97 and info["audio"]["sample_rate"] == 48000


def test_metadata_limits():
    title = metadata.make_title("study_with_me", 480, "a very long setting name " * 5, "rainy late night",
                                {"focus_min": 50, "short_break_min": 10}, "en", "Momo")
    assert len(title) <= 100 and title.startswith("8 Hours Study With Me")
    tags = metadata.make_tags("rain_sounds", "x", "y", [f"tag number {i}" for i in range(100)], [], [], "en")
    assert sum(len(t) + 3 for t in tags) <= 500
    assert metadata.duration_label(30, "vi") == "30 Phút"
