"""Audio filtergraph builder.

Layers are either
  * an asset file (looped with -stream_loop -1), or
  * a procedural generator (FFmpeg noise/expression sources + filters) — original sound
    synthesised at render time, so no third-party recording is needed.

The mix is limited, faded in/out and (for Pomodoro) a soft chime is placed at every
phase change. Everything is one `-filter_complex`; output is AAC 48 kHz stereo.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.render.fonts import quote_option

SAMPLE_RATE = 48000
CHIME_SECONDS = 3.0

GENERATORS: dict[str, dict] = {
    "rain": {"en": "Gentle rain", "label": "Mưa nhẹ", "description": "Tiếng mưa đều (pink noise lọc dải)"},
    "heavy_rain": {"en": "Heavy rain", "label": "Mưa lớn", "description": "Mưa nặng hạt, trầm và dày"},
    "fireplace": {"en": "Crackling fireplace", "label": "Lò sưởi", "description": "Tiếng lửa ấm + tiếng tí tách ngẫu nhiên"},
    "wind": {"en": "Wind", "label": "Gió", "description": "Gió thổi lên xuống chậm"},
    "stream": {"en": "Flowing stream", "label": "Suối chảy", "description": "Nước chảy róc rách"},
    "ocean": {"en": "Ocean waves", "label": "Sóng biển", "description": "Sóng vỗ theo nhịp ~9 giây"},
    "night_crickets": {"en": "Night crickets", "label": "Dế đêm", "description": "Tiếng dế kêu xa (tổng hợp)"},
    "room_tone": {"en": "Cozy room tone", "label": "Không gian phòng", "description": "Âm nền ấm của căn phòng / quán"},
    "brown_noise": {"en": "Brown noise", "label": "Brown noise", "description": "Tiếng ồn nâu trầm, hỗ trợ ngủ & tập trung"},
    "pink_noise": {"en": "Pink noise", "label": "Pink noise", "description": "Tiếng ồn hồng cân bằng"},
    "white_noise": {"en": "White noise", "label": "White noise", "description": "Tiếng ồn trắng (đã làm mềm)"},
}


@dataclass
class AudioLayer:
    kind: str                     # "asset" | "generator"
    volume: float = 1.0
    path: Path | None = None      # asset file (absolute)
    generator: str | None = None
    seed: int = 1


def _noise(label: str, color: str, amp: float, seed: int, d: float) -> str:
    return f"anoisesrc=d={d:.3f}:c={color}:r={SAMPLE_RATE}:a={amp}:s={seed}[{label}]"


def _stereo_noise(p: str, color: str, amp: float, seed: int, d: float, chain: str) -> list[str]:
    """Two decorrelated mono noises (L/R) → same filter chain → joined stereo [p]."""
    return [
        _noise(f"{p}nl", color, amp, seed, d),
        _noise(f"{p}nr", color, amp, seed + 7919, d),
        f"[{p}nl]{chain}[{p}l]",
        f"[{p}nr]{chain}[{p}r]",
        f"[{p}l][{p}r]join=inputs=2:channel_layout=stereo[{p}]",
    ]


def generator_graph(name: str, p: str, seed: int, d: float) -> list[str]:
    """Filter statements whose final output label is [p] (stereo)."""
    if name == "rain":
        return _stereo_noise(p, "pink", 0.55, seed, d,
                             "highpass=f=350,lowpass=f=7500,equalizer=f=3500:t=q:w=1:g=3")
    if name == "heavy_rain":
        return [
            *_stereo_noise(f"{p}a", "brown", 0.6, seed, d, "lowpass=f=2500"),
            *_stereo_noise(f"{p}b", "pink", 0.5, seed + 1, d, "highpass=f=200,lowpass=f=6000"),
            f"[{p}a][{p}b]amix=inputs=2:duration=longest:dropout_transition=0,volume=1.6[{p}]",
        ]
    if name == "fireplace":
        # Sparse random impulses (crackles) at 8 kHz, upsampled. A ~-114 dB noise floor is added so
        # the IIR filters never decay into denormal floats (which made this 30x slower).
        # random(i) keeps its LCG state in variable i: amplitude/right-channel states are seeded apart.
        expr = (f"if(eq(n,0),st(1,{4242 + seed})+st(5,{99 + seed}),0);"
                "if(lt(random(0),0.0013),(random(1)-0.5)*2,0)+(random(5)-0.5)*0.000004"
                f"|if(eq(n,0),st(2,{777 + seed})+st(3,{31337 + seed})+st(6,{7 + seed}),0);"
                "if(lt(random(2),0.0013),(random(3)-0.5)*2,0)+(random(6)-0.5)*0.000004")
        return [
            *_stereo_noise(f"{p}a", "brown", 0.5, seed, d, "lowpass=f=420,highpass=f=40"),
            f"aevalsrc=exprs={quote_option(expr)}:s=8000:d={d:.3f},aresample={SAMPLE_RATE},"
            f"highpass=f=600,lowpass=f=3800,volume=1.2[{p}b]",
            f"[{p}a][{p}b]amix=inputs=2:duration=longest:dropout_transition=0,volume=2[{p}]",
        ]
    if name == "wind":
        mod = quote_option("0.5+0.45*sin(2*PI*t/11)*sin(2*PI*t/7)")
        return _stereo_noise(p, "brown", 0.7, seed, d,
                             f"bandpass=f=500:width_type=h:w=700,volume={mod}:eval=frame")
    if name == "stream":
        return _stereo_noise(p, "pink", 0.55, seed, d,
                             "bandpass=f=1800:width_type=h:w=2600,tremolo=f=5.5:d=0.18")
    if name == "ocean":
        swell = quote_option("0.2+0.8*pow(sin(PI*t/9),2)")
        return _stereo_noise(p, "brown", 0.8, seed, d,
                             f"lowpass=f=1400,volume={swell}:eval=frame")
    if name == "night_crickets":
        # carrier sine × fast tremolo (chirp pulses) × slow on/off gate — all cheap native filters
        def side(freq: float, rate: float, gate_hz: float, phase: float, lab: str) -> str:
            gate = quote_option(f"gt(sin(2*PI*{gate_hz}*t+{phase}),0.55)")
            return (f"sine=frequency={freq}:sample_rate={SAMPLE_RATE}:duration={d:.3f},volume=0.35,"
                    f"tremolo=f={rate}:d=1,volume={gate}:eval=frame[{lab}]")
        return [
            side(4600, 29, 0.73, 0.0, f"{p}l"),
            side(4380, 31, 0.61, 1.3, f"{p}r"),
            # no IIR filter after the gate: gated silence would turn into slow denormals
            f"[{p}l][{p}r]join=inputs=2:channel_layout=stereo[{p}]",
        ]
    if name == "room_tone":
        return [
            *_stereo_noise(f"{p}a", "brown", 0.45, seed, d, "lowpass=f=900,highpass=f=60"),
            *_stereo_noise(f"{p}b", "pink", 0.12, seed + 3, d, "lowpass=f=3000"),
            f"[{p}a][{p}b]amix=inputs=2:duration=longest:dropout_transition=0,volume=2[{p}]",
        ]
    if name == "brown_noise":
        return _stereo_noise(p, "brown", 0.5, seed, d, "highpass=f=25")
    if name == "pink_noise":
        return _stereo_noise(p, "pink", 0.35, seed, d, "highpass=f=25")
    if name == "white_noise":
        return _stereo_noise(p, "white", 0.2, seed, d, "lowpass=f=9000")
    raise ValueError(f"Generator không tồn tại: {name}")


CHIME_EXPR = ("0.28*(sin(2*PI*880*t)+0.5*sin(2*PI*1318.5*t)+0.25*sin(2*PI*1760*t))*exp(-2.2*t)")
_FMT = f"aformat=sample_fmts=fltp:sample_rates={SAMPLE_RATE}:channel_layouts=stereo"


def chime_graph(transitions: list[float], duration: float, label: str = "chimes") -> list[str]:
    """A full-length track: silence + chime at each transition time (concat, linear cost)."""
    times = sorted(t for t in transitions if 0 < t < duration - 0.5)
    if not times:
        return []
    segments: list[tuple[str, float]] = []
    cursor = 0.0
    for t in times:
        if t < cursor:
            continue
        if t - cursor > 0.01:
            segments.append(("sil", t - cursor))
        clen = min(CHIME_SECONDS, duration - t)
        segments.append(("chime", clen))
        cursor = t + clen
    if duration - cursor > 0.01:
        segments.append(("sil", duration - cursor))

    stmts: list[str] = []
    n_chimes = sum(1 for k, _ in segments if k == "chime")
    expr = quote_option(f"{CHIME_EXPR}|{CHIME_EXPR}")
    src = f"aevalsrc=exprs={expr}:s={SAMPLE_RATE}:d={CHIME_SECONDS},{_FMT}"
    if n_chimes == 1:
        stmts.append(f"{src}[ch0]")
    else:
        outs = "".join(f"[ch{i}]" for i in range(n_chimes))
        stmts.append(f"{src},asplit={n_chimes}{outs}")
    seg_labels, ci = [], 0
    for i, (kind, length) in enumerate(segments):
        lab = f"seg{i}"
        if kind == "sil":
            stmts.append(f"anullsrc=r={SAMPLE_RATE}:cl=stereo,atrim=duration={length:.3f},{_FMT}[{lab}]")
        else:
            stmts.append(f"[ch{ci}]atrim=duration={length:.3f},asetpts=PTS-STARTPTS[{lab}]")
            ci += 1
        seg_labels.append(f"[{lab}]")
    stmts.append(f"{''.join(seg_labels)}concat=n={len(seg_labels)}:v=0:a=1[{label}]")
    return stmts


def build_audio_command(layers: list[AudioLayer], duration: float, output: Path, *,
                        transitions: list[float] | None = None, chime_volume: float = 0.6,
                        master_volume: float = 1.0, fade_in: float = 3.0, fade_out: float = 5.0,
                        bitrate_kbps: int = 192) -> tuple[list[str], str]:
    """Return (input args, filtergraph). Caller appends output args via audio_output_args()."""
    if not layers:
        raise ValueError("Cần ít nhất một lớp âm thanh")
    d = float(duration)
    inputs: list[str] = []
    stmts: list[str] = []
    mix_labels: list[str] = []
    file_idx = 0
    for i, layer in enumerate(layers):
        vol = max(0.0, min(2.0, float(layer.volume)))
        lab = f"L{i}"
        if layer.kind == "asset":
            if layer.path is None:
                raise ValueError("Lớp âm thanh asset thiếu file")
            inputs += ["-stream_loop", "-1", "-i", str(layer.path)]
            stmts.append(f"[{file_idx}:a]aresample={SAMPLE_RATE},{_FMT},volume={vol:.3f}[{lab}]")
            file_idx += 1
        elif layer.kind == "generator":
            if layer.generator not in GENERATORS:
                raise ValueError(f"Generator không tồn tại: {layer.generator}")
            g = f"g{i}"
            stmts += generator_graph(layer.generator, g, layer.seed, d)
            stmts.append(f"[{g}]{_FMT},volume={vol:.3f}[{lab}]")
        else:
            raise ValueError(f"Loại lớp âm thanh không hợp lệ: {layer.kind}")
        mix_labels.append(f"[{lab}]")

    n = len(mix_labels)
    if n == 1:
        stmts.append(f"{mix_labels[0]}anull[mix]")
    else:
        stmts.append(f"{''.join(mix_labels)}amix=inputs={n}:duration=shortest:dropout_transition=0,"
                     f"volume={n}[mix]")
    stmts.append(f"[mix]atrim=duration={d:.3f},asetpts=PTS-STARTPTS[main]")

    chimes = chime_graph(transitions or [], d)
    if chimes:
        stmts += chimes
        stmts.append(f"[chimes]volume={max(0.0, min(2.0, chime_volume)):.3f}[chv]")
        stmts.append("[main][chv]amix=inputs=2:duration=first:dropout_transition=0,volume=2[pre]")
    else:
        stmts.append("[main]anull[pre]")

    fi = min(fade_in, d / 4)
    fo = min(fade_out, d / 4)
    stmts.append(
        f"[pre]volume={max(0.0, min(2.0, master_volume)):.3f},alimiter=limit=0.89:level=0,"
        f"afade=t=in:st=0:d={fi:.3f},afade=t=out:st={max(0.0, d - fo):.3f}:d={fo:.3f},{_FMT}[aout]"
    )
    return inputs, ";".join(stmts)


def audio_output_args(output: Path, duration: float, bitrate_kbps: int = 192) -> list[str]:
    return ["-map", "[aout]", "-c:a", "aac", "-b:a", f"{bitrate_kbps}k", "-ar", str(SAMPLE_RATE),
            "-ac", "2", "-t", f"{duration:.3f}", "-movflags", "+faststart", str(output)]
