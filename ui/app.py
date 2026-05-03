#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UI Program for displaying and selecting emotional segments.
"""

import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
os.environ['PYTHONIOENCODING'] = 'utf-8'

import tkinter as tk
from tkinter import ttk, messagebox
import json
import httpx


class SegmentApp:
    def __init__(self, mcp_url: str = "http://127.0.0.1:8765"):
        self.mcp_url = mcp_url
        self.segments: list[dict] = []
        self.selected_ids: set[str] = set()

        self.root = tk.Tk()
        self.root.title("情绪片段选择器")
        self.root.geometry("900x700")

        # Configure style for CJK font
        style = ttk.Style()
        # Try available fonts that support Chinese
        font_names = ["Microsoft YaHei", "SimHei", "PingFang SC", "WenQuanYi Micro Hei", "Noto Sans CJK SC"]
        available_fonts = list(set(font_names) & set(self.root.tk.call("font", "names")))

        if available_fonts:
            font_name = available_fonts[0]
        else:
            # Default sans-serif which usually has CJK support on Windows
            font_name = "TkDefaultFont"

        style.configure("Treeview", font=(font_name, 10))
        style.configure("Treeview.Heading", font=(font_name, 10, "bold"))
        style.configure("TLabel", font=(font_name, 10))
        style.configure("TButton", font=(font_name, 10))

        self._setup_ui()
        self._refresh_segments()

    def _setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            header_frame,
            text="情绪片段列表",
            font=("Microsoft YaHei", 16, "bold")
        ).pack(side=tk.LEFT)

        ttk.Button(
            header_frame,
            text="刷新",
            command=self._refresh_segments
        ).pack(side=tk.RIGHT)

        # Segment list
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        columns = ("selected", "title", "time", "summary")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)

        self.tree.heading("selected", text="选择")
        self.tree.heading("title", text="标题")
        self.tree.heading("time", text="时间段")
        self.tree.heading("summary", text="内容摘要")

        self.tree.column("selected", width=60, anchor="center")
        self.tree.column("title", width=200)
        self.tree.column("time", width=150)
        self.tree.column("summary", width=450)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-Button-1>", self._on_segment_click)

        # Status bar
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=(0, 10))

        self.status_label = ttk.Label(status_frame, text="就绪")
        self.status_label.pack(side=tk.LEFT)

        self.count_label = ttk.Label(status_frame, text="共 0 个片段，已选择 0 个")
        self.count_label.pack(side=tk.RIGHT)

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)

        ttk.Button(button_frame, text="全选", command=self._select_all).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="取消全选", command=self._deselect_all).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="删除选中", command=self._delete_selected).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="确认选择", command=self._confirm_selection).pack(side=tk.RIGHT)

    def _refresh_segments(self):
        try:
            response = httpx.get(f"{self.mcp_url}/segments", timeout=5.0)
            response.raise_for_status()
            # Ensure proper UTF-8 decoding
            raw_content = response.content
            text = raw_content.decode('utf-8', errors='replace')
            data = json.loads(text)
            self.segments = data.get("segments", [])
            self.selected_ids = {s["id"] for s in self.segments if s.get("selected")}
            self._update_display()
            self.status_label.config(text="已刷新")
        except Exception as e:
            self.status_label.config(text=f"刷新失败: {str(e)}")

    def _update_display(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for seg in self.segments:
            time_str = f"{self._format_time(seg['start'])} - {self._format_time(seg['end'])}"
            selected_mark = "✓" if seg["id"] in self.selected_ids else ""
            # Ensure proper string conversion
            title = str(seg.get("title", ""))
            summary = str(seg.get("summary", ""))
            self.tree.insert("", tk.END, values=(
                selected_mark,
                title,
                time_str,
                summary
            ), tags=(seg["id"],))

        self.count_label.config(
            text=f"共 {len(self.segments)} 个片段，已选择 {len(self.selected_ids)} 个"
        )

    def _format_time(self, seconds: float) -> str:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    def _on_segment_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return

        segment_id = self.tree.item(item_id, "tags")[0]

        try:
            httpx.patch(f"{self.mcp_url}/segments/toggle?id={segment_id}", timeout=5.0)
            self._refresh_segments()
        except Exception as e:
            self.status_label.config(text=f"切换选择失败: {str(e)}")

    def _select_all(self):
        for seg in self.segments:
            if seg["id"] not in self.selected_ids:
                try:
                    httpx.patch(f"{self.mcp_url}/segments/toggle?id={seg['id']}", timeout=5.0)
                except:
                    pass
        self._refresh_segments()

    def _deselect_all(self):
        for seg in self.segments:
            if seg["id"] in self.selected_ids:
                try:
                    httpx.patch(f"{self.mcp_url}/segments/toggle?id={seg['id']}", timeout=5.0)
                except:
                    pass
        self._refresh_segments()

    def _delete_selected(self):
        if not self.selected_ids:
            messagebox.showwarning("警告", "请先选择要删除的片段")
            return

        if not messagebox.askyesno("确认", f"确定删除选中的 {len(self.selected_ids)} 个片段？"):
            return

        for segment_id in list(self.selected_ids):
            try:
                httpx.delete(f"{self.mcp_url}/segments?id={segment_id}", timeout=5.0)
            except:
                pass

        self._refresh_segments()

    def _confirm_selection(self):
        if not self.selected_ids:
            messagebox.showwarning("警告", "请至少选择一个片段")
            return

        try:
            response = httpx.post(f"{self.mcp_url}/submit", timeout=5.0)
            response.raise_for_status()
            data = response.json()

            if data.get("submitted"):
                messagebox.showinfo("成功", f"已确认选择 {data.get('count', 0)} 个片段\n\n片段信息已准备好，可用于FFmpeg剪辑")
                self.status_label.config(text="已确认选择")
        except Exception as e:
            self.status_label.config(text=f"确认失败: {str(e)}")
            messagebox.showerror("错误", f"确认选择失败: {str(e)}")

    def run(self):
        self.root.mainloop()


def main():
    mcp_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
    app = SegmentApp(mcp_url)
    app.run()


if __name__ == "__main__":
    main()
