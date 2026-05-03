#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GLM-ASR Transcription - 使用智谱GLM-ASR模型进行语音识别
模型: ZhipuAI/GLM-ASR-Nano-2512
"""

import sys
import json
import argparse
import os
import subprocess


def install_package():
    """安装依赖"""
    try:
        from modelscope import AutoModelForSeq2SeqLM, AutoProcessor
        return True
    except ImportError:
        print("正在安装 modelscope...")
        os.system("pip install modelscope")
        try:
            from modelscope import AutoModelForSeq2SeqLM, AutoProcessor
            return True
        except ImportError:
            return False


def get_audio_duration(audio_path: str) -> float:
    """使用ffprobe获取音频时长（秒）"""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", audio_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0))
    except:
        return 0


def extract_audio_segment(input_path: str, output_path: str, start: float, end: float):
    """使用ffmpeg提取音频片段"""
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ss", str(start),
        "-to", str(end),
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_path
    ]
    subprocess.run(cmd, capture_output=True)


def transcribe_audio(
    audio_path: str,
    model_name: str = "ZhipuAI/GLM-ASR-Nano-2512",
    initial_prompt: str = "下面是一段来自主播诗诗的cs职业赛事解说，由A队对阵G2：",
    segment_duration: int = 30,
    hotwords: list = None
) -> list[dict]:
    """
    使用 GLM-ASR 模型转录音频
    由于GLM-ASR每次只能处理短音频，这里按时间段分割处理

    Args:
        audio_path: 音频/视频文件路径
        model_name: 模型名称
        initial_prompt: 初始提示词，引导模型识别特定内容
        segment_duration: 每段音频的时长（秒），默认30秒
        hotwords: 热词列表，用于提示模型可能出现的词语

    Returns:
        段落列表，每段包含 text, start, end
    """
    from modelscope import AutoModelForSeq2SeqLM, AutoProcessor

    print(f"[GLM-ASR] 加载模型: {model_name}")
    processor = AutoProcessor.from_pretrained(model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name, dtype="auto", device_map="auto")

    # 构建prompt，加入热词
    prompt = initial_prompt
    if hotwords:
        hotwords_str = "、".join(hotwords)
        prompt = f"{initial_prompt} 这段话中可能出现下列词语：{hotwords_str}"

    # 获取音频总时长
    duration = get_audio_duration(audio_path)
    print(f"[GLM-ASR] 音频总时长: {duration:.1f} 秒")

    print(f"[GLM-ASR] 开始转录: {audio_path}")
    print(f"[GLM-ASR] Prompt: {prompt}")

    # 由于GLM-ASR每次只能处理约30秒，这里分割处理
    all_results = []
    import tempfile

    for start_time in range(0, int(duration), segment_duration):
        end_time = min(start_time + segment_duration, duration)
        print(f"[GLM-ASR] 处理段落: {start_time:.1f}s - {end_time:.1f}s")

        # 提取音频片段
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        extract_audio_segment(audio_path, tmp_path, start_time, end_time)

        # 使用apply_transcription_request处理
        inputs = processor.apply_transcription_request(tmp_path)
        inputs = inputs.to(model.device, dtype=model.dtype)

        # 生成转录
        outputs = model.generate(**inputs, do_sample=False, max_new_tokens=500)

        # 解码
        if hasattr(inputs, 'input_ids'):
            input_length = inputs.input_ids.shape[1]
            decoded = processor.batch_decode(
                outputs[:, input_length:],
                skip_special_tokens=True
            )
        else:
            decoded = processor.batch_decode(outputs, skip_special_tokens=True)

        # 解析结果
        for output in decoded:
            if isinstance(output, str):
                text = output.strip()
            elif hasattr(output, '__str__'):
                text = str(output).strip()
            else:
                text = ""

            if text:
                all_results.append({
                    "text": text,
                    "start": float(start_time),
                    "end": float(end_time)
                })

        # 清理临时文件
        os.unlink(tmp_path)

    print(f"[GLM-ASR] 转录完成: {len(all_results)} 个段落")

    return all_results


def save_transcript(transcript: list[dict], output_path: str, format: str = "json"):
    """保存转录结果"""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    if format == "json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(transcript, f, ensure_ascii=False, indent=2)
    elif format == "txt":
        with open(output_path, "w", encoding="utf-8") as f:
            for seg in transcript:
                f.write(f"[{seg['start']:.2f} - {seg['end']:.2f}] {seg['text']}\n")

    print(f"[Transcribe] 已保存到: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="GLM-ASR 语音转文字工具")
    parser.add_argument("input", nargs="?", help="输入音频/视频文件路径")
    parser.add_argument("--model", "-m", default="ZhipuAI/GLM-ASR-Nano-2512",
                        help="模型名称 (默认: ZhipuAI/GLM-ASR-Nano-2512)")
    parser.add_argument("--prompt", "-p", default="下面是一段来自主播诗诗的cs职业赛事解说，由A队对阵G2：",
                        help="初始提示词")
    parser.add_argument("--output", "-o", default="transcript_glm.json", help="输出文件路径")
    parser.add_argument("--format", "-f", default="json", choices=["json", "txt"], help="输出格式")
    parser.add_argument("--config", default="config.json", help="配置文件路径")

    args = parser.parse_args()

    if not args.input:
        parser.print_help()
        print("\n错误: 请提供输入文件")
        return 1

    if not os.path.exists(args.input):
        print(f"错误: 文件不存在: {args.input}")
        return 1

    # 检查依赖
    if not install_package():
        print("错误: 无法安装 modelscope")
        return 1

    # 加载热词
    hotwords = None
    if os.path.exists(args.config):
        try:
            with open(args.config, "r", encoding="utf-8") as f:
                config = json.load(f)
                hotwords = config.get("transcription", {}).get("hotwords", None)
                if hotwords:
                    print(f"[GLM-ASR] 加载热词: {len(hotwords)} 个")
        except Exception as e:
            print(f"[GLM-ASR] 加载配置失败: {e}")

    try:
        result = transcribe_audio(
            args.input,
            model_name=args.model,
            initial_prompt=args.prompt,
            hotwords=hotwords
        )
        if result:
            save_transcript(result, args.output, args.format)
            print("\n转录完成!")
        else:
            print("转录失败或未返回结果")
        return 0
    except Exception as e:
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
