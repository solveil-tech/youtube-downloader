"""Source-attributed Apple catalogue tracks; unknown artists never guessed."""
import datetime as dt
import json
import re
import time
from pathlib import Path
from threading import Lock
import requests
from idol_search import normalize

API = 'https://itunes.apple.com'
# Verified against the corresponding Apple Music artist pages, not search rank.
VERIFIED_ARTISTS = {
    'stayc': 1538881438,  # https://music.apple.com/us/artist/stayc/1538881438
    'itzy': 1451964345,   # https://music.apple.com/us/artist/itzy/1451964345
}
_lock = Lock()
_next_request = 0.0


def catalogue_request(endpoint, params, cancelled=lambda: False):
    global _next_request
    # Apple's documented approximate request limit is 20/minute.
    while not _lock.acquire(timeout=0.1):
        if cancelled():
            raise InterruptedError()
    try:
        while time.monotonic() < _next_request:
            if cancelled():
                raise InterruptedError()
            time.sleep(0.1)
        if cancelled():
            raise InterruptedError()
        _next_request = time.monotonic() + 3.1
    finally:
        _lock.release()
    reply = requests.get(API + endpoint, params=params, timeout=(5, 20))
    if cancelled():
        raise InterruptedError()
    reply.raise_for_status()
    return reply.json()['results']


def base_track_title(title):
    if re.search(r'\b(remix|instrumental|inst|karaoke|sped[ -]?up|slowed|reverb|remaster|live ver(?:sion)?|radio edit|a cappella|acoustic ver(?:sion)?|MAMA version)\b|리믹스|반주', title, re.I):
        return None
    return re.sub(r'\s*[([](?:English|Japanese|Korean|Chinese|Spanish|French|German|ENG|JPN|KOR)\s*(?:ver\.?|version)[)\]]\s*$', '', title, flags=re.I).strip()


def fetch_group_songs(group, cancelled=lambda: False):
    allowed = {normalize(n) for n in [group['name'], group.get('korean', ''), *group.get('aliases', [])] if n}
    confirmed_id = VERIFIED_ARTISTS.get(normalize(group['name']))
    artists = catalogue_request('/lookup' if confirmed_id else '/search',
                               {'id': confirmed_id, 'country': 'US'} if confirmed_id else
                               {'term': group['name'], 'entity': 'musicArtist', 'limit': 200, 'country': 'US'}, cancelled)
    artists = {a['artistId']: a for a in artists if normalize(a.get('artistName', '')) in allowed}
    if confirmed_id:
        artists = {key: artist for key, artist in artists.items() if key == confirmed_id}
    if len(artists) != 1:
        raise ValueError(f"{group['name']}: expected one matching artist in the US music catalogue, found {len(artists)}")
    artist_id = next(iter(artists))
    albums = catalogue_request('/lookup', {'id': artist_id, 'entity': 'album', 'limit': 200, 'country': 'US'}, cancelled)
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    album_ids = list(dict.fromkeys(a['collectionId'] for a in albums if a.get('wrapperType') == 'collection'
                                  and a.get('artistId') == artist_id
                                  and str(a.get('releaseDate') or '')[:10] <= today))
    songs = {}
    for album_id in album_ids:
        tracks = catalogue_request('/lookup', {'id': album_id, 'entity': 'song', 'limit': 200, 'country': 'US'}, cancelled)
        for track in tracks:
            if track.get('kind') != 'song' or track.get('artistId') != artist_id:
                continue
            raw = track.get('trackName', '')
            title = base_track_title(raw)
            if not title:
                continue
            key = normalize(title)
            item = songs.setdefault(key, {'title': title, 'aliases': [], 'sources': []})
            if raw != title and raw not in item['aliases']:
                item['aliases'].append(raw)
            url = track.get('trackViewUrl') or track.get('collectionViewUrl')
            if url and url not in item['sources']:
                item['sources'].append(url)
    if not songs:
        raise ValueError('No eligible songs returned by the music catalogue')
    return {'artist_id': artist_id, 'updated': dt.date.today().isoformat(), 'source': API,
            'coverage': 'Available US storefront albums, up to 200; not an exhaustive discography guarantee',
            'songs': sorted(songs.values(), key=lambda s: s['title'].casefold())}


class SongCatalogue:
    def __init__(self, path, bundled=None):
        self.path = Path(path)
        self.groups = {}
        for candidate in (bundled, self.path):
            try:
                if candidate:
                    self.groups.update(json.loads(Path(candidate).read_text(encoding='utf-8')).get('groups', {}))
            except (OSError, ValueError):
                pass

    def songs(self, group):
        return self.groups.get(group, {}).get('songs', [])

    def aliases(self, group, typed):
        for song in self.songs(group):
            aliases = [song['title'], *song.get('aliases', [])]
            if normalize(typed) in {normalize(a) for a in aliases}:
                return aliases
        return [typed] if typed else []

    def save_group(self, group, result):
        self.groups[group] = result
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps({'schema_version': 1, 'groups': self.groups}, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.path)
