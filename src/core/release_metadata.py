import re

from src.core.platforms import get_platform


def split_mediainfo_sections(media_info):
    sections = []
    current = ''
    lines = []
    for line in str(media_info or '').splitlines():
        heading = re.fullmatch(r'(General|Video|Audio|Text|Menu)(?:\s*#\d+)?', line.strip(), re.IGNORECASE)
        if heading:
            if current:
                sections.append((current, '\n'.join(lines)))
            current = heading.group(1).lower()
            lines = [line]
        elif current:
            lines.append(line)
    if current:
        sections.append((current, '\n'.join(lines)))
    return sections


def section_text(sections, *names):
    return '\n'.join(text for name, text in sections if name in names)


def parse_overall_bitrate_mbps(media_info):
    sections = split_mediainfo_sections(media_info)
    general = section_text(sections, 'general') if sections else str(media_info or '')
    pattern = r'^\s*Overall bit rate\s*:\s*([\d][\d ,.]*?)\s*([kmg]?)(?:b/s|bps)\b'
    values = []
    for value, prefix in re.findall(pattern, general, re.IGNORECASE | re.MULTILINE):
        number = float(value.replace(' ', '').replace(',', ''))
        values.append(number * {'': 0.000001, 'k': 0.001, 'm': 1, 'g': 1000}[prefix.lower()])
    return max(values, default=0.0)


def parse_video_frame_rate(media_info):
    text = section_text(split_mediainfo_sections(media_info), 'video', 'general')
    values = re.findall(r'^\s*Frame rate\s*:\s*([\d.]+)(?:\s*\([^\n]*?\))?\s*FPS\b', text, re.IGNORECASE | re.MULTILINE)
    return max((float(value) for value in values), default=0.0)


def pixel_number(value):
    match = re.search(r'\d+', str(value or '').replace(' ', '').replace(',', ''))
    return int(match.group()) if match else 0


def resolution_from_dimensions(width, height):
    width, height = pixel_number(width), pixel_number(height)
    if not width and not height:
        return ''
    use_width = bool(width)
    if width and height:
        long_edge, short_edge = max(width, height), min(width, height)
        use_width = long_edge / short_edge >= 1.5
        value = long_edge if use_width else short_edge
    else:
        value = width or height
    thresholds = (
        (4608 if use_width else 4000, '4320p'),
        (3200 if use_width else 2000, '2160p'),
        (2240 if use_width else 1400, '1440p'),
        (1600 if use_width else 1000, '1080p'),
        (900 if use_width else 700, '720p'),
        (533 if use_width else 400, '480p'),
    )
    return next((label for minimum, label in thresholds if value >= minimum), '480p')


def normalize_hdr_format(hdr_format, transfer=''):
    raw = str(hdr_format or '').strip()
    value = raw.replace('.', ' ').lower()
    transfer = str(transfer or '').lower()
    if re.search(r'bt\.?\s*709|bt\.?\s*601|\bsdr\b', transfer):
        return ''
    dolby = bool(re.search(r'dolby\s*vision|dvhe|dvh1|\bdv\b', value))
    hdr_plus = bool(re.search(r'hdr10\+|smpte\s*st\s*2094', value))
    hdr10 = bool(re.search(r'hdr10|smpte\s*st\s*2086', value))
    if dolby and hdr_plus:
        return 'DV HDR10+ Hybrid'
    if dolby and hdr10:
        return 'DV HDR10 Hybrid'
    if dolby:
        return 'DV'
    if hdr_plus:
        return 'HDR10+'
    if hdr10:
        return 'HDR10'
    if 'hdr vivid' in value or value == 'hdr':
        return 'HDR'
    if re.search(r'\bhlg\b|arib\s*std.?b67', value + ' ' + transfer):
        return 'HLG'
    if re.search(r'\bpq\b|smpte\s*st\s*2084', transfer):
        return 'HDR10'
    return '' if not raw or value == 'sdr' else None


def _video_fields(media_info):
    sections = split_mediainfo_sections(media_info)
    video = next((text for name, text in sections if name == 'video'), '')
    return {
        key.strip().lower(): value.strip()
        for key, value in re.findall(r'^\s*([^:\n]+):\s*([^\n]*)', video, re.MULTILINE)
    }


def _has_hdr(fields):
    transfer = fields.get('transfer characteristics', '')
    hdr = normalize_hdr_format(fields.get('hdr format', ''), transfer)
    if hdr == 'HDR10' and not transfer:
        return False
    return bool(hdr)


