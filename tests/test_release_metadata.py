from types import SimpleNamespace

import pytest

from src.core import rename
from src.core.platforms import normalize_platform_source
from src.core.release_metadata import (
    append_quality_note,
    has_platform_brand_tag,
    normalize_hdr_format,
    parse_overall_bitrate_mbps,
    parse_video_frame_rate,
    platform_brand_tier,
    platform_brand_violations,
    resolution_from_dimensions,
)


HIGH_SDR_MEDIAINFO = '''General
Complete name : C:/HDR10/Tencent/movie.mkv
Overall bit rate : 20.8 Mb/s

Video
Format : HEVC
Width : 3 840 pixels
Height : 1 608 pixels
Transfer characteristics : BT.709
Frame rate : 23.976 (24000/1001) FPS

Audio #1
Format : E-AC-3
Frame rate : 187.500 FPS
Title : HDR10 Atmos
'''
HIGH_HDR_MEDIAINFO = HIGH_SDR_MEDIAINFO.replace(
    'Transfer characteristics : BT.709',
    'Transfer characteristics : PQ\nHDR format : SMPTE ST 2086, HDR10 compatible',
)


@pytest.mark.parametrize('platform, source, expected', [
    ('iQIYI', 'IQY WEB-DL', 'WEB-DL'),
    ('Tencent', 'TX.WEB-DL', 'WEB-DL'),
    ('Tencent', 'TX_WEB-DL', 'WEB-DL'),
    ('腾讯', 'Tencent WEB-DL', 'WEB-DL'),
    ('YouKu', 'YK WEB-DL', 'WEB-DL'),
    ('YouKu', 'Youku.WEB-DL', 'WEB-DL'),
    ('Bilibili', 'BILI WEB-DL', 'WEB-DL'),
    ('NF', 'DSNP WEB-DL', 'WEB-DL'),
    ('NF', 'DSNP_WEB_DL', 'WEB-DL'),
    ('AMZN', 'Amazon WEBRip', 'WEBRip'),
    ('iQIYI', 'IQY', 'WEB-DL'),
    ('Tencent', '', 'WEB-DL'),
    ('NF', 'Blu-ray Remux', 'Blu-ray Remux'),
    ('', 'DSNP WEB-DL', 'DSNP WEB-DL'),
])
def test_platform_source_normalization(tmp_path, monkeypatch, platform, source, expected):
    monkeypatch.chdir(tmp_path)
    assert normalize_platform_source(platform, source) == expected


@pytest.mark.parametrize('raw, expected', [
    ('Dolby Vision, dvhe.05.03, BL+RPU / SMPTE ST 2086, HDR10 compatible', 'DV HDR10 Hybrid'),
    ('Dolby.Vision,.dvhe.05.06,.SMPTE.ST.2094.App.4,.HDR10+.Profile.A.compatible', 'DV HDR10+ Hybrid'),
    ('Dolby Vision, dvhe.05.03, BL+RPU', 'DV'),
    ('SMPTE ST 2094 App 4, HDR10+ Profile B compatible', 'HDR10+'),
    ('SMPTE ST 2086, HDR10 compatible', 'HDR10'),
    ('HDR Vivid, Version 1', 'HDR'), ('HLG', 'HLG'),
    ('', ''), ('SDR', ''), ('Unknown HDR format', None),
])
def test_dynamic_hdr_formats(raw, expected):
    assert normalize_hdr_format(raw) == expected


def test_sdr_transfer_overrides_stale_hdr_mastering_information():
    assert normalize_hdr_format('SMPTE ST 2086, HDR10 compatible', 'BT.709') == ''
    assert normalize_hdr_format('', 'ARIB STD-B67 (HLG)') == 'HLG'


@pytest.mark.parametrize('width, height, expected', [
    (3840, 1608, '2160p'), (4096, 1716, '2160p'),
    (2840, 2160, '2160p'), (1920, 800, '1080p'),
    (0, 1080, '1080p'), (0, 0, ''),
])
def test_cropped_and_narrow_video_resolutions(width, height, expected):
    assert resolution_from_dimensions(width, height) == expected


@pytest.mark.parametrize('platform, media_info, expected', [
    ('iQIYI', HIGH_HDR_MEDIAINFO, 'iQIYI【帧绮映画MAX】4K 20.8Mbps'),
    ('Tencent', HIGH_HDR_MEDIAINFO, 'Tencent【臻彩视听】4K 20.8Mbps'),
    ('优酷', HIGH_SDR_MEDIAINFO, 'YouKu【帧享影院】4K 20.8Mbps'),
    ('iQIYI', HIGH_SDR_MEDIAINFO, 'iQIYI4K高码率 20.8Mbps'),
    ('Tencent', HIGH_SDR_MEDIAINFO, 'Tencent4K高码率 20.8Mbps'),
    ('Netflix', HIGH_HDR_MEDIAINFO, 'NF4K高码率 20.8Mbps'),
    ('Bilibili', HIGH_HDR_MEDIAINFO, 'Bilibili4K高码率 20.8Mbps'),
    ('', HIGH_SDR_MEDIAINFO, '4K高码率 20.8Mbps'),
])
def test_platform_quality_notes(tmp_path, monkeypatch, platform, media_info, expected):
    monkeypatch.chdir(tmp_path)
    assert append_quality_note('标题', media_info=media_info, platform=platform) == '标题 | ' + expected


