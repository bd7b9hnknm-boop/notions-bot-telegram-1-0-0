"""
Конвертация аудио для распознавания речи.

Telegram присылает голосовые в формате ogg/opus, а Qwen ASR принимает
wav/mp3. Конвертируем в WAV 16 кГц моно через PyAV (ffmpeg идёт внутри
пакета — отдельная установка ffmpeg не нужна, в т.ч. на Railway).
"""
from __future__ import annotations

import io

import av


def to_wav(data: bytes) -> bytes:
    """ogg/opus (или любой поддерживаемый формат) -> WAV PCM 16 кГц моно."""
    in_buf = io.BytesIO(data)
    out_buf = io.BytesIO()

    in_container = av.open(in_buf)
    out_container = av.open(out_buf, mode="w", format="wav")
    try:
        out_stream = out_container.add_stream("pcm_s16le", rate=16000, layout="mono")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)

        for frame in in_container.decode(audio=0):
            frame.pts = None
            for r_frame in resampler.resample(frame):
                for packet in out_stream.encode(r_frame):
                    out_container.mux(packet)

        # дочищаем хвосты ресемплера и энкодера
        for r_frame in resampler.resample(None):
            for packet in out_stream.encode(r_frame):
                out_container.mux(packet)
        for packet in out_stream.encode(None):
            out_container.mux(packet)
    finally:
        out_container.close()
        in_container.close()

    return out_buf.getvalue()
