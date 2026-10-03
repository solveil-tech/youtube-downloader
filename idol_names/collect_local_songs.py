"""Maintainer-only discography import. Never run by the downloader UI."""
import concurrent.futures
import datetime
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from song_catalogue import base_track_title
from idol_search import normalize


class TracksParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.heading = []
        self.tracks = []
        self.item = None
        self.article = False
        self.context = ''
        self.release_allowed = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'div' and 'entry-content' in attrs.get('class', '').split():
            self.article = True
        self.stack.append(tag)
        if self.article and tag in ('ol', 'ul'):
            dates = re.findall(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(\d{4})', self.context, re.I)
            if dates:
                try:
                    self.release_allowed = datetime.datetime.strptime(' '.join(dates[-1]), '%B %d %Y').date() <= datetime.date.today()
                except ValueError:
                    self.release_allowed = False
            else:
                numeric = re.findall(r'Release\s*Date\s*[:–—-]?\s*(\d{1,2}/\d{1,2}/\d{2,4})', self.context, re.I)
                try:
                    stamp = numeric[-1]
                    self.release_allowed = datetime.datetime.strptime(stamp, '%d/%m/%y' if len(stamp.split('/')[-1]) == 2 else '%d/%m/%Y').date() <= datetime.date.today()
                except (ValueError, IndexError):
                    self.release_allowed = False
        if self.article and self.release_allowed and tag == 'li' and any(t in self.stack for t in ('ol', 'ul')):
            self.item = []

    def handle_data(self, data):
        if 'h1' in self.stack:
            self.heading.append(data)
        if self.item is not None:
            self.item.append(data)
        else:
            self.context += ' ' + data

    def handle_endtag(self, tag):
        if tag == 'li' and self.item is not None:
            self.tracks.append(' '.join(' '.join(self.item).split()))
            self.item = None
        if tag in self.stack:
            self.stack = self.stack[:len(self.stack) - 1 - self.stack[::-1].index(tag)]
        if tag in ('ol', 'ul'):
            self.context = ''


def collect(group):
    names = [group['name'], *group.get('aliases', [])]
    slugs = list(dict.fromkeys(re.sub(r'[^a-z0-9]+', '-', n.lower()).strip('-') for n in names if n.isascii()))
    overrides = {'i-dle': ['gi-dle', 'gidle', 'g-i-dle'], 'fromis_9': ['fromis-9', 'fromis_9'],
                 "Girls' Generation": ['girls-generation', 'snsd'], 'f(x)': ['fx'], 'woo!ah!': ['wooah'],
                 '9MUSES': ['9muses', 'nine-muses'], 'ifeye': ['ifeye'], 'OH MY GIRL': ['oh-girl']}
    slugs = overrides.get(group['name'], []) + slugs
    for slug in dict.fromkeys(slugs):
        url = f'https://kprofiles.com/{slug}-discography/'
        try:
            response = requests.get(url, timeout=(5, 18))
            if response.status_code != 200:
                continue
            parser = TracksParser()
            parser.feed(response.text)
            heading = normalize(' '.join(parser.heading))
            heading = heading.replace('λ', 'a')
            if 'discography' not in heading or not any(normalize(n) in heading for n in names if n.isascii()):
                continue
            songs = {}
            for raw in parser.tracks:
                raw = re.sub(r'\s*\((?:Title|Title Track)\)\s*', '', raw, flags=re.I)
                title = base_track_title(raw)
                if not title or len(title) > 160 or re.search(r'\b(remix|version|ver\.|inst\.|instrumental|sped|slowed|live|demo|intro|outro)\b', title, re.I):
                    continue
                songs.setdefault(normalize(title), {'title': title, 'aliases': [], 'sources': [url]})
            if songs:
                return group['name'], {'updated': datetime.date.today().isoformat(), 'source': url,
                    'coverage': 'Locally stored release track lists; excludes alternate versions; not guaranteed exhaustive',
                    'songs': sorted(songs.values(), key=lambda s: s['title'].casefold())}
        except requests.RequestException:
            continue
    return group['name'], None


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    groups = json.loads((root / 'idol_aliases.json').read_text(encoding='utf-8'))['groups']
    target = root / 'song_catalogue.json'
    db = json.loads(target.read_text(encoding='utf-8'))
    # Replace maintenance imports rather than keeping failed/obsolete parser output.
    for name in list(db['groups']):
        apple = [s for s in db['groups'][name]['songs'] if any('music.apple.com/' in u for u in s.get('sources', []))]
        if apple:
            db['groups'][name]['songs'] = apple
        else:
            del db['groups'][name]
    missing = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for name, result in pool.map(collect, groups):
            if result:
                previous = db['groups'].get(name, {})
                merged = {normalize(s['title']): s for s in previous.get('songs', [])
                          if any('music.apple.com/' in url for url in s.get('sources', []))}
                for song in result['songs']:
                    key = normalize(song['title'])
                    if key in merged:
                        merged[key]['sources'] = list(dict.fromkeys(merged[key].get('sources', []) + song['sources']))
                    else:
                        merged[key] = song
                result['songs'] = sorted(merged.values(), key=lambda s: s['title'].casefold())
                db['groups'][name] = result
                print(name, len(result['songs']), flush=True)
            elif name not in db['groups']:
                missing.append(name)
    db['collection_report'] = {'unavailable_groups': missing, 'runtime_network': False}
    target.write_text(json.dumps(db, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('COVERAGE', len(db['groups']), '/', len(groups), 'MISSING', missing, flush=True)
