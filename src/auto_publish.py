#!/usr/bin/env python3
"""Poll a media folder and publish ready items per interval."""

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1
from pathlib import Path

from douban_resolver import resolve_douban
from longpt_publish import build_form, load_env_file, parse_auto_feed, submit
from longpt_seed import add_to_qbit, download_torrent, extract_torrent_id
from main_cli import process_movie, process_tv


VIDEO_EXTENSIONS = {
    '.mkv', '.mp4', '.avi', '.mov', '.wmv', '.m2ts', '.ts', '.flv', '.webm',
}

INCOMPLETE_EXTENSIONS = {
    '.!qb', '.part', '.crdownload', '.aria2', '.tmp',
}


@dataclass
class AutoPublishConfig:
    media_root: Path
    archive_root: Path = Path(r'C:\download\comp')
    auto_list: Path = Path('auto_feed.txt')
    interval_minutes: int = 30
    stable_minutes: int = 10
    stable_probe_seconds: int = 5
    max_per_run: int = 1
    min_confidence: int = 85
    source: str = 'DSNP WEB-DL'
    team: str = 'LongWeb'
    submit: bool = False
    auto_download: bool = False
    vt_service: str = 'DisneyPlus'
    vt_default_quality: int = 2160
    vt_video_codec: str = 'h265'
    vt_subtitle_languages: str = 'zh-Hans,zh-HK,en'
    vt_audio_languages: str = 'en,zh'
    vt_probe_template: str = 'poetry run vt dl --list {service} {url}'
    vt_workdir: Path = Path('.')
    qbit_skip_checking: bool = True
    state_db: Path = Path('temp/auto_publish_state.sqlite3')
    upload_html: Path = Path('html/LongPT __ 发布 - Powered by NexusPHP.html')


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def load_config(args):
    load_env_file()
    media_root = Path(args.root or os.environ.get('AUTO_MEDIA_ROOT', r'C:\download\iqy'))
    archive_root = Path(args.archive_root or os.environ.get('AUTO_ARCHIVE_ROOT', r'C:\download\comp'))
    return AutoPublishConfig(
        media_root=media_root,
        archive_root=archive_root,
        auto_list=Path(args.auto_list or os.environ.get('AUTO_LIST', 'auto_feed.txt')),
        interval_minutes=int(args.interval_minutes or os.environ.get('AUTO_PUBLISH_INTERVAL_MINUTES', 30)),
        stable_minutes=int(os.environ.get('AUTO_PUBLISH_STABLE_MINUTES', 10)),
        stable_probe_seconds=int(os.environ.get('AUTO_PUBLISH_STABLE_PROBE_SECONDS', 5)),
        max_per_run=int(os.environ.get('AUTO_PUBLISH_MAX_PER_RUN', 1)),
        min_confidence=int(os.environ.get('AUTO_PUBLISH_MIN_CONFIDENCE', 85)),
        source=os.environ.get('AUTO_SOURCE', 'DSNP WEB-DL'),
        team=os.environ.get('AUTO_TEAM', 'LongWeb'),
        submit=env_bool('AUTO_SUBMIT', False) and not args.dry_run,
        auto_download=env_bool('AUTO_DOWNLOAD', False) or args.auto_download,
        vt_service=os.environ.get('AUTO_VT_SERVICE', 'DisneyPlus'),
        vt_default_quality=int(os.environ.get('AUTO_VT_DEFAULT_QUALITY', 2160)),
        vt_video_codec=os.environ.get('AUTO_VT_VIDEO_CODEC', 'h265'),
        vt_subtitle_languages=os.environ.get('AUTO_VT_SUBTITLE_LANGUAGES', 'zh-Hans,zh-HK,en'),
        vt_audio_languages=os.environ.get('AUTO_VT_AUDIO_LANGUAGES', 'en,zh'),
        vt_probe_template=os.environ.get('AUTO_VT_PROBE_TEMPLATE', 'poetry run vt dl --list {service} {url}'),
        vt_workdir=Path(os.environ.get('AUTO_VT_WORKDIR', '.')),
        qbit_skip_checking=env_bool('QBIT_SKIP_CHECKING', True),
        state_db=Path(os.environ.get('AUTO_PUBLISH_STATE_DB', 'temp/auto_publish_state.sqlite3')),
        upload_html=Path(os.environ.get('LONGPT_UPLOAD_HTML', 'html/LongPT __ 发布 - Powered by NexusPHP.html')),
    )


