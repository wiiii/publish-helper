from pathlib import Path

from auto_publish import (
    AutoPublishConfig,
    add_auto_publish_notice,
    build_vt_download_command,
    load_auto_list,
    parse_auto_list_line,
    select_vt_options,
)


def test_add_auto_publish_notice_prepends_styled_quote():
    description = "body"

    result = add_auto_publish_notice(description)

    assert result.startswith("[quote]")
    assert "LongPT 自动发种机发布" in result
    assert "如有错误请联系管理修改。" in result
    assert "[align=center]" not in result
    assert result.endswith("body")


def test_add_auto_publish_notice_is_idempotent():
    description = add_auto_publish_notice("body")

    assert add_auto_publish_notice(description) == description


def test_parse_auto_list_tv_pipe_line():
    item = parse_auto_list_line(
        "tv|S01|DisneyPlus|https://example.test/show|韩国剧名",
        default_service="DisneyPlus",
    )

    assert item["kind"] == "tv"
    assert item["season"] == "S01"
    assert item["service"] == "DisneyPlus"
    assert item["url"] == "https://example.test/show"
    assert item["title"] == "韩国剧名"
    assert item["korean"] is True


def test_load_auto_list_deduplicates_urls(tmp_path):
    auto_list = tmp_path / "auto_list.txt"
    auto_list.write_text(
        "movie|DisneyPlus|https://example.test/movie|Movie\n"
        "movie|DisneyPlus|https://example.test/movie|Movie\n",
        encoding="utf-8",
    )

    assert len(load_auto_list(auto_list, "DisneyPlus")) == 1


def test_select_vt_options_prefers_2160_dv_hdr():
    options = select_vt_options("1080p SDR\n2160p Dolby Vision HDR10", 2160)

    assert options == {"quality": 2160, "dynamic_range": "dv+hdr"}


def test_select_vt_options_falls_back_to_1080_hdr():
    options = select_vt_options("1080p HDR10", 2160)

    assert options == {"quality": 1080, "dynamic_range": "hdr"}


def test_build_vt_movie_command_matches_requested_shape():
    config = AutoPublishConfig(media_root=Path("media"))
    item = {
        "kind": "movie",
        "service": "DisneyPlus",
        "url": "https://example.test/movie",
        "title": "Movie",
    }

    command = build_vt_download_command(
        config,
        item,
        {"quality": 2160, "dynamic_range": "dv+hdr"},
    )

    assert command == [
        "poetry", "run", "vt", "dl",
        "-q", "2160",
        "-r", "dv+hdr",
        "-v", "h265",
        "-sl", "zh-Hans,zh-HK,en",
        "-al", "en,zh",
        "DisneyPlus",
        "-m",
        "https://example.test/movie",
    ]


def test_build_vt_tv_command_adds_korean_languages():
    config = AutoPublishConfig(media_root=Path("media"))
    item = {
        "kind": "tv",
        "season": "S01",
        "service": "DisneyPlus",
        "url": "https://example.test/show",
        "title": "韩国剧集",
    }

    command = build_vt_download_command(
        config,
        item,
        {"quality": 1080, "dynamic_range": "hdr"},
    )

    assert command == [
        "poetry", "run", "vt", "dl",
        "-q", "1080",
        "-r", "hdr",
        "-v", "h265",
        "-sl", "zh-Hans,zh-HK,en,ko",
        "-al", "en,zh,ko",
        "-w", "S01",
        "DisneyPlus",
        "https://example.test/show",
    ]
