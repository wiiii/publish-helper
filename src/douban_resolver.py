#!/usr/bin/env python3
"""Resolve Douban subject URLs from release names with confidence scoring."""

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlparse, parse_qs

import requests

ALIAS_PATH = Path('static/douban_aliases.json')

NOISE_TOKENS = {
    '2160p', '1080p', '720p', '480p', 'web', 'web-dl', 'webrip', 'dsnp',
    'nf', 'amzn', 'hulu', 'hmax', 'bluray', 'blu-ray', 'remux', 'h264',
    'h.264', 'x264', 'h265', 'h.265', 'x265', 'hevc', 'avc', 'hdr',
    'hdr10', 'dv', 'ddp', 'eac3', 'e-ac3', 'aac', 'dts', 'truehd',
    'atmos', 'audio', 'longweb', 'longpt', 'longa', 'cmct', 'wiki',
    'proper', 'repack', 'multi', 'complete', 'season',
}


@dataclass
class DoubanCandidate:
    url: str
    title: str = ''
    year: str = ''
    score: int = 0
    reason: str = ''


def release_text(path_or_name):
    name = Path(path_or_name).stem if Path(str(path_or_name)).suffix else Path(str(path_or_name)).name
    return re.sub(r'[._\-]+', ' ', name)


def extract_year(text):
    match = re.search(r'\b(19\d{2}|20\d{2})\b', text)
    return match.group(1) if match else ''


def extract_season(text):
    match = re.search(r'\bS(?:eason)?\s*0*(\d{1,2})\b', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r'第([一二三四五六七八九十\d]+)季', text)
    if match and match.group(1).isdigit():
        return int(match.group(1))
    return 0


def search_terms(path_or_name):
    text = release_text(path_or_name)
    tokens = []
    for token in re.split(r'\s+', text):
        clean = token.strip()
        if not clean:
            continue
        lower = clean.lower()
        if lower in NOISE_TOKENS:
            continue
        if re.fullmatch(r'(s\d{1,2}e\d{1,3}|s\d{1,2}|e\d{1,3}|\d+bit|\d+audio)', lower):
            continue
        tokens.append(clean)
    return ' '.join(tokens[:8]).strip(), extract_year(text), extract_season(text)


def normalize_alias_key(value):
    value = release_text(value).lower()
    value = re.sub(r'\b(s\d{1,2}|season\s+\d{1,2}|e\d{1,3})\b', ' ', value)
    value = re.sub(r'\b(19\d{2}|20\d{2})\b', ' ', value)
    for token in NOISE_TOKENS:
        value = re.sub(rf'\b{re.escape(token)}\b', ' ', value)
    return re.sub(r'\s+', ' ', value).strip(' .-_')


def lookup_alias(path_or_name):
    if not ALIAS_PATH.exists():
        return ''
    try:
        aliases = json.loads(ALIAS_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return ''
    key = normalize_alias_key(path_or_name)
    dotted = key.replace(' ', '.')
    direct = aliases.get(key, '') or aliases.get(dotted, '')
    if direct:
        return direct
    for alias_key, url in aliases.items():
        normalized_alias = normalize_alias_key(alias_key)
        if normalized_alias and (key == normalized_alias or key.startswith(normalized_alias + ' ')):
            return url
    return ''


def normalize_subject_url(url):
    url = html.unescape(unquote(url))
    if 'duckduckgo.com/l/' in url:
        query = parse_qs(urlparse(url).query)
        if query.get('uddg'):
            url = query['uddg'][0]
    match = re.search(r'https?://movie\.douban\.com/subject/(\d+)/?', url)
    if not match:
        return ''
    return f'https://movie.douban.com/subject/{match.group(1)}/'


def collect_subject_urls(query, timeout=15):
    urls = []
    headers = {'User-Agent': 'Mozilla/5.0 publish-helper douban resolver'}
    search_url = f'https://duckduckgo.com/html/?q={quote_plus(query)}'
    response = requests.get(search_url, headers=headers, timeout=timeout)
    response.raise_for_status()
    for href in re.findall(r'href=["\']([^"\']+)["\']', response.text):
        subject_url = normalize_subject_url(href)
        if subject_url and subject_url not in urls:
            urls.append(subject_url)
        if len(urls) >= 8:
            break
    return urls


def fetch_subject_title(url, timeout=15):
    headers = {
        'Referer': 'https://movie.douban.com/',
        'User-Agent': 'Mozilla/5.0 publish-helper douban resolver',
    }
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    match = re.search(r'<title>(.*?)</title>', response.text, re.IGNORECASE | re.DOTALL)
    title = html.unescape(re.sub(r'\s+', ' ', match.group(1)).strip()) if match else ''
    year_match = re.search(r'year">?\(?(\d{4})\)?<', response.text)
    if not year_match:
        year_match = re.search(r'\((\d{4})\)', title)
    return title, year_match.group(1) if year_match else ''


def score_candidate(candidate, query_text, expected_year='', expected_season=0, rank=0):
    title = candidate.title.lower()
    query_tokens = [token.lower() for token in re.split(r'\s+', query_text) if token]
    matched = sum(1 for token in query_tokens if token in title)
    score = min(45, matched * 12)
    reasons = []
    if matched:
        reasons.append(f'title_tokens={matched}')
    if expected_year and candidate.year == expected_year:
        score += 25
        reasons.append('year')
    if expected_season:
        if re.search(rf'(第\s*{expected_season}\s*季|Season\s*{expected_season}|\bS0?{expected_season}\b)', candidate.title, re.IGNORECASE):
            score += 25
            reasons.append('season')
    if rank == 0:
        score += 5
        reasons.append('top_result')
    candidate.score = min(score, 100)
    candidate.reason = ','.join(reasons)
    return candidate


def resolve_douban(path_or_name, min_confidence=85):
    alias_url = lookup_alias(path_or_name)
    if alias_url:
        try:
            title, year = fetch_subject_title(alias_url)
        except requests.RequestException:
            title, year = '', ''
        candidate = DoubanCandidate(
            url=alias_url,
            title=title,
            year=year,
            score=100,
            reason='alias',
        )
        return candidate, [candidate]

    query_text, year, season = search_terms(path_or_name)
    if not query_text:
        return None, []

    query = f'site:movie.douban.com/subject {query_text} 豆瓣'
    candidates = []
    for rank, url in enumerate(collect_subject_urls(query)):
        try:
            title, candidate_year = fetch_subject_title(url)
        except requests.RequestException:
            title, candidate_year = '', ''
        candidate = score_candidate(
            DoubanCandidate(url=url, title=title, year=candidate_year),
            query_text,
            expected_year=year,
            expected_season=season,
            rank=rank,
        )
        candidates.append(candidate)

    candidates.sort(key=lambda item: item.score, reverse=True)
    best = candidates[0] if candidates and candidates[0].score >= min_confidence else None
    return best, candidates
