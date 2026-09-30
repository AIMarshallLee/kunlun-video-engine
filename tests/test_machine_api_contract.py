from webapp.machine_api import VideoJobRequest


def test_machine_api_defaults() -> None:
    payload = VideoJobRequest(script="这是一段用于测试昆仑视频引擎机器接口的完整中文脚本。", voice_id="voice-demo")
    assert payload.aspect_ratio == "9:16"
    assert payload.mode == "infographic"
    assert payload.style == "极简商务涂鸦风"
    assert payload.pen_text == "昆仑增长"


def test_machine_api_accepts_metadata() -> None:
    payload = VideoJobRequest(
        script="这是一段用于测试上游内容工作台元数据透传的完整中文脚本。",
        voice_id="voice-demo",
        metadata={"source": "kunlun-content-workbench", "content_id": "demo-001"},
    )
    assert payload.metadata["source"] == "kunlun-content-workbench"
