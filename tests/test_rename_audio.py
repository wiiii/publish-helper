"""Tests for audio track selection in src.core.rename."""

from types import SimpleNamespace

from src.core import rename


def test_audio_selection_prioritizes_codec_level_before_channels_and_bitrate():
    audio_tracks = [
        {
            "index": 0,
            "codec": "Dolby Digital Plus",
            "channels": "7.1",
            "bitrate": 1536,
        },
        {
            "index": 1,
            "codec": "Dolby TrueHD",
            "channels": "2.0",
            "bitrate": 640,
        },
    ]

    assert rename._select_best_audio_track(audio_tracks) == (
        "Dolby TrueHD",
        "2.0",
    )


def test_get_video_info_selects_higher_spec_audio_track(tmp_path, monkeypatch):
    video_file = tmp_path / "sample.mkv"
    video_file.write_bytes(b"")

    media_info = SimpleNamespace(
        tracks=[
            SimpleNamespace(
                track_type="General",
                other_frame_rate=["23.976 FPS"],
            ),
            SimpleNamespace(
                track_type="Video",
                other_width=["1 920 pixels"],
                other_height=["1 080 pixels"],
                other_format=["HEVC"],
                other_hdr_format=[],
                other_bit_depth=["10 bits"],
                writing_library="",
            ),
            SimpleNamespace(
                track_type="Audio",
                commercial_name="AAC",
                channel_layout="L R",
                other_language="English",
                bit_rate="128 kb/s",
            ),
            SimpleNamespace(
                track_type="Audio",
                commercial_name="Dolby Digital Plus",
                channel_layout="L R C LFE Ls Rs",
                other_language="English",
                bit_rate="640 kb/s",
            ),
        ],
        to_json=lambda: "{}",
    )
    monkeypatch.setattr(rename.MediaInfo, "parse", lambda _: media_info)

    abbreviations = {
        "1 920 pixels": "1080p",
        "HEVC": "H265",
        "10 bits": "10bit",
        "23.976 FPS": "",
        "Dolby Digital Plus": "DDP",
        "L R C LFE Ls Rs": "5.1",
        "Audio": "Audio",
    }
    monkeypatch.setattr(
        rename,
        "get_abbreviation",
        lambda original_name: abbreviations.get(original_name, original_name),
    )

    success, result = rename.get_video_info(str(video_file))

    assert success is True
    assert result[5] == "DDP"
    assert result[6] == "5.1"
    assert result[7] == "2Audio"
