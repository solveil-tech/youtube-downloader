"""Mechanical normalization of the source-attributed local song database."""
import json
import re
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from idol_search import normalize
from song_catalogue import base_track_title

root = Path(__file__).resolve().parent
path = root / 'song_catalogue.json'
db = json.loads(path.read_text(encoding='utf-8'))
for name, supplement in json.loads((root / 'song_supplement.json').read_text(encoding='utf-8')).items():
    db['groups'][name] = {'source': supplement['source'], 'coverage': 'Locally verified selected released songs; partial catalogue',
                         'songs': supplement.get('songs') or [{'title': title, 'aliases': [], 'sources': [supplement['source']]} for title in supplement['titles']]}
for group in db['groups'].values():
    songs = {}
    for song in group['songs']:
        title = song['title'].strip()
        if re.search(r'\b(remixes?|instrumental|karaoke|sped[ -]?up|slowed|remaster|accapella|acca\.|interlude)\b|\bver\.', title, re.I):
            continue
        title = re.sub(r'\s*\([^)]*(?:CD Only|hidden track|edition|Solo|feat\.|with )[^)]*\)|\s*\bCD Only\b', '', title, flags=re.I).strip()
        aliases = list(song.get('aliases', []))
        # Bilingual title annotations become alternate names, not a required combined phrase.
        bilingual = re.fullmatch(r'(.+?)\s*\(([^()]*[가-힣][^()]*)\)', title)
        if bilingual and not re.search(r'[가-힣]', bilingual[1]):
            aliases.append(bilingual[2])
            title = bilingual[1].strip()
        title = base_track_title(title)
        if not title:
            continue
        key = normalize(title)
        item = songs.setdefault(key, {'title': title, 'aliases': [], 'sources': []})
        item['aliases'] = list(dict.fromkeys(item['aliases'] + [a for a in aliases if normalize(a) != key]))
        item['sources'] = list(dict.fromkeys(item['sources'] + song.get('sources', [])))
    group['songs'] = sorted(songs.values(), key=lambda s: s['title'].casefold())
db['collection_report'] = {'runtime_network': False, 'unavailable_groups': [], 'coverage_note': 'All registered groups have entries; individual catalogues are partial, not exhaustive.'}
path.write_text(json.dumps(db, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('LOCAL_GROUPS', len(db['groups']), 'TRACKS', sum(len(g['songs']) for g in db['groups'].values()))
