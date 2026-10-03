"""Validated, data-only catalogue updates independent of the application EXE."""
import json
import os
import tempfile
from pathlib import Path
import requests
from idol_search import normalize

REPOSITORY = 'solveil-tech/youtube-downloader'
PACK_NAME = 'search_database.json'
MAX_BYTES = 20 * 1024 * 1024


def validate(idols, songs):
    if not isinstance(idols, dict) or idols.get('schema_version') != 2:
        raise ValueError('Unsupported member database version (expected 2)')
    groups, members = idols.get('groups'), idols.get('members')
    if not isinstance(groups, list) or not groups or not isinstance(members, list) or not members:
        raise ValueError('Member database has no groups or members')
    names = set()
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get('name'), str) or not group['name']:
            raise ValueError('Invalid group record')
        if group['name'] in names or not isinstance(group.get('aliases'), list) or not all(isinstance(a, str) for a in group['aliases']):
            raise ValueError('Invalid or duplicate group aliases')
        if not isinstance(group.get('korean', ''), str):
            raise ValueError('Invalid group name')
        names.add(group['name'])
    ids, expected = set(), {}
    for member in members:
        if not isinstance(member, dict) or not all(isinstance(member.get(k), str) and member[k] for k in ('id', 'group', 'stage_name')):
            raise ValueError('Invalid member record')
        if member['id'] in ids or member['group'] not in names:
            raise ValueError('Duplicate member or unknown group')
        if not isinstance(member.get('raw_name_fields', {}), dict):
            raise ValueError('Invalid member name fields')
        if not all(isinstance(member.get(k, ''), str) for k in ('full_name', 'full_name_hangul', 'stage_name_hangul')) or not all(isinstance(v, str) for v in member.get('raw_name_fields', {}).values()):
            raise ValueError('Invalid member name text')
        ids.add(member['id'])
        aliases = member.get('aliases')
        if not isinstance(aliases, list) or not aliases:
            raise ValueError('Missing member aliases')
        for alias in aliases:
            if not isinstance(alias, dict) or not isinstance(alias.get('text'), str) or not alias['text'] or alias.get('normalized') != normalize(alias['text']):
                raise ValueError('Invalid member alias')
            expected.setdefault(alias['normalized'], set()).add(member['id'])
    index = idols.get('alias_index')
    if not isinstance(index, dict) or any(not isinstance(v, list) or not all(isinstance(i, str) for i in v) for v in index.values()):
        raise ValueError('Invalid alias index')
    if {k: set(v) for k, v in index.items()} != expected:
        raise ValueError('Alias index does not match member records')
    if not isinstance(songs, dict) or songs.get('schema_version') != 1 or not isinstance(songs.get('groups'), dict):
        raise ValueError('Unsupported song database version (expected 1)')
    for name, group in songs['groups'].items():
        if not isinstance(group, dict) or not isinstance(group.get('songs'), list):
            raise ValueError('Invalid song group: ' + name)
        for song in group['songs']:
            if not isinstance(song, dict) or not isinstance(song.get('title'), str) or not song['title'].strip():
                raise ValueError('Invalid song title')
            if not isinstance(song.get('aliases', []), list) or not all(isinstance(a, str) for a in song.get('aliases', [])):
                raise ValueError('Invalid song aliases')
    return {'schema_version': 1, 'idols': idols, 'songs': songs}


def read_json(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Database exceeds the 20 MB size limit')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def load_databases(data_dir, bundled_idols, bundled_songs):
    pack_path = Path(data_dir) / 'idol_names' / PACK_NAME
    error = ''
    if pack_path.is_file():
        try:
            pack = read_json(pack_path)
            if not isinstance(pack, dict) or pack.get('schema_version') != 1:
                raise ValueError('Unsupported database pack version')
            return validate(pack['idols'], pack['songs']), ''
        except (OSError, ValueError, KeyError, TypeError) as exc:
            error = str(exc)
    return validate(read_json(bundled_idols), read_json(bundled_songs)), error


def import_database(path, current):
    data = read_json(path)
    if isinstance(data, dict) and 'idols' in data and 'songs' in data:
        if data.get('schema_version') != 1:
            raise ValueError('Unsupported database pack version')
        return validate(data['idols'], data['songs'])
    if isinstance(data, dict) and isinstance(data.get('groups'), list):
        sibling = Path(path).with_name('song_catalogue.json')
        return validate(data, read_json(sibling) if sibling.is_file() else current['songs'])
    return validate(current['idols'], data)


def download_databases(cancelled=lambda: False):
    def fetch(url):
        if cancelled():
            raise InterruptedError('Database update cancelled')
        # Stream with a hard cap; downloaded files are JSON data, never code.
        with requests.get(url, timeout=(5, 20), stream=True) as reply:
            reply.raise_for_status()
            content = bytearray()
            for chunk in reply.iter_content(64 * 1024):
                if cancelled():
                    raise InterruptedError('Database update cancelled')
                content.extend(chunk)
                if len(content) > MAX_BYTES:
                    raise ValueError('Database exceeds the 20 MB size limit')
            return json.loads(content.decode('utf-8-sig'))
    # Pin both files to one revision to prevent mixing an in-progress release.
    revision = fetch(f'https://api.github.com/repos/{REPOSITORY}/commits/main')['sha']
    if not isinstance(revision, str) or len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
        raise ValueError('Invalid GitHub revision')
    root = f'https://raw.githubusercontent.com/{REPOSITORY}/{revision}/idol_names'
    pack = validate(fetch(root + '/idol_aliases.json'), fetch(root + '/song_catalogue.json'))
    pack['revision'] = revision
    return pack


def install_database(data_dir, pack):
    validate(pack['idols'], pack['songs'])
    target = Path(data_dir) / 'idol_names' / PACK_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent, suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            json.dump(pack, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return target