# ---------------------------------------------------------------------------
# 平台高画质品牌词规则（与 longpt-auto-publisher 保持同一套）
#
# 这些品牌名本身就是在宣称 HDR 体验，MediaInfo 必须能证明；
# 否则副标题与实际画质不符，站点会以「描述与实际不符」拒种。
# SDR 源命中 HDR 限定品牌词即判为违规，由调用方决定提示还是阻断。
PLATFORM_BRAND_TAG_RULES = (
    {
        'label': '爱奇艺帧绮映画MAX/4K MAX+',
        'pattern': r'帧绮映画|4K\s*MAX\s*\+',
        'require_hdr': True,
    },
    {
        'label': '腾讯臻彩视听/臻彩MAX',
        'pattern': r'臻彩(?:视听|MAX)?',
        'require_hdr': True,
    },
    {
        # 帧享(影音/4K) 是 HDR 品牌标准，但「帧享影院」是酷喵 TV 的入口档位，
        # 同样提供 SDR 高码率流——入口名只是来源说明，不是 HDR 宣称，豁免。
        'label': '优酷帧享',
        'pattern': r'帧享(?!影院)(?:影音|4K)?',
        'require_hdr': True,
    },
    {
        'label': '优酷帧享120帧',
        'pattern': r'帧享\s*120\s*帧',
        'require_hdr': True,
        'require_fps_min': 100,
    },
)

# 高码率档位的平台专属品牌词：'hdr' 供真 HDR 源使用，'sdr' 供 SDR 高码率源使用。
# 键为平台规范名的小写形式，中文别名经 get_platform 归一后同样命中。
PLATFORM_BRAND_TIERS = {
    'iqiyi': {'hdr': '帧绮映画MAX', 'sdr': ''},
    'tencent': {'hdr': '臻彩视听', 'sdr': ''},
    'youku': {'hdr': '帧享影院', 'sdr': '帧享影院'},
}


def media_info_has_hdr(media_info):
    """MediaInfo 能否证明画面属于 HDR 家族（含纯 Dolby Vision）。"""
    fields = _video_fields(media_info)
    if not fields:
        return False
    return _has_hdr(fields)


def has_platform_brand_tag(text):
    """文本里是否出现平台高画质品牌词（用于决定要不要去解析 MediaInfo）。"""
    value = str(text or '')
    return any(
        re.search(rule['pattern'], value, re.IGNORECASE)
        for rule in PLATFORM_BRAND_TAG_RULES
    )


def platform_brand_violations(text, media_info=''):
    """返回品牌词与媒资不符的说明列表，空列表表示没问题。"""
    value = str(text or '')
    if not value:
        return []
    hdr_ok = media_info_has_hdr(media_info)
    frame_rate = parse_video_frame_rate(media_info) if media_info else 0.0
    problems = []
    for rule in PLATFORM_BRAND_TAG_RULES:
        if not re.search(rule['pattern'], value, re.IGNORECASE):
            continue
        if rule.get('require_hdr') and not hdr_ok:
            problems.append(
                f'{rule["label"]} 要求真 HDR 源（Dolby Vision / HDR10 / HDR10+ / HLG / HDR Vivid），'
                '但 MediaInfo 显示 SDR 或没有 HDR 证据'
            )
        min_fps = rule.get('require_fps_min')
        if min_fps and (not frame_rate or frame_rate + 1e-6 < min_fps):
            problems.append(
                f'{rule["label"]} 要求帧率不低于 {min_fps} fps，'
                f'MediaInfo 帧率为 {frame_rate or "未知"}'
            )
    return problems


def platform_brand_tier(platform_label, media_info=''):
    """返回该平台高码率档位可用的品牌词，没有或撑不住时返回空串。"""
    label = get_platform(platform_label)[0] or str(platform_label or '').strip()
    tiers = PLATFORM_BRAND_TIERS.get(label.strip().casefold())
    if not tiers:
        return ''
    brand = tiers.get('hdr' if media_info_has_hdr(media_info) else 'sdr') or ''
    if brand and platform_brand_violations(brand, media_info):
        return ''
    return brand


def _valid_quality_summary(summary, media_info):
    return not platform_brand_violations(summary, media_info)


def append_quality_note(second_title, quality_summary='', media_info='', platform=''):
    title = str(second_title or '')
    label = get_platform(platform)[0]
    fields = _video_fields(media_info)
    explicit = str(quality_summary or '').strip()
    note = explicit if _valid_quality_summary(explicit, media_info) else ''
    resolution = resolution_from_dimensions(fields.get('width', ''), fields.get('height', ''))
    bitrate = parse_overall_bitrate_mbps(media_info)
    fallback = ''
    if (resolution == '2160p' and bitrate >= 12) or (resolution == '1080p' and bitrate >= 8):
        brand = platform_brand_tier(label, media_info) if resolution == '2160p' else ''
        speed = f'{bitrate:.1f}'.rstrip('0').rstrip('.')
        quality = f'【{brand}】4K' if brand else ('4K高码率' if resolution == '2160p' else '1080P高码率')
        fallback = f'{label}{quality} {speed}Mbps'
    brand_pattern = r'帧享影院|帧享\s*120\s*帧|帧享|帧绮映画(?:MAX)?|臻彩(?:视听|MAX)?|4K\s*MAX\s*\+'
    if not note or (fallback and not re.search(brand_pattern, note) and '【' in fallback):
        note = fallback
    if note and '【' not in note:
        note = re.sub(f'({brand_pattern})', r'【\1】', note, count=1, flags=re.IGNORECASE)
        note = re.sub(r'】\s+', '】', note)
    if not note or note in title:
        return title
    return f'{title} | {note}' if title else note
