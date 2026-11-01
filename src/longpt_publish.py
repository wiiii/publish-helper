#!/usr/bin/env python3
"""Submit a prepared torrent to LongPT's NexusPHP upload form.

Default mode is a dry run. Real publishing requires --submit and LONGPT_COOKIE.
"""

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from src.core.release_metadata import (
    parse_overall_bitrate_mbps,
    parse_video_frame_rate,
    platform_brand_violations,
    section_text,
    split_mediainfo_sections,
)

# 与 longpt-auto-publisher 同名开关：设为 0 可跳过品牌词校验（本地自测用）。
BRAND_TAG_CHECK_ENV = 'LONGPT_BRAND_TAG_CHECK'


def _env_bool(name, default=True):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in ('0', 'false', 'no', 'off')


def enforce_platform_brand_tags(fields):
    """校验副标题/名称里的平台高画质品牌词能否被 MediaInfo 支撑。

    帧绮映画MAX / 臻彩视听 / 帧享 本身在宣称 HDR 体验，SDR 源写上会被站点
    判为「描述与实际不符」。没有 MediaInfo 时视为无法判断，不拦。
    """
    if not _env_bool(BRAND_TAG_CHECK_ENV, True):
        return []
    media_info = get_mediainfo_text(fields)
    if not media_info:
        return []
    violations = []
    for key in ('small_descr', 'name'):
        for problem in platform_brand_violations(fields.get(key), media_info):
            violations.append(f'{key}: {problem}')
    return violations


TYPE_VALUES = {
    '剧集': '402',
    '电视剧': '402',
    '电影': '401',
    '动画': '405',
    '纪录片': '404',
    '综艺': '403',
    '音乐视频': '406',
    '体育': '407',
    '音频': '408',
    '有声书': '410',
}

MEDIUM_VALUES = {
    'WEB-DL': '4',
    'WEB': '4',
    'HDTV': '5',
    'Blu-ray': '1',
    'UHD Blu-ray': '2',
    'Remux': '3',
    'Blu-ray Remux': '3',
    'UHD Blu-ray Remux': '11',
    'DVD': '6',
    'Encode': '7',
}

CODEC_VALUES = {
    'H264': '1',
    'H.264': '1',
    'AVC': '1',
    'H265': '2',
    'H.265': '2',
    'HEVC': '2',
    'VC-1': '3',
    'MPEG-2': '4',
    'AV1': '5',
}

STANDARD_VALUES = {
    '4K': '5',
    '2160p': '5',
    '2160i': '5',
    '8K': '6',
    '4320p': '6',
    '1080p': '2',
    '1080i': '2',
    '720p': '3',
    '720i': '3',
    '480p': '4',
    '480i': '4',
    '2K': '1',
    '1440p': '1',
}

AUDIO_VALUES = {
    'EAC3': '10',
    'E-AC3': '10',
    'DDP': '10',
    'AC3': '15',
    'AAC': '6',
    'FLAC': '1',
    'DTS': '13',
    'DTS-HD MA': '3',
    'DTS:X': '12',
    'TRUEHD': '19',
    'TRUEHD ATMOS': '9',
}

TEAM_VALUES = {
    'LongA': '1',
    'LongWeb': '2',
    'LongPT': '3',
    'WiKi': '4',
    'RL': '6',
    'CMCT': '7',
    'HHWEB': '8',
}

TAG_VALUES = {
    '禁转': '1',
    '英字': '9',
    '首发': '2',
    '官方': '3',
    'DIY': '4',
    '国语': '5',
    '中字': '6',
    'HDR': '7',
    '去广告纯享版': '17',
    '高帧': '16',
    '高码': '15',
    '臻彩MAX': '14',
    '高分': '13',
    '分集': '12',
    '特效': '11',
    '杜比': '10',
    '完结': '8',
}


def extract_mediainfo_from_description(description):
    """Recover MediaInfo when the auto-feed template embedded it in descr."""
    for match in re.finditer(r'\[quote\]\s*(General\b.*?)(?:\[/quote\]|$)', str(description or ''), re.IGNORECASE | re.DOTALL):
        return match.group(1).strip()
    return ''


