#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Live Stream Transcription - 带时间戳的语音识别
使用 faster-whisper 实现实时/离线语音转文字
"""

import sys
import json
import argparse
import os
from datetime import datetime


def install_package():
    """检查并提示安装依赖"""
    try:
        from faster_whisper import WhisperModel
        return True
    except ImportError:
        print("正在安装 faster-whisper...")
        os.system("pip install faster-whisper")
        try:
            from faster_whisper import WhisperModel
            return True
        except ImportError:
            return False


def transcribe_audio(
    audio_path: str,
    model_size: str = "large-v3",
    language: str = "zh",
    device: str = "auto",
    condition_on_previous_text: bool = True,
    vad_filter: bool = True,
    vad_parameters: dict = None,
    initial_prompt: str = "下面是一段来自主播诗诗的cs职业赛事解说，由A队对阵G2："
) -> list[dict]:
    """
    使用 faster-whisper 转录音频

    Args:
        audio_path: 音频/视频文件路径
        model_size: 模型大小 (tiny, base, small, medium, large-v3)
        language: 语言代码 (zh, en, ja, etc., None=自动检测)
        device: 设备 (auto, cpu, cuda)
        condition_on_previous_text: 是否利用前一段文本提高准确性
        vad_filter: 是否使用语音活动检测过滤静音
        vad_parameters: VAD参数
        initial_prompt: 初始提示词，帮助提高特定术语识别
        vocabulary: 自定义词汇表 (由create_custom_vocabulary创建)

    Returns:
        段落列表，每段包含 text, start, end
    """
    from faster_whisper import WhisperModel

    # 选择设备
    if device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"

    print(f"[Transcribe] 加载模型: {model_size} ({device})")
    model = WhisperModel(model_size, device=device, compute_type="float16" if device == "cuda" else "int8", cpu_threads=16)

    # VAD参数
    if vad_parameters is None:
        vad_parameters = {
            "min_silence_duration_ms": 500,
        }

    print(f"[Transcribe] 开始转录: {audio_path}")

    # 执行转录
    segments, info = model.transcribe(
        audio_path,
        language=language,
        condition_on_previous_text=condition_on_previous_text,
        vad_filter=vad_filter,
        vad_parameters=vad_parameters,
        initial_prompt=initial_prompt,
        word_timestamps=True
    )

    # 显示识别信息
    print(f"[Transcribe] 语言: {info.language}")
    print(f"[Transcribe] 检测到语言概率: {info.language_probability:.2%}")

    # 转换为标准格式
    results = []
    for segment in segments:
        results.append({
            "text": segment.text.strip(),
            "start": round(segment.start, 2),
            "end": round(segment.end, 2)
        })

    print(f"[Transcribe] 转录完成: {len(results)} 个片段")

    return results


def transcribe_with_words(
    audio_path: str,
    model_size: str = "large-v3",
    language: str = "zh",
    device: str = "auto"
) -> list[dict]:
    """
    转录音频并返回词级别时间戳

    Returns:
        词列表，每词包含 text, start, end
    """
    from faster_whisper import WhisperModel

    if device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"

    print(f"[Transcribe] 加载模型: {model_size} ({device})")
    model = WhisperModel(model_size, device=device, compute_type="float16" if device == "cuda" else "int8")

    print(f"[Transcribe] 开始转录(词级时间戳): {audio_path}")

    segments, info = model.transcribe(
        audio_path,
        language=language,
        word_timestamps=True,
        vad_filter=True
    )

    words = []
    for segment in segments:
        if segment.words:
            for word in segment.words:
                words.append({
                    "word": word.word.strip(),
                    "start": round(word.start, 2),
                    "end": round(word.end, 2),
                    "probability": round(word.probability, 2)
                })

    print(f"[Transcribe] 转录完成: {len(words)} 个词")

    return words


def save_transcript(transcript: list[dict], output_path: str, format: str = "json"):
    """
    保存转录结果

    Args:
        transcript: 转录结果列表
        output_path: 输出文件路径
        format: 输出格式 (json, srt, vtt, txt)
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    if format == "json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(transcript, f, ensure_ascii=False, indent=2)

    elif format == "txt":
        with open(output_path, "w", encoding="utf-8") as f:
            for seg in transcript:
                f.write(f"[{seg['start']:.2f} - {seg['end']:.2f}] {seg['text']}\n")

    elif format == "srt":
        with open(output_path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(transcript, 1):
                start = _format_srt_time(seg['start'])
                end = _format_srt_time(seg['end'])
                f.write(f"{i}\n{start} --> {end}\n{seg['text']}\n\n")

    elif format == "vtt":
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")
            for seg in transcript:
                start = _format_vtt_time(seg['start'])
                end = _format_vtt_time(seg['end'])
                f.write(f"{start} --> {end}\n{seg['text']}\n\n")

    print(f"[Transcribe] 已保存到: {output_path}")


def _format_srt_time(seconds: float) -> str:
    """秒转换为 SRT 时间格式 HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_vtt_time(seconds: float) -> str:
    """秒转换为 VTT 时间格式 HH:MM:SS.mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def main():
    parser = argparse.ArgumentParser(description="语音转文字工具 - 带时间戳")
    parser.add_argument(
        "input",
        nargs="?",
        help="输入音频/视频文件路径"
    )
    parser.add_argument(
        "--model", "-m",
        default="large-v3",
        choices=["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"],
        help="模型大小 (默认: large-v3)"
    )
    parser.add_argument(
        "--language", "-l",
        default="zh",
        help="语言代码 (默认: zh, 自动检测请用 auto)"
    )
    parser.add_argument(
        "--output", "-o",
        default="transcript.json",
        help="输出文件路径 (默认: transcript.json)"
    )
    parser.add_argument(
        "--format", "-f",
        default="json",
        choices=["json", "txt", "srt", "vtt"],
        help="输出格式 (默认: json)"
    )
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cpu", "cuda"],
        help="运行设备 (默认: auto)"
    )
    parser.add_argument(
        "--words",
        action="store_true",
        help="输出词级时间戳"
    )
    parser.add_argument(
        "--prompt",
        help="初始提示词，帮助识别特定术语"
    )

    args = parser.parse_args()

    # 检查输入文件
    if not args.input:
        parser.print_help()
        print("\n错误: 请提供输入文件")
        return 1

    if not os.path.exists(args.input):
        print(f"错误: 文件不存在: {args.input}")
        return 1

    # 检查依赖
    if not install_package():
        print("错误: 无法安装 faster-whisper")
        return 1

    # 解析语言
    language = None if args.language == "auto" else args.language

    try:
        if args.words:
            # 词级时间戳
            result = transcribe_with_words(
                args.input,
                model_size=args.model,
                language=language,
                device=args.device
            )
            # 词级输出只支持json格式
            save_transcript(result, args.output, "json")
        else:
            # 段落级时间戳
            result = transcribe_audio(
                args.input,
                model_size=args.model,
                language=language,
                device=args.device,
                initial_prompt=args.prompt
            )
            save_transcript(result, args.output, args.format)

        print(f"\n转录完成!")
        return 0

    except KeyboardInterrupt:
        print("\n已取消")
        return 130
    except Exception as e:
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
