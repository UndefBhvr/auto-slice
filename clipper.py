#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Video Clipper - 根据选定的段落剪辑视频
使用FFmpeg无损剪辑，保留原视频的清晰度和格式
"""

import sys
import json
import argparse
import os
import subprocess
import shlex


def get_video_info(video_path: str) -> dict:
    """使用ffprobe获取视频信息"""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {}
    return json.loads(result.stdout)


def format_time(seconds: float) -> str:
    """将秒数格式化为HH:MM:SS.ms格式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    else:
        return f"{minutes:02d}:{secs:06.3f}"


def sanitize_filename(filename: str) -> str:
    """移除文件名中不合法的字符"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    # 移除首尾空格和点
    filename = filename.strip(' .')
    return filename


def clip_video(
    input_video: str,
    output_dir: str,
    start_time: float,
    end_time: float,
    title: str,
    quality_preset: str = "high"
) -> bool:
    """
    使用ffmpeg剪辑视频片段

    Args:
        input_video: 输入视频路径
        output_dir: 输出目录
        start_time: 开始时间（秒）
        end_time: 结束时间（秒）
        title: 片段标题（用作输出文件名）
        quality_preset: 质量预设 (high, medium, low)

    Returns:
        是否成功
    """
    duration = end_time - start_time
    start_str = format_time(start_time)
    duration_str = format_time(duration)

    # 清理文件名
    safe_title = sanitize_filename(title)
    if not safe_title:
        safe_title = f"clip_{start_time:.0f}"

    output_ext = os.path.splitext(input_video)[1] or ".mp4"
    output_path = os.path.join(output_dir, safe_title + output_ext)

    # 构建ffmpeg命令
    # -ss start_time: 开始时间（在输入前所以是精确seek）
    # -i input: 输入文件
    # -t duration: 持续时间
    # -c copy: 流拷贝（无损）
    # -avoid_negative_ts make_zero: 避免负时间戳问题
    cmd = [
        "ffmpeg",
        "-y",  # 覆盖已存在的文件
        "-ss", start_str,
        "-i", input_video,
        "-t", duration_str,
        "-c:v", "copy",
        "-c:a", "copy",
        "-avoid_negative_ts", "make_zero",
        output_path
    ]

    print(f"\n[{safe_title}]")
    print(f"  时间: {start_str} - {format_time(end_time)} (时长: {duration:.1f}秒)")
    print(f"  输出: {output_path}")
    print(f"  命令: {' '.join(shlex.quote(c) for c in cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(60, duration * 2)  # 至少60秒或时长2倍
        )

        if result.returncode == 0:
            # 检查输出文件
            if os.path.exists(output_path):
                size = os.path.getsize(output_path)
                print(f"  状态: 成功 ({size / 1024 / 1024:.2f} MB)")
                return True
            else:
                print(f"  状态: 失败 (输出文件不存在)")
                return False
        else:
            print(f"  状态: 失败")
            if result.stderr:
                # 只显示最后几行错误
                errors = result.stderr.strip().split('\n')
                print(f"  错误: {errors[-1] if errors else '未知错误'}")
            return False

    except subprocess.TimeoutExpired:
        print(f"  状态: 失败 (超时)")
        return False
    except Exception as e:
        print(f"  状态: 失败 ({str(e)})")
        return False


def main():
    parser = argparse.ArgumentParser(description="视频剪辑工具 - 根据选定段落剪辑视频")
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="输入视频文件路径"
    )
    parser.add_argument(
        "--segments", "-s",
        default="selected_segments.json",
        help="段落信息JSON文件 (默认: selected_segments.json)"
    )
    parser.add_argument(
        "--output", "-o",
        default="clips",
        help="输出目录 (默认: clips)"
    )
    parser.add_argument(
        "--prefix",
        default="",
        help="输出文件名前缀"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅显示将要执行的操作，不实际剪辑"
    )

    args = parser.parse_args()

    # 检查ffmpeg是否可用
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("错误: 未找到ffmpeg，请先安装ffmpeg")
        print("  Ubuntu/Debian: sudo apt install ffmpeg")
        print("  Windows: 下载 https://ffmpeg.org/download.html")
        print("  macOS: brew install ffmpeg")
        return 1

    # 检查输入文件
    if not os.path.exists(args.input):
        print(f"错误: 输入文件不存在: {args.input}")
        return 1

    # 读取段落信息
    if not os.path.exists(args.segments):
        print(f"错误: 段落文件不存在: {args.segments}")
        print("请先运行 main.py --demo 生成段落文件")
        return 1

    with open(args.segments, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data.get("segments", [])
    if not segments:
        print("错误: 段落文件中没有片段")
        return 1

    # 创建输出目录
    os.makedirs(args.output, exist_ok=True)

    # 显示视频信息
    print("=" * 80)
    print("视频剪辑工具")
    print("=" * 80)
    print(f"输入视频: {args.input}")
    print(f"输出目录: {args.output}")

    video_info = get_video_info(args.input)
    if video_info:
        format_info = video_info.get("format", {})
        duration = float(format_info.get("duration", 0))
        print(f"视频时长: {int(duration // 60)}:{duration % 60:05.2f}")

    print(f"片段数量: {len(segments)}")
    print("=" * 80)

    if args.dry_run:
        print("\n[Dry Run] 以下是将要执行的操作:\n")

    # 剪辑每个片段
    success_count = 0
    fail_count = 0

    for i, seg in enumerate(segments, 1):
        title = seg.get("title", f"clip_{i}")
        if args.prefix:
            title = f"{args.prefix}_{title}"

        start = seg.get("start", 0)
        end = seg.get("end", 0)

        if end <= start:
            print(f"\n[{title}] 跳过: 结束时间({end}) <= 开始时间({start})")
            fail_count += 1
            continue

        if args.dry_run:
            print(f"  [{i}] {title}: {format_time(start)} - {format_time(end)}")
        else:
            if clip_video(args.input, args.output, start, end, title):
                success_count += 1
            else:
                fail_count += 1

    # 总结
    print("\n" + "=" * 80)
    print("剪辑完成")
    print("=" * 80)
    print(f"成功: {success_count} 个")
    print(f"失败: {fail_count} 个")

    if success_count > 0 and not args.dry_run:
        print(f"\n输出文件保存在: {os.path.abspath(args.output)}")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