def strip_mediainfo_from_description(description):
    """Remove embedded MediaInfo quotes from the public description field."""
    text = str(description or '')
    text = re.sub(
        r'\[quote\]\s*General\b.*?\[/quote\]',
        '',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r'\n{3,}',
        '\n\n',
        text,
    )
    return text.strip()


def get_mediainfo_text(fields):
    for name in ('full_mediainfo', 'mediainfo_cmct', 'technical_info'):
        value = str(fields.get(name) or '').strip()
        if value:
            return value
    return extract_mediainfo_from_description(fields.get('descr', ''))


def infer_mediainfo_tags(media_info):
    tags = set()
    sections = split_mediainfo_sections(media_info)
    audio_text = section_text(sections, 'audio')
    text_text = section_text(sections, 'text')
    video_text = section_text(sections, 'general', 'video')

    if re.search(r'Language\s*:\s*.*English|\bEnglish\b|\bSDH\b', text_text, re.IGNORECASE):
        tags.add('英字')
    if re.search(r'Language\s*:\s*.*Chinese|\bChinese\b|Simplified|Traditional|Mandarin|Cantonese|中文|中字|简体|繁体|国语|粤语', text_text, re.IGNORECASE):
        tags.add('中字')
    if re.search(r'Language\s*:\s*.*Chinese|\bMandarin\b|Putonghua|普通话|国语', audio_text, re.IGNORECASE):
        tags.add('国语')
    if re.search(r'Dolby Vision|dvhe|dvh1', video_text, re.IGNORECASE):
        tags.add('杜比')
    if re.search(r'HDR format\s*:\s*\S|Dolby Vision|HDR10|HDR Vivid|\bHLG\b|SMPTE ST 2086|SMPTE ST 2094', video_text, re.IGNORECASE):
        tags.add('HDR')
    if parse_overall_bitrate_mbps(media_info) > 15:
        tags.add('高码')
    if parse_video_frame_rate(media_info) > 30:
        tags.add('高帧')
    return tags


def parse_auto_feed(path):
    text = Path(path).read_text(encoding='utf-8').strip()
    if '#separator#' not in text:
        raise ValueError('auto_feed link does not contain #separator#')

    payload = text.split('#separator#', 1)[1]
    payload += '=' * (-len(payload) % 4)
    decoded = base64.b64decode(payload).decode('utf-8')
    parts = decoded.split('#linkstr#')
    if len(parts) % 2:
        raise ValueError('decoded auto_feed payload has an odd field count')

    fields = {}
    for key, value in zip(parts[0::2], parts[1::2]):
        fields[key] = unquote(value)
    return fields


def load_env_file(path='.env'):
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def first_match(value, mapping, default='0'):
    source = str(value or '').upper()
    for key, mapped in mapping.items():
        if key.upper() in source:
            return mapped
    return default


def infer_tags(fields, extra_tags=None):
    tags = set(extra_tags or [])
    tags.add('官方')
    media_info = get_mediainfo_text(fields)
    if media_info:
        tags.update(infer_mediainfo_tags(media_info))

    return [TAG_VALUES[tag] for tag in TAG_VALUES if tag in tags]


def build_form(fields, tags=None, pos_state='sticky', sticky_days=7):
    brand_violations = enforce_platform_brand_tags(fields)
    if brand_violations:
        raise ValueError(
            '副标题/名称带平台高画质品牌词，但 MediaInfo 不支持'
            '（SDR 源不能标帧绮映画MAX/臻彩视听/帧享）: '
            + '; '.join(brand_violations)
            + f'。确认无误可设置 {BRAND_TAG_CHECK_ENV}=0 跳过校验。'
        )
    category = fields.get('type') or '剧集'
    category_value = first_match(category, TYPE_VALUES)
    if category_value == '0':
        category_value = TYPE_VALUES['剧集']
    group_suffix = '4'
    sticky_until = ''
    if pos_state != 'normal' and sticky_days:
        sticky_until = (datetime.now() + timedelta(days=sticky_days)).strftime('%Y-%m-%d %H:%M')

    technical_info = get_mediainfo_text(fields)
    data = {
        'name': fields.get('name', ''),
        'small_descr': fields.get('small_descr', ''),
        'url': fields.get('url', ''),
        'descr': strip_mediainfo_from_description(fields.get('descr', '')),
        'technical_info': technical_info,
        'type': category_value,
        f'medium_sel[{group_suffix}]': first_match(fields.get('medium_sel'), MEDIUM_VALUES),
        f'codec_sel[{group_suffix}]': first_match(fields.get('codec_sel'), CODEC_VALUES),
        f'standard_sel[{group_suffix}]': first_match(fields.get('standard_sel'), STANDARD_VALUES),
        f'audiocodec_sel[{group_suffix}]': first_match(fields.get('audiocodec_sel'), AUDIO_VALUES),
        f'team_sel[{group_suffix}]': first_match(fields.get('origin_site'), TEAM_VALUES),
        'pos_state': pos_state,
        'pos_state_until': sticky_until,
        'qr': '发布',
    }

    tag_values = infer_tags(fields, tags)
    for idx, value in enumerate(tag_values):
        data[f'tags[{group_suffix}][]#{idx}'] = value

    return data, tag_values