def test_quality_thresholds_and_no_media_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert append_quality_note('标题', media_info=HIGH_SDR_MEDIAINFO.replace('20.8 Mb/s', '10.5 Mb/s'), platform='YouKu') == '标题'
    assert append_quality_note('标题', platform='iQIYI') == '标题'
    media_info = HIGH_SDR_MEDIAINFO.replace('3 840 pixels', '1 920 pixels').replace('1 608 pixels', '1 080 pixels')
    assert append_quality_note('', media_info=media_info, platform='YouKu') == 'YouKu1080P高码率 20.8Mbps'


def test_explicit_quality_is_checked_and_notes_are_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    note = append_quality_note('标题', 'iQIYI帧绮映画MAX 4K', HIGH_SDR_MEDIAINFO, 'iQIYI')
    assert note == '标题 | iQIYI4K高码率 20.8Mbps'
    assert append_quality_note(note, media_info=HIGH_SDR_MEDIAINFO, platform='iQIYI') == note
    assert append_quality_note('标题', '优酷帧享120帧', HIGH_HDR_MEDIAINFO, 'YouKu') == '标题 | YouKu【帧享影院】4K 20.8Mbps'


@pytest.mark.parametrize('bitrate', ['20.8 Mb/s', '20 800 kb/s', '20,800,000 bps', '0.0208 Gb/s'])
def test_bitrate_units_and_audio_frame_rate(bitrate):
    media_info = HIGH_SDR_MEDIAINFO.replace('20.8 Mb/s', bitrate)
    assert parse_overall_bitrate_mbps(media_info) == pytest.approx(20.8)
    assert parse_video_frame_rate(media_info) == pytest.approx(23.976)


def test_mediainfo_scalar_fields_and_missing_optional_attributes(tmp_path, monkeypatch):
    video = tmp_path / 'example.mkv'
    video.write_bytes(b'video')
    media_info = SimpleNamespace(tracks=[
        SimpleNamespace(track_type='Video', width=3840, height=1608, format='HEVC',
                        other_hdr_format='Dolby Vision, dvhe.05.03, BL+RPU / HDR10 compatible',
                        other_frame_rate='60.000 FPS'),
        SimpleNamespace(track_type='Audio', format='AAC', other_language=['English']),
    ], to_json=lambda: '{}')
    monkeypatch.setattr(rename.MediaInfo, 'parse', lambda *args: media_info)
    monkeypatch.setattr(rename, 'get_abbreviation', lambda value: value)
    success, info = rename.get_video_info(str(video))
    assert success
    assert info[0] == '2160p'
    assert info[3] == 'DV HDR10 Hybrid'
    assert info[4] == '60.000 FPS'
    assert '英语' in info[8]


def test_unknown_hdr_does_not_become_a_filename(tmp_path, monkeypatch):
    video = tmp_path / 'example.mkv'
    video.write_bytes(b'video')
    media_info = SimpleNamespace(tracks=[SimpleNamespace(
        track_type='Video', width=3840, height=2160, hdr_format='Unmapped HDR format',
    )], to_json=lambda: '{}')
    monkeypatch.setattr(rename.MediaInfo, 'parse', lambda *args: media_info)
    monkeypatch.setattr(rename, 'get_abbreviation', lambda value: value)
    success, info = rename.get_video_info(str(video))
    assert not success
    assert 'HDR格式未映射' in info[0]


def test_publish_title_separators_keep_codec_and_channels(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(rename, 'get_settings', lambda key: '{en_title}.{platform}.{source}.{video_codec}.{channels}')
    result = rename.get_name_from_template(
        'Example.Title', '', '', '', '2026', '2160p', 'TX WEB-DL', 'H.265',
        '', '', '', '', '5.1', '', '', '', '', '', '', '', '', 'main_title_movie', platform='Tencent',
    )
    assert result == 'Example Title Tencent WEB-DL H.265 5.1'


def test_brand_tags_require_hdr_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # HDR 限定品牌词：SDR 源判违规，HDR 源放行
    assert platform_brand_violations('【臻彩视听】4K', HIGH_SDR_MEDIAINFO)
    assert platform_brand_violations('【臻彩视听】4K', HIGH_HDR_MEDIAINFO) == []
    assert platform_brand_violations('iQIYI【帧绮映画MAX】4K', HIGH_SDR_MEDIAINFO)
    # 帧享影院是入口档位（也提供 SDR 高码率），不算 HDR 宣称
    assert platform_brand_violations('【帧享影院】4K', HIGH_SDR_MEDIAINFO) == []
    assert has_platform_brand_tag('【帧享影院】4K') is False
    assert has_platform_brand_tag('【臻彩视听】4K') is True


def test_frame_120_needs_100fps(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 同一份 HDR 媒资，帧率 23.976，低于 120 帧档要求
    assert platform_brand_violations('帧享 120 帧', HIGH_HDR_MEDIAINFO)
    high_fps = HIGH_HDR_MEDIAINFO.replace('23.976 (24000/1001) FPS', '120.000 FPS')
    assert platform_brand_violations('帧享 120 帧', high_fps) == []


def test_platform_brand_tier_follows_media_info(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert platform_brand_tier('iQIYI', HIGH_HDR_MEDIAINFO) == '帧绮映画MAX'
    assert platform_brand_tier('iQIYI', HIGH_SDR_MEDIAINFO) == ''
    assert platform_brand_tier('腾讯', HIGH_HDR_MEDIAINFO) == '臻彩视听'
    assert platform_brand_tier('优酷', HIGH_SDR_MEDIAINFO) == '帧享影院'
    assert platform_brand_tier('NF', HIGH_HDR_MEDIAINFO) == ''
