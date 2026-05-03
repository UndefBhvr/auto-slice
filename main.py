#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Live Stream Clipper - 直播切片工具
完整流程：转录 -> LLM精彩片段分析 -> 片段选择 -> 视频剪辑
"""

import sys
import json
import argparse
import threading
import os

# === Encoding setup - must be first ===
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['LANG'] = 'en_US.UTF-8'

from http.server import HTTPServer

from mcp_server.server import MCPRequestHandler, SegmentStore


def load_demo_transcript():
    """Load a demo transcript for testing."""
    return [
        {"text": "大家好，欢迎来到今天的直播！", "start": 0.0, "end": 5.0},
        {"text": "今天我们要聊一个非常重要的话题", "start": 5.0, "end": 10.0},
        {"text": "我真的太激动了，这个消息太震撼了！", "start": 15.0, "end": 22.0},
        {"text": "大家有没有看到刚才那个弹幕，太好笑了", "start": 25.0, "end": 30.0},
        {"text": "说真的，我对这个问题非常生气", "start": 45.0, "end": 52.0},
        {"text": "我们必须认真对待这件事", "start": 55.0, "end": 60.0},
        {"text": "感谢大家的支持，我会继续努力的", "start": 120.0, "end": 128.0},
        {"text": "这太疯狂了，我们做到了！", "start": 180.0, "end": 186.0},
    ]


def display_segments_cli(segments: list[dict]):
    """Display segments in CLI format."""
    print("\n" + "=" * 80)
    print("找到的精彩片段：")
    print("=" * 80)

    for i, seg in enumerate(segments, 1):
        start_min = int(seg['start'] // 60)
        start_sec = int(seg['start'] % 60)
        end_min = int(seg['end'] // 60)
        end_sec = int(seg['end'] % 60)

        print(f"\n[{i}] {seg['title']}")
        print(f"    时间: {start_min:02d}:{start_sec:02d} - {end_min:02d}:{end_sec:02d}")
        print(f"    摘要: {seg['summary']}")

    print("\n" + "=" * 80)
    print(f"共找到 {len(segments)} 个片段")
    print("=" * 80)


class MCPServerRunner:
    """Helper class to run MCP server with shared store."""
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.store = SegmentStore()
        self.server = None
        self.thread = None

    def start(self):
        MCPRequestHandler.store = self.store
        self.server = HTTPServer((self.host, self.port), MCPRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        print(f"[MCP Server] Started at http://{self.host}:{self.port}")

    def get_url(self):
        return f"http://{self.host}:{self.port}"


def run_transcription(audio_path: str, model_size: str = "large-v3", language: str = "zh", vocabulary: dict = None) -> list[dict]:
    """运行语音转录"""
    from transcriber import transcribe_audio, save_transcript

    print("\n" + "=" * 80)
    print("第一部分：语音转录")
    print("=" * 80)

    # 检查ffmpeg（转录需要）
    import subprocess
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("错误: 未找到ffmpeg，无法提取音频")
        print("请安装: sudo apt install ffmpeg")
        return []

    # 检查faster-whisper
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("正在安装 faster-whisper...")
        os.system("pip install faster-whisper")

    transcript = transcribe_audio(
        audio_path,
        model_size=model_size,
        language=language if language != "auto" else None,
        vocabulary=vocabulary
    )

    # 保存转录结果
    transcript_path = "transcript.json"
    save_transcript(transcript, transcript_path, "json")
    print(f"[Main] 转录结果已保存到: {transcript_path}")

    return transcript


def run_llm_analysis(transcript: list[dict]) -> list[dict]:
    """运行LLM精彩片段分析"""
    from llm_client import LLMClient

    print("\n" + "=" * 80)
    print("第二部分：LLM精彩片段分析")
    print("=" * 80)

    llm_client = LLMClient("config.json")
    segments = llm_client.analyze_emotion_segments(transcript)

    if not segments:
        print("[Main] LLM未找到任何精彩片段")
        return []

    print(f"[Main] LLM找到 {len(segments)} 个精彩片段")
    return segments


def run_segment_selection(segments: list[dict], store: SegmentStore):
    """交互式选择片段"""
    print("\n" + "=" * 80)
    print("第三部分：片段选择")
    print("=" * 80)

    # 添加到store
    for seg in segments:
        store.add_segment(
            start=seg["start"],
            end=seg["end"],
            summary=seg["summary"],
            title=seg["title"]
        )

    # 显示片段
    display_segments_cli(segments)

    # 交互选择
    print("\n请选择要保留的片段（输入编号，用逗号分隔，如 1,3,5）：")
    print("直接回车保留所有片段，输入 q 退出")

    try:
        choice = input("> ").strip()
        if choice.lower() == 'q':
            print("退出")
            return []

        if choice:
            selected_indices = set()
            choice_clean = choice.replace(' ', '')
            for part in choice_clean.split(','):
                if part.isdigit():
                    idx = int(part) - 1
                    if 0 <= idx < len(segments):
                        selected_indices.add(idx)

            if selected_indices:
                store.set_selections_by_indices(selected_indices)
                print(f"已选择 {len(selected_indices)} 个片段")
        else:
            store.set_selections_by_indices(set(range(len(segments))))
            print("已选择所有片段")
    except EOFError:
        pass

    return store.get_selected_segments()


def run_video_clipping(video_path: str, selected: list):
    """剪辑视频"""
    print("\n" + "=" * 80)
    print("第四部分：视频剪辑")
    print("=" * 80)

    from clipper import clip_video

    # 检查ffmpeg
    import subprocess
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("错误: 未找到ffmpeg，无法剪辑视频")
        return

    os.makedirs("clips", exist_ok=True)

    success = 0
    fail = 0

    for seg in selected:
        if clip_video(video_path, "clips", seg.start, seg.end, seg.title):
            success += 1
        else:
            fail += 1

    print(f"\n剪辑完成: 成功 {success} 个，失败 {fail} 个")


def main():
    parser = argparse.ArgumentParser(
        description="直播切片工具 - 转录 -> 精彩片段分析 -> 片段选择 -> 视频剪辑",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 完整流程（需要视频文件和配置）
  python main.py --video video.mp4 --config config.json

  # 仅转录
  python main.py --transcribe-only --video video.mp4

  # 仅LLM分析（使用已有转录文件）
  python main.py --analyze-only --transcript transcript.json

  # 仅选择片段（使用demo数据）
  python main.py --demo

  # 仅剪辑视频
  python main.py --clip-only --video video.mp4
"""
    )
    parser.add_argument("--video", help="输入视频文件路径")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    parser.add_argument("--transcript", help="转录文件路径 (JSON格式)")
    parser.add_argument("--demo", action="store_true", help="使用演示转录文本")

    # 步骤控制
    parser.add_argument("--transcribe-only", action="store_true", help="仅运行转录")
    parser.add_argument("--analyze-only", action="store_true", help="仅运行LLM分析")
    parser.add_argument("--select-only", action="store_true", help="仅运行片段选择")
    parser.add_argument("--clip-only", action="store_true", help="仅运行视频剪辑")
    parser.add_argument("--output", "-o", default="segments.json", help="输出文件路径 (默认: segments.json)")

    args = parser.parse_args()

    # 加载配置
    config = {}
    if os.path.exists(args.config):
        with open(args.config, "r", encoding="utf-8") as f:
            config = json.load(f)

    transcription_config = config.get("transcription", {})
    transcription_model = transcription_config.get("model", "large-v3")
    transcription_language = transcription_config.get("language", "zh")

    # 启动MCP服务器
    mcp = MCPServerRunner("127.0.0.1", 8765)
    mcp.start()

    transcript = None
    segments = []
    selected = []

    # === 第一步：转录 ===
    if args.transcribe_only or args.video:
        if not args.video and not args.transcribe_only:
            # 完整流程但没有视频
            if not args.demo:
                print("错误: 请提供 --video 参数")
                return 1

        if args.video:
            if not os.path.exists(args.video):
                print(f"错误: 视频文件不存在: {args.video}")
                return 1
            transcript = run_transcription(args.video, transcription_model, transcription_language)

        if args.transcribe_only:
            print("[Main] 仅转录模式，完成后退出")
            return 0

    # === 第二步：LLM分析 ===
    if args.analyze_only or (transcript and not args.select_only and not args.clip_only):
        if args.analyze_only or args.transcript:
            if args.transcript:
                if not os.path.exists(args.transcript):
                    print(f"错误: 转录文件不存在: {args.transcript}")
                    return 1
                with open(args.transcript, "r", encoding="utf-8") as f:
                    transcript = json.load(f)
                print(f"[Main] 加载转录文件: {args.transcript}")

        if not transcript:
            if args.demo:
                transcript = load_demo_transcript()
                print(f"[Main] 使用演示转录文本，共 {len(transcript)} 条")
            else:
                print("错误: 没有可用的转录数据")
                return 1

        segments = run_llm_analysis(transcript)

        if args.analyze_only:
            # 保存LLM分析结果
            output = {
                "segments": [
                    {
                        "start": seg["start"],
                        "end": seg["end"],
                        "title": seg["title"],
                        "summary": seg["summary"]
                    }
                    for seg in segments
                ]
            }
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            print(f"[Main] 结果已保存到 {args.output}")
            print("[Main] 仅分析模式，完成后退出")
            return 0

    # === 第三步：片段选择 ===
    if args.select_only or (segments and not args.clip_only):
        if not segments:
            print("错误: 没有可用的片段数据")
            return 1

        selected = run_segment_selection(segments, mcp.store)

        if args.select_only:
            # 保存选择结果
            output = {
                "segments": [
                    {
                        "start": seg.start,
                        "end": seg.end,
                        "title": seg.title,
                        "summary": seg.summary
                    }
                    for seg in selected
                ]
            }
            with open("selected_segments.json", "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            print(f"结果已保存到 selected_segments.json")
            return 0

    # === 第四步：视频剪辑 ===
    if args.clip_only:
        if not os.path.exists("selected_segments.json"):
            print("错误: 没有选择结果文件 selected_segments.json")
            return 1

        with open("selected_segments.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        selected = []
        for seg in data.get("segments", []):
            from mcp_server.server import Segment
            s = Segment(
                id=f"clip_{len(selected)}",
                start=seg["start"],
                end=seg["end"],
                summary=seg.get("summary", ""),
                title=seg["title"],
                created_at="",
                selected=True
            )
            selected.append(s)

    if selected:
        if not args.video:
            print("警告: 没有提供视频文件，跳过剪辑步骤")
        else:
            run_video_clipping(args.video, selected)
    else:
        print("错误: 没有选中的片段")
        return 1

    # 保存最终结果
    if selected:
        output = {
            "segments": [
                {
                    "start": seg.start,
                    "end": seg.end,
                    "title": seg.title,
                    "summary": seg.summary
                }
                for seg in selected
            ]
        }
        with open("selected_segments.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n最终结果已保存到 selected_segments.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())
