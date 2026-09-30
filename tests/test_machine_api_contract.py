from webapp.machine_api import KUNLUN_PRESETS, VideoJobRequest


def test_machine_api_defaults() -> None:
    payload = VideoJobRequest(script="这是一段用于测试昆仑视频引擎机器接口的完整中文脚本。", voice_id="voice-demo")
    assert payload.preset == "short-video"
    assert payload.aspect_ratio is None
    assert payload.mode is None
    assert payload.style is None
    assert KUNLUN_PRESETS[payload.preset]["aspect_ratio"] == "9:16"


def test_machine_api_accepts_metadata() -> None:
    payload = VideoJobRequest(
        script="这是一段用于测试上游内容工作台元数据透传的完整中文脚本。",
        voice_id="voice-demo",
        metadata={"source": "kunlun-content-workbench", "content_id": "demo-001"},
    )
    assert payload.metadata["source"] == "kunlun-content-workbench"


def test_kunlun_presets_are_machine_safe() -> None:
    assert KUNLUN_PRESETS["short-video"]["aspect_ratio"] == "9:16"
    assert KUNLUN_PRESETS["business-explainer"]["aspect_ratio"] == "16:9"
    assert KUNLUN_PRESETS["high-impact"]["mode"] == "standard"
    for preset in KUNLUN_PRESETS.values():
        assert preset["aspect_ratio"] in {"9:16", "16:9", "1:1"}
        assert preset["mode"] in {"standard", "infographic"}
        assert 1 <= preset["scenes_per_image"] <= 4
