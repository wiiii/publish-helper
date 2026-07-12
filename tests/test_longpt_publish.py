from src.longpt_publish import (
    TAG_VALUES,
    build_form,
    extract_mediainfo_from_description,
    infer_tags,
    parse_overall_bitrate_mbps,
    parse_video_frame_rate,
    strip_mediainfo_from_description,
)


MEDIAINFO = """General
Overall bit rate                    : 16.2 Mb/s
Frame rate                          : 23.976 FPS

Video
HDR format                          : SMPTE ST 2086, HDR10 compatible
Frame rate mode                     : Constant
Frame rate                          : 23.976 (24000/1001) FPS

Audio #1
Format                              : E-AC-3
Commercial name                     : Dolby Digital Plus
Frame rate                          : 31.250 FPS (1536 SPF)
Language                            : Chinese

Text #1
Title                               : Simplified
Language                            : Chinese (Simplified)

Text #2
Title                               : SDH
Language                            : English
"""


def test_extracts_mediainfo_from_description_quote():
    description = f"[quote]signature[/quote]\nbody\n[quote]{MEDIAINFO}[/quote]"

    assert extract_mediainfo_from_description(description).startswith("General")


def test_build_form_uses_description_mediainfo_as_technical_info():
    data, _tags = build_form({"descr": f"description[quote]{MEDIAINFO}[/quote]"})

    assert data["technical_info"].startswith("General")
    assert data["descr"] == "description"


def test_strip_mediainfo_removes_only_general_quote():
    description = f"[quote]signature[/quote]\nbody\n[quote]{MEDIAINFO}[/quote]"

    result = strip_mediainfo_from_description(description)

    assert "[quote]signature[/quote]" in result
    assert "body" in result
    assert "Overall bit rate" not in result


def test_infers_required_tags_from_mediainfo():
    values = set(infer_tags({"descr": f"[quote]{MEDIAINFO}[/quote]"}))

    assert TAG_VALUES["官方"] in values
    assert TAG_VALUES["英字"] in values
    assert TAG_VALUES["中字"] in values
    assert TAG_VALUES["国语"] in values
    assert TAG_VALUES["杜比"] not in values
    assert TAG_VALUES["HDR"] in values
    assert TAG_VALUES["高码"] in values
    assert TAG_VALUES["高帧"] not in values


def test_dolby_tag_requires_dolby_vision_video():
    media_info = MEDIAINFO.replace(
        "HDR format                          : SMPTE ST 2086, HDR10 compatible",
        "HDR format                          : Dolby Vision, Version 1.0, dvhe.05.06",
    )

    assert TAG_VALUES["杜比"] in set(infer_tags({"technical_info": media_info}))


def test_video_frame_rate_ignores_audio_frame_rate():
    assert parse_video_frame_rate(MEDIAINFO) == 23.976


def test_high_frame_detects_video_frame_rate_above_30fps():
    media_info = MEDIAINFO.replace("Frame rate                          : 23.976 (24000/1001) FPS", "Frame rate                          : 59.940 FPS")

    assert parse_video_frame_rate(media_info) == 59.94
    assert TAG_VALUES["高帧"] in set(infer_tags({"technical_info": media_info}))


def test_overall_bitrate_parses_kbps_and_mbps():
    assert parse_overall_bitrate_mbps("Overall bit rate                    : 6 821 kb/s") == 6.821
    assert parse_overall_bitrate_mbps("Overall bit rate                    : 16.2 Mb/s") == 16.2
