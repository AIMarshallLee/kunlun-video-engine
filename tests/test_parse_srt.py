"""parse_srt.py 的回归测试：SRT 解析与分镜建议是字幕音画合成的第一步，
本文件作为纯 Python 单测防线，不依赖 ffmpeg 或模型。"""
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import NamedTemporaryFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from parse_srt import group_scenes, main, parse_srt  # noqa: E402

SRT_SAMPLE = """1
00:00:01,000 --> 00:00:03,500
欢迎来到第一幕

2
00:00:03,500 --> 00:00:08,000
这里讲两个要点
第二行也在本条里

3
00:00:08,000 --> 00:00:33,000
第三段持续二十五秒

4
00:00:33,000 --> 00:00:40,000
第四段收尾
"""


class TestParseSrt(unittest.TestCase):

    # 1. 基本解析：字段、毫秒换算、多行合并
    def test_basic_parse(self):
        cues = parse_srt(SRT_SAMPLE)
        self.assertEqual(len(cues), 4)
        self.assertEqual(cues[0]["startMs"], 1000)
        self.assertEqual(cues[0]["endMs"], 3500)
        self.assertEqual(cues[0]["durMs"], 2500)
        self.assertEqual(cues[0]["text"], "欢迎来到第一幕")
        self.assertEqual(cues[1]["text"], "这里讲两个要点 第二行也在本条里")
        self.assertEqual([c["index"] for c in cues], [1, 2, 3, 4])

    # 2. 容错：BOM、CRLF、点毫秒、缺序号、纯噪声块
    def test_tolerant_parsing(self):
        messy = (
            "﻿1\n00:00:01.200 --> 00:00:02.800\n点号毫秒\r\n\r\n"
            "00:00:05,000 --> 00:00:06,000\n没有序号也能解析\r\n\r\n"
            "这不是字幕块，没有时间轴\r\n\r\n"
            "3\n00:00:06,000 --> 00:00:07,000\n第三条"
        )
        cues = parse_srt(messy)
        self.assertEqual(len(cues), 3)
        self.assertEqual(cues[0]["startMs"], 1200)
        self.assertEqual(cues[1]["startMs"], 5000)
        self.assertEqual(cues[2]["text"], "第三条")

    # 3. 空输入返回空列表
    def test_empty_input(self):
        self.assertEqual(parse_srt(""), [])
        self.assertEqual(parse_srt("\n\n  \n"), [])

    # 4. 分幕：落在 min/max 区间内，顺序连续，cueRange 不重不漏
    def test_group_scenes_bounds(self):
        cues = parse_srt(SRT_SAMPLE)
        scenes = group_scenes(cues, target_sec=30, min_sec=25, max_sec=35)
        self.assertEqual(scenes[0]["cueRange"], [1, 3])  # 1s–33s = 32s，达到目标
        self.assertEqual(scenes[1]["cueRange"], [4, 4])
        for s in scenes:
            self.assertLessEqual(s["sceneDurationMs"], 35_000)
        # 幕与幕之间首尾衔接、连续
        for prev, cur in zip(scenes, scenes[1:]):
            self.assertEqual(cur["startMs"], prev["endMs"])
            self.assertEqual(cur["sceneIndex"], prev["sceneIndex"] + 1)

    # 5. 超长字幕强制断幕（span 超 max 先断，不产生超长幕）
    def test_force_break_over_max(self):
        long_cues = [
            {"index": i + 1, "startMs": i * 20_000, "endMs": (i + 1) * 20_000,
             "durMs": 20_000, "text": f"第{i+1}条二十秒"}
            for i in range(4)
        ]
        scenes = group_scenes(long_cues, target_sec=30, min_sec=25, max_sec=35)
        # 两条并一块是 40s > max 35s，所以每幕最多一条
        self.assertTrue(all(s["sceneDurationMs"] <= 35_000 for s in scenes))
        self.assertEqual(len(scenes), 4)

    # 6. CLI：正常文件输出 JSON、退出码 0；空字幕退出码 1
    def test_cli_exit_codes(self):
        with NamedTemporaryFile("w", suffix=".srt", delete=False, encoding="utf-8") as f:
            f.write(SRT_SAMPLE)
            srt_path = f.name
        try:
            buf_out, buf_err = io.StringIO(), io.StringIO()
            with redirect_stdout(buf_out), redirect_stderr(buf_err):
                code = main([srt_path])
            self.assertEqual(code, 0)
            payload = json.loads(buf_out.getvalue())
            self.assertEqual(len(payload["cues"]), 4)
            self.assertGreaterEqual(len(payload["scenes"]), 1)
            self.assertIn("建议场景", buf_err.getvalue())
        finally:
            Path(srt_path).unlink()

        with NamedTemporaryFile("w", suffix=".srt", delete=False, encoding="utf-8") as f:
            f.write("没有时间轴的内容\n")
            empty_path = f.name
        try:
            code = main([empty_path])
            self.assertEqual(code, 1)
        finally:
            Path(empty_path).unlink()


if __name__ == "__main__":
    unittest.main()