def to_requests_data(data):
    """Keep duplicate checkbox names while retaining normal fields."""
    pairs = []
    for key, value in data.items():
        if '#/' in key:
            key = key.split('#/', 1)[0]
        if '#' in key:
            key = key.split('#', 1)[0]
        pairs.append((key, value))
    return pairs


def submit(action, data, torrent_path, cookie):
    headers = {
        'Cookie': cookie,
        'Referer': 'https://longpt.org/upload.php',
        'User-Agent': 'publish-helper/longpt-auto-publish',
    }
    with open(torrent_path, 'rb') as torrent_file:
        files = {
            'file': (Path(torrent_path).name, torrent_file, 'application/x-bittorrent'),
        }
        response = requests.post(
            action,
            data=to_requests_data(data),
            files=files,
            headers=headers,
            timeout=60,
            allow_redirects=False,
        )
    return response


def main():
    parser = argparse.ArgumentParser(description='Auto publish to LongPT upload form')
    parser.add_argument('--html', default='html/LongPT __ 发布 - Powered by NexusPHP.html')
    parser.add_argument('--auto-feed', default='temp/auto_feed.txt')
    parser.add_argument('--torrent', required=True)
    parser.add_argument('--tag', action='append', default=[], help='Extra tag name, repeatable')
    parser.add_argument('--pos-state', default='sticky', choices=['normal', 'r_sticky', 'sticky'])
    parser.add_argument('--sticky-days', type=int, default=7)
    parser.add_argument('--submit', action='store_true', help='Actually submit to LongPT')
    parser.add_argument('--plan', default='temp/longpt_publish_plan.json')
    args = parser.parse_args()

    load_env_file()

    html = Path(args.html).read_text(encoding='utf-8', errors='ignore')
    action_match = re.search(r'<form[^>]+action="([^"]+)"', html)
    action = action_match.group(1) if action_match else 'https://longpt.org/takeupload.php'

    fields = parse_auto_feed(args.auto_feed)
    data, tag_values = build_form(fields, args.tag, args.pos_state, args.sticky_days)

    plan = {
        'action': action,
        'torrent': str(Path(args.torrent).resolve()),
        'data': data,
        'selected_tag_values': tag_values,
        'selected_tag_names': [name for name, value in TAG_VALUES.items() if value in tag_values],
    }
    Path(args.plan).parent.mkdir(parents=True, exist_ok=True)
    Path(args.plan).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'发布计划已写入: {args.plan}')
    print(json.dumps(plan, ensure_ascii=False, indent=2))

    if not args.submit:
        print('dry-run: 未提交。确认无误后加 --submit，并设置 LONGPT_COOKIE。')
        return 0

    cookie = os.environ.get('LONGPT_COOKIE')
    if not cookie:
        raise SystemExit('缺少 LONGPT_COOKIE，拒绝提交。')

    response = submit(action, data, args.torrent, cookie)
    print(f'HTTP {response.status_code}')
    if response.headers.get('Location'):
        print(f'Location: {response.headers["Location"]}')
    print(response.text[:1000])
    return 0 if response.status_code in {200, 302, 303} else 1


if __name__ == '__main__':
    raise SystemExit(main())