class StateStore:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                original_path TEXT NOT NULL,
                current_path TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                douban_url TEXT DEFAULT '',
                confidence INTEGER DEFAULT 0,
                candidates_json TEXT DEFAULT '',
                torrent_path TEXT DEFAULT '',
                downloaded_torrent_path TEXT DEFAULT '',
                longpt_id TEXT DEFAULT '',
                archive_path TEXT DEFAULT '',
                error TEXT DEFAULT '',
                attempts INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_key TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL,
                title TEXT DEFAULT '',
                service TEXT NOT NULL,
                kind TEXT NOT NULL,
                season TEXT DEFAULT '',
                status TEXT NOT NULL,
                spec_json TEXT DEFAULT '',
                command_json TEXT DEFAULT '',
                error TEXT DEFAULT '',
                attempts INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.ensure_column('archive_path', "TEXT DEFAULT ''")
        self.conn.commit()

    def ensure_column(self, name, definition):
        columns = {
            row['name']
            for row in self.conn.execute('PRAGMA table_info(resources)').fetchall()
        }
        if name not in columns:
            self.conn.execute(f'ALTER TABLE resources ADD COLUMN {name} {definition}')

    def upsert_candidate(self, item):
        now = datetime.now().isoformat(timespec='seconds')
        existing = self.conn.execute(
            'SELECT id, status FROM resources WHERE fingerprint = ?',
            (item['fingerprint'],),
        ).fetchone()
        if existing:
            self.conn.execute(
                'UPDATE resources SET current_path = ?, updated_at = ? WHERE id = ?',
                (item['path'], now, existing['id']),
            )
            self.conn.commit()
            return existing['id'], existing['status']

        cursor = self.conn.execute(
            """
            INSERT INTO resources
                (fingerprint, original_path, current_path, kind, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'new', ?, ?)
            """,
            (item['fingerprint'], item['path'], item['path'], item['kind'], now, now),
        )
        self.conn.commit()
        return cursor.lastrowid, 'new'

    def pending_rows(self):
        return self.conn.execute(
            """
            SELECT * FROM resources
            WHERE status IN ('new', 'failed', 'prepared', 'needs_seed')
            ORDER BY created_at ASC
            """
        ).fetchall()

    def pending_download_rows(self):
        return self.conn.execute(
            """
            SELECT * FROM downloads
            WHERE status IN ('new', 'failed')
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()

    def upsert_download_item(self, item):
        now = datetime.now().isoformat(timespec='seconds')
        existing = self.conn.execute(
            'SELECT id, status FROM downloads WHERE item_key = ?',
            (item['item_key'],),
        ).fetchone()
        if existing:
            self.conn.execute(
                """
                UPDATE downloads
                SET title = ?, service = ?, kind = ?, season = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    item.get('title', ''),
                    item.get('service', ''),
                    item.get('kind', ''),
                    item.get('season', ''),
                    now,
                    existing['id'],
                ),
            )
            self.conn.commit()
            return existing['id'], existing['status']

        cursor = self.conn.execute(
            """
            INSERT INTO downloads
                (item_key, url, title, service, kind, season, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'new', ?, ?)
            """,
            (
                item['item_key'],
                item['url'],
                item.get('title', ''),
                item.get('service', ''),
                item.get('kind', ''),
                item.get('season', ''),
                now,
                now,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid, 'new'

    def update(self, resource_id, status, **fields):
        now = datetime.now().isoformat(timespec='seconds')
        fields['status'] = status
        fields['updated_at'] = now
        assignments = ', '.join(f'{key} = ?' for key in fields)
        values = list(fields.values()) + [resource_id]
        self.conn.execute(f'UPDATE resources SET {assignments} WHERE id = ?', values)
        self.conn.commit()

    def update_download(self, download_id, status, **fields):
        now = datetime.now().isoformat(timespec='seconds')
        fields['status'] = status
        fields['updated_at'] = now
        assignments = ', '.join(f'{key} = ?' for key in fields)
        values = list(fields.values()) + [download_id]
        self.conn.execute(f'UPDATE downloads SET {assignments} WHERE id = ?', values)
        self.conn.commit()

    def increment_attempts(self, resource_id):
        self.conn.execute('UPDATE resources SET attempts = attempts + 1 WHERE id = ?', (resource_id,))
        self.conn.commit()

    def increment_download_attempts(self, download_id):
        self.conn.execute('UPDATE downloads SET attempts = attempts + 1 WHERE id = ?', (download_id,))
        self.conn.commit()

    def counts(self):
        rows = self.conn.execute(
            'SELECT status, COUNT(*) AS count FROM resources GROUP BY status ORDER BY status'
        ).fetchall()
        return {row['status']: row['count'] for row in rows}

    def download_counts(self):
        rows = self.conn.execute(
            'SELECT status, COUNT(*) AS count FROM downloads GROUP BY status ORDER BY status'
        ).fetchall()
        return {row['status']: row['count'] for row in rows}


def stable_key(*parts):
    hasher = sha1()
    for part in parts:
        hasher.update(str(part or '').strip().lower().encode('utf-8', 'ignore'))
        hasher.update(b'\0')
    return hasher.hexdigest()


def normalize_kind(value):
    text = str(value or '').strip().lower()
    if text in {'tv', 'series', 'show', 'episode', '剧集', '电视剧'}:
        return 'tv'
    if text in {'movie', 'film', '电影'}:
        return 'movie'
    return ''


def normalize_season(value):
    text = str(value or '').strip()
    if not text:
        return ''
    match = re.search(r'S0*(\d{1,2})', text, re.IGNORECASE)
    if match:
        return f"S{int(match.group(1)):02d}"
    if text.isdigit():
        return f"S{int(text):02d}"
    return text


def looks_like_url(value):
    return bool(re.search(r'https?://\S+', str(value or ''), re.IGNORECASE))


def is_korean_item(item):
    text = ' '.join(str(item.get(name, '')) for name in ('title', 'url'))
    return bool(re.search(r'韩国|韓国|韩语|韓語|\bkorea(?:n)?\b|\bkr\b', text, re.IGNORECASE))


def parse_auto_list_line(line, default_service='DisneyPlus'):
    text = line.strip()
    if not text or text.startswith('#'):
        return None

    if text.startswith('{'):
        data = json.loads(text)
        url = str(data.get('url') or '').strip()
        if not url:
            return None
        kind = normalize_kind(data.get('kind') or data.get('type')) or 'movie'
        season = normalize_season(data.get('season') or data.get('w'))
        if season:
            kind = 'tv'
        item = {
            'url': url,
            'title': str(data.get('title') or data.get('name') or '').strip(),
            'service': str(data.get('service') or data.get('provider') or default_service).strip(),
            'kind': kind,
            'season': season,
        }
        item['korean'] = bool(data.get('korean')) or is_korean_item(item)
        item['item_key'] = stable_key(item['service'], item['kind'], item['season'], item['url'])
        return item

    parts = [part.strip() for part in re.split(r'\s*\|\s*', text) if part.strip()]
    if len(parts) == 1:
        match = re.search(r'https?://\S+', text, re.IGNORECASE)
        if not match:
            return None
        url = match.group(0)
        title = text.replace(url, '').strip(' |')
        item = {
            'url': url,
            'title': title,
            'service': default_service,
            'kind': 'movie',
            'season': '',
        }
        item['korean'] = is_korean_item(item)
        item['item_key'] = stable_key(item['service'], item['kind'], item['season'], item['url'])
        return item

    url_index = next((index for index, part in enumerate(parts) if looks_like_url(part)), -1)
    if url_index < 0:
        return None

    url = parts[url_index]
    kind = ''
    season = ''
    service = default_service
    title_parts = []
    for index, part in enumerate(parts):
        if index == url_index:
            continue
        normalized_kind = normalize_kind(part)
        normalized_season = normalize_season(part)
        if normalized_kind:
            kind = normalized_kind
        elif normalized_season and re.search(r'^(S?\d{1,2})$', part, re.IGNORECASE):
            season = normalized_season
        elif service == default_service and re.fullmatch(r'[A-Za-z][A-Za-z0-9_+-]*', part):
            service = part
        else:
            title_parts.append(part)

    if season:
        kind = 'tv'
    kind = kind or 'movie'
    item = {
        'url': url,
        'title': ' '.join(title_parts).strip(),
        'service': service,
        'kind': kind,
        'season': season,
    }
    item['korean'] = is_korean_item(item)
    item['item_key'] = stable_key(item['service'], item['kind'], item['season'], item['url'])
    return item


def load_auto_list(path, default_service='DisneyPlus'):
    path = Path(path)
    if not path.exists():
        return []
    items = []
    seen = set()
    for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        try:
            item = parse_auto_list_line(line, default_service)
        except (TypeError, ValueError, json.JSONDecodeError):
            item = None
        if not item or item['item_key'] in seen:
            continue
        seen.add(item['item_key'])
        items.append(item)
    return items


def sync_auto_list(config, store):
    queued = []
    items = load_auto_list(config.auto_list, config.vt_service)
    fallback = Path('auto_list.txt')
    if fallback != config.auto_list:
        items.extend(load_auto_list(fallback, config.vt_service))

    seen = set()
    for item in items:
        if item['item_key'] in seen:
            continue
        seen.add(item['item_key'])
        download_id, status = store.upsert_download_item(item)
        queued.append({'id': download_id, 'url': item['url'], 'kind': item['kind'], 'status': status})
    return queued


def comma_languages(value):
    return [part.strip() for part in str(value or '').split(',') if part.strip()]


def with_language(value, language):
    languages = comma_languages(value)
    lowered = {part.lower() for part in languages}
    if language.lower() not in lowered:
        languages.append(language)
    return ','.join(languages)


def select_vt_options(probe_text, default_quality=2160):
    text = str(probe_text or '')
    resolutions = {int(value) for value in re.findall(r'\b(2160|1080|720|480)p\b', text, re.IGNORECASE)}
    if 2160 in resolutions or not resolutions:
        quality = default_quality
    elif 1080 in resolutions:
        quality = 1080
    else:
        quality = max(resolutions)

    has_dv = bool(re.search(r'Dolby\s+Vision|\bDoVi\b|\bDV\b|dvhe|dvh1', text, re.IGNORECASE))
    has_hdr = bool(re.search(r'\bHDR(?:10|10\+)?\b|HLG|SMPTE\s+ST\s+20(?:86|94)', text, re.IGNORECASE))
    if not text:
        dynamic_range = 'dv+hdr'
    elif has_dv and has_hdr:
        dynamic_range = 'dv+hdr'
    elif has_dv:
        dynamic_range = 'dv'
    elif has_hdr:
        dynamic_range = 'hdr'
    else:
        dynamic_range = ''

    return {'quality': quality, 'dynamic_range': dynamic_range}


def render_template_command(template, **values):
    rendered = template.format(**values)
    return re.findall(r'"[^"]*"|\'[^\']*\'|\S+', rendered)


def clean_command_parts(parts):
    cleaned = []
    for part in parts:
        if len(part) >= 2 and part[0] == part[-1] and part[0] in {'"', "'"}:
            cleaned.append(part[1:-1])
        else:
            cleaned.append(part)
    return cleaned


def run_command(command, cwd):
    process = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    output = '\n'.join(part for part in (process.stdout, process.stderr) if part)
    return process.returncode, output


def probe_vt_specs(config, item):
    command = clean_command_parts(render_template_command(
        config.vt_probe_template,
        service=item['service'],
        url=item['url'],
        season=item.get('season') or 'S01',
        title=item.get('title', ''),
    ))
    return_code, output = run_command(command, config.vt_workdir)
    return {
        'command': command,
        'return_code': return_code,
        'output': output,
        'options': select_vt_options(output if return_code == 0 else '', config.vt_default_quality),
    }


def build_vt_download_command(config, item, options):
    subtitle_languages = config.vt_subtitle_languages
    audio_languages = config.vt_audio_languages
    if item.get('korean') or is_korean_item(item):
        subtitle_languages = with_language(subtitle_languages, 'ko')
        audio_languages = with_language(audio_languages, 'ko')

    command = [
        'poetry', 'run', 'vt', 'dl',
        '-q', str(options['quality']),
        '-v', config.vt_video_codec,
        '-sl', subtitle_languages,
        '-al', audio_languages,
    ]
    if options.get('dynamic_range'):
        command[6:6] = ['-r', options['dynamic_range']]

    if item['kind'] == 'tv':
        command.extend(['-w', item.get('season') or 'S01', item['service'], item['url']])
    else:
        command.extend([item['service'], '-m', item['url']])
    return command


def download_next_from_auto_list(config, store):
    queued = sync_auto_list(config, store)
    rows = store.pending_download_rows()
    if not rows:
        return {'queued': queued, 'downloaded': None}

    row = rows[0]
    item = {
        'url': row['url'],
        'title': row['title'],
        'service': row['service'],
        'kind': row['kind'],
        'season': row['season'],
    }
    item['korean'] = is_korean_item(item)
    store.increment_download_attempts(row['id'])
    store.update_download(row['id'], 'probing', error='')
    probe = probe_vt_specs(config, item)
    command = build_vt_download_command(config, item, probe['options'])
    store.update_download(
        row['id'],
        'downloading',
        spec_json=json.dumps(probe, ensure_ascii=False),
        command_json=json.dumps(command, ensure_ascii=False),
    )

    return_code, output = run_command(command, config.vt_workdir)
    if return_code:
        store.update_download(row['id'], 'failed', error=output[-2000:])
        raise RuntimeError(f"vt 下载失败: {row['url']}")

    store.update_download(row['id'], 'downloaded', error='', command_json=json.dumps(command, ensure_ascii=False))
    return {
        'queued': queued,
        'downloaded': {
            'id': row['id'],
            'url': row['url'],
            'kind': row['kind'],
            'command': command,
            'probe_return_code': probe['return_code'],
        },
    }


def media_files(path):
    path = Path(path)
    if path.is_file():
        return [path] if path.suffix.lower() in VIDEO_EXTENSIONS else []
    return [
        item for item in path.rglob('*')
        if item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS
    ]


def all_files(path):
    path = Path(path)
    if path.is_file():
        return [path]
    return [item for item in path.rglob('*') if item.is_file()]


def has_incomplete_download_markers(path):
    return any(item.suffix.lower() in INCOMPLETE_EXTENSIONS for item in all_files(path))


def file_signature(path):
    signature = {}
    for item in all_files(path):
        stat = item.stat()
        signature[str(item)] = (stat.st_size, stat.st_mtime_ns)
    return signature


def is_stable(path, stable_minutes, probe_seconds=0):
    files = media_files(path)
    if not files:
        return False
    if has_incomplete_download_markers(path):
        return False
    newest_mtime = max(item.stat().st_mtime for item in all_files(path))
    if (time.time() - newest_mtime) < stable_minutes * 60:
        return False
    if probe_seconds <= 0:
        return True
    before = file_signature(path)
    time.sleep(probe_seconds)
    return before == file_signature(path)


def fingerprint(path):
    root = Path(path)
    hasher = sha1()
    files = media_files(root)
    for item in sorted(files):
        stat = item.stat()
        rel = item.name if root.is_file() else str(item.relative_to(root))
        hasher.update(rel.lower().encode('utf-8', 'ignore'))
        hasher.update(str(stat.st_size).encode())
        hasher.update(str(int(stat.st_mtime)).encode())
    return hasher.hexdigest()


def classify_entry(path):
    path = Path(path)
    if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
        return 'movie'
    if path.is_dir():
        videos = media_files(path)
        if len(videos) == 1:
            return 'movie'
        if videos:
            return 'tv'
    return ''


def scan_media_root(config, store):
    config.media_root.mkdir(parents=True, exist_ok=True)
    added = []
    entries = sorted(
        config.media_root.iterdir(),
        key=lambda item: (media_newest_mtime(item), item.name.lower()),
    )
    for entry in entries:
        kind = classify_entry(entry)
        if not kind or not is_stable(
            entry,
            config.stable_minutes,
            config.stable_probe_seconds,
        ):
            continue
        item = {
            'path': str(entry),
            'kind': kind,
            'fingerprint': fingerprint(entry),
        }
        resource_id, status = store.upsert_candidate(item)
        added.append({'id': resource_id, 'path': str(entry), 'kind': kind, 'status': status})
    return added


def media_newest_mtime(path):
    files = media_files(path)
    if not files:
        return 0
    return max(item.stat().st_mtime for item in files)


def mark_existing_folders_published(config, store):
    marked = []
    for entry in sorted(config.media_root.iterdir(), key=lambda item: item.name.lower()):
        if not entry.is_dir() or not media_files(entry):
            continue
        item = {
            'path': str(entry),
            'kind': 'tv',
            'fingerprint': fingerprint(entry),
        }
        resource_id, _status = store.upsert_candidate(item)
        store.update(
            resource_id,
            'seeding',
            current_path=str(entry),
            error='手动标记：现有文件夹已发布，后续跳过',
        )
        marked.append({'id': resource_id, 'path': str(entry)})
    return marked


def parse_season_and_episode(path):
    text = Path(path).name
    season_match = re.search(r'\bS0*(\d{1,2})\b', text, re.IGNORECASE)
    season = int(season_match.group(1)) if season_match else 1

    episode_numbers = []
    for file in media_files(path):
        match = re.search(r'\bS\d{1,2}E0*(\d{1,3})\b|\bE0*(\d{1,3})\b', file.name, re.IGNORECASE)
        if match:
            episode_numbers.append(int(match.group(1) or match.group(2)))
    return season, min(episode_numbers) if episode_numbers else 1


def ensure_movie_folder(path):
    file_path = Path(path)
    if file_path.is_dir():
        return file_path
    folder = file_path.with_suffix('')
    folder.mkdir(exist_ok=True)
    target = folder / file_path.name
    if not target.exists():
        shutil.move(str(file_path), str(target))
    return folder


def unique_destination(path):
    path = Path(path)
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f'{path.stem} ({index}){path.suffix}')
        if not candidate.exists():
            return candidate
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return path.with_name(f'{path.stem} ({timestamp}){path.suffix}')


def move_to_archive(config, path):
    source = Path(path)
    if not source.exists():
        raise RuntimeError(f'待移动路径不存在: {source}')

    config.archive_root.mkdir(parents=True, exist_ok=True)
    if source.parent.resolve() == config.archive_root.resolve():
        return source

    target = unique_destination(config.archive_root / source.name)
    shutil.move(str(source), str(target))
    return target


def get_upload_action(config):
    html = config.upload_html.read_text(encoding='utf-8', errors='ignore')
    match = re.search(r'<form[^>]+action="([^"]+)"', html)
    return match.group(1) if match else 'https://longpt.org/takeupload.php'


def publish_to_longpt(config, torrent_path):
    cookie = os.environ.get('LONGPT_COOKIE')
    if not cookie:
        raise RuntimeError('缺少 LONGPT_COOKIE')
    fields = parse_auto_feed('temp/auto_feed.txt')
    data, _tag_values = build_form(fields)
    data['descr'] = add_auto_publish_notice(data.get('descr', ''))
    response = submit(get_upload_action(config), data, torrent_path, cookie)
    if response.status_code not in {200, 302, 303}:
        raise RuntimeError(f'LongPT 发布失败: HTTP {response.status_code}')
    location = response.headers.get('Location', '')
    longpt_id = extract_torrent_id(location)
    if not longpt_id:
        raise RuntimeError(f'LongPT 已响应但未找到种子 id: {location or response.text[:200]}')
    return longpt_id


def douban_subject_id(url):
    match = re.search(r'movie\.douban\.com/subject/(\d+)', str(url or ''))
    return match.group(1) if match else ''


def validate_auto_feed_douban(auto_feed_path, expected_url):
    try:
        fields = parse_auto_feed(auto_feed_path)
    except (OSError, ValueError):
        return False, '无法读取 auto_feed 校验豆瓣信息'

    feed_subject = douban_subject_id(fields.get('dburl') or fields.get('url'))
    expected_subject = douban_subject_id(expected_url)
    if expected_subject and feed_subject and expected_subject != feed_subject:
        return False, f'auto_feed 豆瓣 id={feed_subject} 与匹配结果 id={expected_subject} 不一致'
    if not fields.get('name'):
        return False, 'auto_feed 缺少主标题'
    return True, ''


def add_auto_publish_notice(description):
    notice = (
        '[quote]\n'
        '[color=RoyalBlue][b][size=4]LongPT 自动发种机发布[/size][/b][/color]\n'
        '[color=Gray]如有错误请联系管理修改。[/color]\n'
        '[/quote]'
    )
    description = str(description or '').strip()
    if 'LongPT 自动发种机发布' in description:
        return description
    if not description:
        return notice
    return f'{notice}\n\n{description}'


def finish_seeding(config, store, resource_id, longpt_id, resource_path, downloaded_torrent_path=''):
    store.update(resource_id, 'downloading_torrent', longpt_id=longpt_id)
    if downloaded_torrent_path and Path(downloaded_torrent_path).exists():
        torrent_path = Path(downloaded_torrent_path)
    else:
        torrent_path, _details_url, _download_url = download_torrent(
            longpt_id,
            'temp/torrent/downloaded',
        )

    store.update(
        resource_id,
        'archiving',
        downloaded_torrent_path=str(torrent_path),
        current_path=str(resource_path),
    )
    archived_path = move_to_archive(config, resource_path)
    store.update(
        resource_id,
        'adding_to_qbit',
        current_path=str(archived_path),
        archive_path=str(archived_path),
    )

    add_to_qbit(
        torrent_path,
        str(archived_path.parent),
        skip_checking=config.qbit_skip_checking,
    )
    store.update(
        resource_id,
        'seeding',
        longpt_id=longpt_id,
        current_path=str(archived_path),
        archive_path=str(archived_path),
        downloaded_torrent_path=str(torrent_path),
        error='',
    )


def resume_seeding(config, store, row):
    if not row['longpt_id']:
        raise RuntimeError('needs_seed 状态缺少 LongPT 种子 id，无法只补辅种')
    resource_path = Path(row['current_path'])
    finish_seeding(
        config,
        store,
        row['id'],
        row['longpt_id'],
        resource_path,
        row['downloaded_torrent_path'],
    )


def process_resource(config, store, row):
    if row['status'] == 'needs_seed':
        resume_seeding(config, store, row)
        return

    store.increment_attempts(row['id'])
    path = Path(row['current_path'])
    store.update(row['id'], 'resolving', error='')

    working_path = ensure_movie_folder(path) if row['kind'] == 'movie' else path
    best, candidates = resolve_douban(working_path.name, config.min_confidence)
    candidates_json = json.dumps([candidate.__dict__ for candidate in candidates], ensure_ascii=False)
    if not best:
        store.update(
            row['id'],
            'needs_review',
            current_path=str(working_path),
            candidates_json=candidates_json,
            error='豆瓣匹配置信度不足',
        )
        return

    store.update(
        row['id'],
        'processing',
        current_path=str(working_path),
        douban_url=best.url,
        confidence=best.score,
        candidates_json=candidates_json,
    )

    if row['kind'] == 'movie':
        result = process_movie(best.url, str(working_path), source=config.source, team=config.team)
    else:
        season, episodes_start = parse_season_and_episode(working_path)
        result = process_tv(best.url, str(working_path), season, episodes_start, source=config.source, team=config.team)

    if not result:
        raise RuntimeError('main_cli 处理失败')

    torrent_path = result.get('torrent_path', '')
    if not torrent_path:
        raise RuntimeError('main_cli 未返回种子路径')

    ok, feed_error = validate_auto_feed_douban(
        result.get('auto_feed_path', 'temp/auto_feed.txt'),
        best.url,
    )
    if not ok:
        store.update(
            row['id'],
            'needs_review',
            torrent_path=torrent_path,
            current_path=str(working_path),
            error=feed_error,
        )
        return

    if not config.submit:
        store.update(row['id'], 'prepared', torrent_path=torrent_path)
        return

    store.update(row['id'], 'publishing', torrent_path=torrent_path)
    longpt_id = publish_to_longpt(config, torrent_path)
    store.update(row['id'], 'published', longpt_id=longpt_id)

    resource_path = Path(result.get('video_path') or working_path)
    try:
        finish_seeding(config, store, row['id'], longpt_id, resource_path)
    except Exception as exc:
        store.update(
            row['id'],
            'needs_seed',
            current_path=str(resource_path),
            longpt_id=longpt_id,
            error=f'已发布 LongPT id={longpt_id}，但下载/移动/辅种失败: {exc}',
        )
        return


def run_once(config, scan_only=False):
    store = StateStore(config.state_db)
    scanned = scan_media_root(config, store)
    queued = sync_auto_list(config, store) if config.auto_download else []
    if scan_only:
        return {
            'scanned': scanned,
            'queued': queued,
            'counts': store.counts(),
            'download_counts': store.download_counts(),
        }

    processed = []
    errors = []
    for row in store.pending_rows():
        if config.max_per_run > 0 and len(processed) >= config.max_per_run:
            break
        try:
            process_resource(config, store, row)
            processed.append(row['id'])
        except Exception as exc:
            store.update(row['id'], 'failed', error=str(exc))
            errors.append({'id': row['id'], 'path': row['current_path'], 'error': str(exc)})

    downloaded = None
    download_error = None
    if config.auto_download and not processed and not errors:
        try:
            download_result = download_next_from_auto_list(config, store)
            queued = download_result['queued']
            downloaded = download_result['downloaded']
        except Exception as exc:
            download_error = str(exc)

    return {
        'scanned': scanned,
        'queued': queued,
        'counts': store.counts(),
        'download_counts': store.download_counts(),
        'processed': processed,
        'errors': errors,
        'downloaded': downloaded,
        'download_error': download_error,
    }


def main():
    parser = argparse.ArgumentParser(description='Auto publish ready media from a folder')
    parser.add_argument('--root', default='')
    parser.add_argument('--archive-root', default='')
    parser.add_argument('--auto-list', default='')
    parser.add_argument('--interval-minutes', type=int, default=0)
    parser.add_argument('--max-per-run', type=int, default=-1)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--daemon', action='store_true')
    parser.add_argument('--auto-download', action='store_true')
    parser.add_argument('--scan-only', action='store_true')
    parser.add_argument('--mark-existing-folders-published', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='Do not submit to LongPT even if AUTO_SUBMIT=true')
    args = parser.parse_args()

    config = load_config(args)
    if args.max_per_run >= 0:
        config.max_per_run = args.max_per_run
    if args.mark_existing_folders_published:
        store = StateStore(config.state_db)
        marked = mark_existing_folders_published(config, store)
        print(json.dumps({'marked': marked, 'counts': store.counts()}, ensure_ascii=False, indent=2))
        return 0

    if not args.daemon:
        result = run_once(config, scan_only=args.scan_only)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    while True:
        try:
            result = run_once(config, scan_only=args.scan_only)
            print(json.dumps(result, ensure_ascii=False))
        except Exception as exc:
            print(f'自动发布失败: {exc}')
        time.sleep(config.interval_minutes * 60)


if __name__ == '__main__':
    raise SystemExit(main())
