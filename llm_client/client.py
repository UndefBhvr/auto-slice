import json
import httpx
from typing import Optional


class LLMClient:
    def __init__(self, config_path: str = "config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)["llm"]
        self.base_url = self.config["base_url"]
        self.api_key = self.config["api_key"]
        self.model = self.config["model"]
        self.temperature = self.config["temperature"]

    def analyze_emotion_segments(
        self,
        transcript: list[dict],
        stream_callback=None
    ) -> list[dict]:
        """
        Analyze transcript and identify emotional/passionate segments.
        """
        prompt = self._build_prompt(transcript)

        messages = [
            {"role": "system", "content": """你是一个游戏以及解说直播内容分析专家，擅长识别游戏发生精彩事件或主播情绪激动的片段。
你的任务是在直播转录文本中找出主播表达强烈情绪（兴奋、愤怒、悲伤、喜悦、惊讶等）的片段，或是比赛中选手打出精彩操作（如连杀、少打多翻盘、连续追分），
或是选手出现失误导致情绪波动的片段，
或者说出特别重要、令人难忘的内容。

对于每个精彩的片段，请提供：
1. 开始和结束的时间戳
2. 简要概括内容（1-2句话）
3. 一个吸引人的标题（不超过10个字）

**重要：所有输出必须使用中文，包括summary和title字段。**

只返回JSON数组格式，不要返回其他内容。
格式示例：
[
  {"start": 12.5, "end": 45.2, "summary": "主播兴奋地宣布粉丝数突破10万", "title": "10万粉丝里程碑"},
  {"start": 120.0, "end": 180.5, "summary": "主播因为游戏bug明显表现出愤怒情绪", "title": "怒喷游戏bug"}
]"""},
            {"role": "user", "content": prompt}
        ]

        response = self._call_llm(messages, stream=stream_callback is not None)

        if stream_callback:
            full_content = ""
            for chunk in response:
                if chunk.get("choices"):
                    delta = chunk["choices"][0].get("delta", {})
                    if delta.get("content"):
                        content_str = delta["content"]
                        if isinstance(content_str, bytes):
                            content_str = content_str.decode('utf-8', errors='replace')
                        full_content += content_str
                        stream_callback(content_str)
            return self._parse_response(full_content)
        else:
            # Non-streaming response
            content = response["choices"][0]["message"]["content"]
            if isinstance(content, bytes):
                content = content.decode('utf-8', errors='replace')
            return self._parse_response(content)

    def _build_prompt(self, transcript: list[dict]) -> str:
        transcript_lines = []
        for t in transcript:
            text = t.get("text", "")
            if isinstance(text, bytes):
                text = text.decode('utf-8', errors='replace')
            transcript_lines.append(f"[{t['start']:.1f}s - {t['end']:.1f}s] {text}")
        return "分析以下直播转录文本，找出其中精彩的片段：\n\n" + "\n".join(transcript_lines)

    def _call_llm(self, messages: list, stream: bool = False):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature
        }

        if stream:
            data["stream"] = True

        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data
            )
            response.raise_for_status()
            return response.iter_lines() if stream else response.json()

    def _parse_response(self, content: str) -> list[dict]:
        if not content:
            return []

        # Ensure content is string
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='replace')

        # Try to extract JSON array from response
        try:
            start = content.find("[")
            end = content.rfind("]") + 1
            if start != -1 and end != 0:
                json_str = content[start:end]
                # Parse and verify structure
                parsed = json.loads(json_str)
                if isinstance(parsed, list):
                    # Ensure all fields are proper strings
                    result = []
                    for item in parsed:
                        result.append({
                            "start": float(item.get("start", 0)),
                            "end": float(item.get("end", 0)),
                            "summary": str(item.get("summary", "")),
                            "title": str(item.get("title", ""))
                        })
                    return result
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"JSON parse error: {e}")
            print(f"Content was: {content[:500]}...")

        return []
