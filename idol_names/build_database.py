"""Build a source-traceable search-name database; never edits the downloader.

Run with the project's Python environment. Only name facts are extracted;
profile biographies and images are not redistributed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
import unicodedata

import requests

ROOT = Path(__file__).resolve().parent
AS_OF = "2026-10-01"

# Editorial coverage, not a ranking and not an assertion of current lineups.
# Historical members are deliberately included for archival fancam searches.
GROUPS = [
    ("fromis_9", "프로미스나인", "fromis_9-members-profile", ["fromis9", "fromis 9", "프로미스 9"]),
    ("BLACKPINK", "블랙핑크", "blackpink-members-profile", ["black pink"]),
    ("TWICE", "트와이스", "twice-members-profile", []),
    ("Red Velvet", "레드벨벳", "red-velvet-members-profile", ["redvelvet"]),
    ("aespa", "에스파", "aespa-members-profile", []),
    ("IVE", "아이브", "ive-members-profile", []),
    ("LE SSERAFIM", "르세라핌", "le-sserafim-members-profile", ["lesserafim", "le sserafim"]),
    ("NewJeans", "뉴진스", "newjeans-members-profile", ["new jeans", "NJZ"]),
    ("ITZY", "있지", "itzy-members-profile", []),
    ("NMIXX", "엔믹스", "nmixx-members-profile", []),
    ("i-dle", "아이들", "gidle-members-profile", ["(G)I-DLE", "GIDLE", "G-IDLE", "여자아이들", "(여자)아이들"]),
    ("STAYC", "스테이씨", "stayc-members-profile", []),
    ("BABYMONSTER", "베이비몬스터", "babymonster-members-profile", ["baby monster", "BAEMON", "베몬"]),
    ("ILLIT", "아일릿", "illit-members-profile", []),
    ("KISS OF LIFE", "키스오브라이프", "kiss-of-life-members-profile", ["KIOF", "키오프"]),
    ("MEOVV", "미야오", "meovv-members-profile", []),
    ("Hearts2Hearts", "하츠투하츠", "hearts2hearts-members-profile", ["H2H", "hearts to hearts"]),
    ("KiiiKiii", "키키", "kiiikiii-members-profile", []),
    ("izna", "이즈나", "izna-members-profile", []),
    ("UNIS", "유니스", "unis-members-profile", []),
    ("tripleS", "트리플에스", "triples-members-profile-and-facts", ["triple s"]),
    ("Kep1er", "케플러", "kep1er-members-profile", ["kepler"]),
    ("FIFTY FIFTY", "피프티피프티", "fifty-fifty-members-profile", ["fiftyfifty"]),
    ("Dreamcatcher", "드림캐쳐", "dreamcatcher-members-profile", ["dream catcher", "드림캐처"]),
    ("EVERGLOW", "에버글로우", "everglow-members-profile", []),
    ("MAMAMOO", "마마무", "mamamoo-members-profile", []),
    ("OH MY GIRL", "오마이걸", "oh-my-girl-members-profile", ["ohmygirl", "OMG"]),
    ("WJSN", "우주소녀", "cosmic-girls-wjsn-members-profile", ["Cosmic Girls"]),
    ("LOONA", "이달의 소녀", "loona-members-profile", ["이달의소녀"]),
    ("ARTMS", "아르테미스", "artms-members-profile", []),
    ("Loossemble", "루셈블", "loossemble-members-profile", []),
    ("VIVIZ", "비비지", "viviz-members-profile", []),
    ("GFRIEND", "여자친구", "gfriend-members-profile", ["g friend"]),
    ("Apink", "에이핑크", "apink-members-profile", ["a pink"]),
    ("Girls' Generation", "소녀시대", "girls-generation-snsd-members-profile", ["SNSD", "소시"]),
    ("KARA", "카라", "kara-members-profile", []),
    ("2NE1", "투애니원", "2ne1-members-profile", []),
    ("Wonder Girls", "원더걸스", "wonder-girls-members-profile", ["wondergirls"]),
    ("T-ARA", "티아라", "t-ara-members-profile", ["tara"]),
    ("f(x)", "에프엑스", "fx-members-profile", ["fx"]),
    ("SISTAR", "씨스타", "sistar-members-profile", []),
    ("AOA", "에이오에이", "aoa-members-profile", []),
    ("EXID", "이엑스아이디", "exid-members-profile", []),
    ("Girl's Day", "걸스데이", "girls-day-members-profile", ["girls day", "girlsday"]),
    ("Lovelyz", "러블리즈", "lovelyz-members-profile", []),
    ("Weki Meki", "위키미키", "weki-meki-members-profile", ["wekimeki"]),
    ("IZ*ONE", "아이즈원", "izone-members-profile", ["IZONE", "IZ ONE"]),
    ("I.O.I", "아이오아이", "ioi-members-profile", ["IOI"]),
    ("CLC", "씨엘씨", "clc-members-profile", []),
    ("PURPLE KISS", "퍼플키스", "purple-kiss-members-profile", ["purplekiss"]),
    ("Billlie", "빌리", "billlie-members-profile", []),
    ("woo!ah!", "우아", "wooah-members-profile", ["WOOAH", "woo ah"]),
    ("Weeekly", "위클리", "weeekly-members-profile", []),
    ("Rocket Punch", "로켓펀치", "rocket-punch-members-profile", []),
    ("Cherry Bullet", "체리블렛", "cherry-bullet-members-profile", []),
    ("cignature", "시그니처", "cignature-members-profile", []),
    ("LIGHTSUM", "라잇썸", "lightsum-members-profile", []),
    ("H1-KEY", "하이키", "h1-key-members-profile", ["h1key"]),
    ("BBGIRLS", "브브걸", "bbgirls-members-profile", []),
    ("Brave Girls", "브레이브걸스", "brave-girls-members-profile", []),
    ("CSR", "첫사랑", "csr-members-profile", []),
    ("ICHILLIN'", "아이칠린", "ichillin-members-profile", ["ichillin"]),
    ("CLASS:y", "클라씨", "classy-members-profile", ["CLASSY"]),
    ("NATURE", "네이처", "nature-members-profile", []),
    ("GWSN", "공원소녀", "gwsn-members-profile", []),
    ("DIA", "다이아", "dia-members-profile", []),
    ("APRIL", "에이프릴", "april-members-profile", []),
    ("9MUSES", "나인뮤지스", "nine-muses-members-profile", ["Nine Muses", "9 muses"]),
    ("After School", "애프터스쿨", "after-school-members-profile", ["afterschool"]),
    ("miss A", "미쓰에이", "miss-a-members-profile", ["missa"]),
    ("SECRET", "시크릿", "secret-members-profile", []),
    ("XG", "엑스지", "xg-members-profile", []),
    ("NiziU", "니쥬", "niziu-members-profile", []),
    ("QWER", "큐더블유이알", "qwer-members-profile", []),
    ("SAY MY NAME", "세이마이네임", "say-my-name-members-profile", []),
    ("MADEIN", "메이딘", "madein-members-profile", []),
    ("RESCENE", "리센느", "rescene-members-profile", []),
    ("BADVILLAIN", "배드빌런", "badvillain-members-profile", []),
    ("YOUNG POSSE", "영파씨", "young-posse-members-profile", []),
    ("MOMOLAND", "모모랜드", "momoland-members-profile", []),
    ("PRISTIN", "프리스틴", "pristin-members-profile", []),
    ("gugudan", "구구단", "gugudan-members-profile", []),
    ("4MINUTE", "포미닛", "4minute-members-profile", ["4 minute"]),
    ("Brown Eyed Girls", "브라운아이드걸스", "brown-eyed-girls-members-profile", ["BEG"]),
    ("EL7Z UP", "엘즈업", "el7z-up-members-profile", ["EL7ZUP"]),
    ("LIMELIGHT", "라임라잇", "limelight-members-profile", []),
    ("ALICE", "앨리스", "elris-members-profile", ["ELRIS", "엘리스"]),
    ("LABOUM", "라붐", "laboum-members-profile", []),
    ("Rainbow", "레인보우", "rainbow-members-profile", []),
    ("Dal Shabet", "달샤벳", "dal-shabet-members-profile", ["dalshabet"]),
    ("FIESTAR", "피에스타", "fiestar-members-profile", []),
    ("SPICA", "스피카", "spica-members-profile", []),
    ("BESTie", "베스티", "bestie-members-profile", []),
    ("Ladies' Code", "레이디스 코드", "ladies-code-members-profile", ["ladies code"]),
    ("STELLAR", "스텔라", "stellar-members-profile", []),
    ("Berry Good", "베리굿", "berry-good-members-profile", ["berrygood"]),
    ("S.E.S.", "에스이에스", "ses-members-profile", ["SES"]),
    ("Fin.K.L", "핑클", "fin-k-l-members-profile", ["FINKL"]),
    ("T.T.MA", "티티마", "t-t-ma-members-profile", ["TTMA"]),
    ("TRI.BE", "트라이비", "tri-be-members-profile", ["TRIBE"]),
    ("Lapillus", "라필루스", "lapillus-members-profile", []),
    ("ILY:1", "아일리원", "ily1-members-profile", ["ILY1"]),
    ("KATSEYE", "캣츠아이", "katseye-members-profile", []),
    ("Geenius", "지니어스", "geenius-members-profile", []),
    ("VVUP", "비비업", "vvup-members-profile", []),
    ("PIXY", "픽시", "pixy-members-profile", []),
]

URL_CORRECTIONS = {
    "BLACKPINK": "black-pink-members-profile", "NMIXX": "nmixx-profile",
    "i-dle": "idle-members-profile", "UNIS": "unis-universe-ticket-members-profile",
    "WJSN": "wjsn-cosmic-girls-profile", "GFRIEND": "gfriend-profile-and-facts",
    "Girl's Day": "girls-day-profile", "Cherry Bullet": "cherry-bullet-profile",
    "GWSN": "gwsn-profile", "9MUSES": "9muses-members-profile",
    "miss A": "miss-a-profile",
    "Brown Eyed Girls": "brown-eyed-girls-profile", "S.E.S.": "s-e-s-members-profile",
}
GROUPS = [(n, k, URL_CORRECTIONS.get(n, s), a) for n, k, s, a in GROUPS]

SUPPLEMENT_PAGES = {"9MUSES": ["9muses-former-members"]}


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if tag in ("br", "p", "div", "h1", "h2", "h3", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        if tag in ("p", "div", "h1", "h2", "h3", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def normalize(value):
    value = unicodedata.normalize("NFKD", value).casefold()
    return unicodedata.normalize("NFC", "".join(c for c in value if c.isalnum() and not unicodedata.combining(c)))


def split_name(value):
    value = unicodedata.normalize("NFC", value)
    latin = re.split(r"[（(/,]", value)[0].strip().rstrip("*†")
    korean = re.findall(r"[가-힣]+(?: [가-힣]+)*", value)
    return latin, korean[0] if korean else ""


def fetch_group(group):
    name, korean, slug, group_aliases = group
    url = f"https://kprofiles.com/{slug}/"
    response = requests.get(url, timeout=(12, 35))
    response.raise_for_status()
    parser = TextParser()
    # Ignore navigation, related posts, and comment-submitted corrections.
    match = re.search(r'<div[^>]+class="[^"]*entry-content[^\"]*"[^>]*>', response.text)
    content = response.text[match.end():] if match else response.text
    content = re.split(r'<(?:div|section)[^>]+(?:id|class)="[^"]*(?:comments|related-posts)', content)[0]
    parser.feed(content)
    lines = [re.sub(r"\s+", " ", x).strip() for x in "".join(parser.parts).splitlines() if x.strip()]
    records = []
    current = None
    historical = False
    for i, line in enumerate(lines):
        if re.match(r"Former (?:Members|Member|Pre.Debut)|Past Members", line, re.I):
            historical = True
        stage = re.match(r"(?:(?:Current )?Stage(?:\s*/\s*(?:Birth|Korean))? Name(?:s)?|Name)\s*:\s*(.+)", line, re.I)
        if stage:
            if current and not current["fields"] and i > 0 and re.match(r"Stage Name:", lines[i-1]):
                current["fields"]["birth name"] = stage.group(1)
                continue
            current = {"group": name, "stage_raw": stage.group(1), "fields": {},
                       "historical_section": historical, "source_url": response.url}
            if re.match(r"Stage\s*/\s*Birth", line):
                current["fields"]["birth name"] = stage.group(1)
            records.append(current)
        else:
            field = re.match(r"(Birth Name|Legal Name|Full Name|Korean Name|Korean Birth Name|Japanese Name|Chinese Birth Name|Chinese Name|Real Name|Former Stage Name)\s*:\s*(.+)", line, re.I)
            if field:
                previous = lines[i-1] if i else ""
                if (field.group(1).lower() in ("birth name", "legal name", "real name")
                        and previous and len(previous) < 45
                        and re.fullmatch(r"[A-Za-zÀ-ž .’'\-]+", previous)
                        and not re.search(r"(?:facts|profiles|members)", previous, re.I)):
                    korean_name = split_name(field.group(2))[1]
                    current = {"group": name, "stage_raw": previous + (f" ({korean_name})" if korean_name else ""),
                               "fields": {}, "historical_section": historical, "source_url": response.url}
                    records.append(current)
                if current:
                    current["fields"][field.group(1).lower()] = field.group(2)
    unique = {}
    for rec in records:
        key = normalize(split_name(rec["stage_raw"])[0])
        if key and key not in unique:
            unique[key] = rec
    return {"name": name, "korean": korean, "aliases": list(dict.fromkeys([name, korean] + group_aliases)),
            "source_url": response.url, "records": list(unique.values())}


# Conservative variants. These are search candidates, not verified stage names.
# In particular do NOT globally equate seung/sung, eun/un, or unrelated nicknames.
REPLACEMENTS = [
    ("gyung", ["gyeong", "kyung", "kyeong"]),
    ("gyeong", ["gyung", "kyung", "kyeong"]),
    ("kyung", ["gyung", "gyeong", "kyeong"]),
    ("hyun", ["hyeon"]), ("hyeon", ["hyun"]),
    ("young", ["yeong"]), ("yeong", ["young"]),
    ("jung", ["jeong"]), ("jeong", ["jung"]),
    ("soo", ["su"]), ("yoo", ["yu"]), ("woo", ["u"]),
]
SURNAMES = {"lee": ["yi", "i"], "park": ["bak", "pak"], "kim": ["gim"],
            "choi": ["choe"], "jung": ["jeong"], "jeong": ["jung"],
            "cho": ["jo"], "jo": ["cho"], "lim": ["im"], "im": ["lim"],
            "roh": ["noh", "no"], "noh": ["roh", "no"], "baek": ["paek"],
            "kwon": ["gwon"], "jang": ["chang"], "oh": ["o"], "yoon": ["yun"]}
KOREAN_SURNAMES = set(SURNAMES) | {"song", "kang", "han", "jin", "hwang", "kwak", "gong", "jeon", "shin", "cha", "bae", "son", "koo", "goo", "eom", "go", "nam", "moon", "hong", "heo", "huh", "hur", "an", "ahn", "na", "yu", "yeo", "yang", "seo", "so", "seong", "pyo", "chu", "woo", "min", "sim", "youn"}


def romanize_hangul(text):
    # Syllable transliteration only. Not a claim about an artist's preferred spelling.
    initials = ("g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h")
    vowels = ("a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i")
    finals = ("", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "p", "l", "l", "p", "l", "m", "p", "p", "t", "t", "ng", "t", "t", "k", "t", "p", "t")
    parts = []
    for char in text:
        number = ord(char) - 0xAC00
        if not 0 <= number < 11172:
            return ""
        parts.append(initials[number // 588] + vowels[number // 28 % 21] + finals[number % 28])
    return "".join(parts)


def aliases_for(rec):
    aliases = {}

    def add(text, kind, priority, evidence):
        text = text.strip()
        key = (text.casefold(), kind)
        if not text or key in aliases:
            return
        aliases[key] = {"text": text, "normalized": normalize(text), "kind": kind,
                        "priority": priority, "evidence": evidence}

    stage, stage_ko = split_name(rec["stage_raw"])
    add(stage, "source_stage", 100, rec["source_url"])
    if stage_ko:
        add(stage_ko, "source_stage_hangul", 100, rec["source_url"])
    def add_alternate_parts(raw):
        raw = unicodedata.normalize("NFC", raw)
        for part in re.split(r"(?:formerly(?: known as)?|legally changed (?:it|her name) to|legalized her name to|but legally changed it to|/)", raw, flags=re.I)[1:]:
            latin, ko = split_name(part.strip(" ,"))
            if latin and re.fullmatch(r"[A-Za-zÀ-ž .’'\-]+", latin):
                add(latin, "source_alternate_name", 90, rec["source_url"])
            if ko:
                add(ko, "source_alternate_hangul", 90, rec["source_url"])
    add_alternate_parts(rec["stage_raw"])
    for extra in rec.get("supplemental_names", []):
        latin, korean = split_name(extra["stage_raw"])
        add(latin, "source_historical_stage", 95, extra["source_url"])
        if korean:
            add(korean, "source_historical_hangul", 95, extra["source_url"])
        for raw in extra["fields"].values():
            latin, korean = split_name(raw)
            add(latin, "source_historical_full", 90, extra["source_url"])
            if korean:
                add(korean, "source_historical_hangul", 90, extra["source_url"])
    full = ""
    full_ko = ""
    for label, value in rec["fields"].items():
        # Some community pages assign playful Korean "names" to foreign members.
        # Keep raw evidence, but don't turn those assignments into search identities.
        if label == "korean name" and rec["group"] not in ("WJSN", "Red Velvet", "KARA", "miss A"):
            continue
        add_alternate_parts(value)
        latin, hangul = split_name(value)
        add(latin, "source_" + label.replace(" ", "_"), 90, rec["source_url"])
        if hangul:
            add(hangul, "source_hangul", 95, rec["source_url"])
        if label in ("legal name", "birth name", "full name", "real name") and not full:
            full, full_ko = latin, hangul
    if not full:
        for label in ("chinese birth name", "chinese name", "korean name"):
            if label in rec["fields"]:
                full, full_ko = split_name(rec["fields"][label])
                break

    # Formatting variants preserve identity; romanizations remain explicitly inferred.
    for alias in list(aliases.values()):
        if not re.search(r"[A-Za-z]", alias["text"]):
            continue
        value = re.sub(r"[‐‑–—]", "-", alias["text"])
        compact = re.sub(r"[\s.\-'’]", "", value)
        spaced = re.sub(r"[-]", " ", value)
        for text in (compact, spaced):
            if text.casefold() != alias["text"].casefold():
                add(text, "generated_format", 85, "remove separators / split hyphens")

    bases = [stage]
    if full:
        bases.append(full)
        parts = full.split()
        # Only infer Korean given names when a Hangul full name is available.
        if full_ko and len(parts) > 1:
            given = " ".join(parts[1:])
            add(given, "generated_given_name", 80, "given name candidate by removing first name token")
            add(normalize(given), "generated_format", 80, "given name without separators")
            if len(full_ko.replace(" ", "")) in (3, 4) and full_ko[0] in "김이박최정강조윤장임한오서신권황안송전홍유고문양손배백허심노하주차우진곽성구남나민":
                add(full_ko.replace(" ", "")[1:], "generated_given_hangul", 80, "Hangul family-name removal; candidate only")
            bases.append(given)
            for surname in SURNAMES.get(parts[0].casefold(), []):
                add(surname + " " + given, "generated_romanization", 50, "family-name spelling variant")
                add(surname + normalize(given), "generated_romanization", 50, "family-name spelling variant")
            if parts[0].casefold() in KOREAN_SURNAMES and len(full_ko.replace(" ", "")) in (3, 4):
                given_ko = full_ko.replace(" ", "")[1:]
                roman = romanize_hangul(given_ko)
                if roman:
                    add(roman, "generated_hangul_romanization", 55, "syllable transliteration; not a verified artist spelling")
                    bases.append(roman)
    for base in bases:
        compact = normalize(base)
        for old, replacements in REPLACEMENTS:
            if old in compact:
                for new in replacements:
                    add(compact.replace(old, new), "generated_romanization", 60,
                        f"search expansion: {old} -> {new}; not an attested alias")
    return stage, stage_ko, full, full_ko, list(aliases.values())


def build(results, failures):
    members = []
    groups = []
    for result in results:
        groups.append({k: v for k, v in result.items() if k != "records"})
        for rec in result["records"]:
            stage, stage_ko, full, full_ko, aliases = aliases_for(rec)
            members.append({"id": normalize(rec["group"]) + ":" + normalize(stage),
                            "group": rec["group"], "stage_name": stage,
                            "stage_name_hangul": stage_ko, "full_name": full,
                            "full_name_hangul": full_ko,
                            "historical_section": rec["historical_section"],
                            "verification": "community_profile_extracted",
                            "source_url": rec["source_url"], "raw_name_fields": rec["fields"],
                            "aliases": aliases})
    # User-requested spelling has independent community evidence.
    for member in members:
        if member["group"] == "fromis_9" and normalize(member["stage_name"]) == "nagyung":
            for text in ("Nakyung", "Lee Nakyung", "leenakyung"):
                member["aliases"].append({"text": text, "normalized": normalize(text),
                    "kind": "community_variant", "priority": 90,
                    "evidence": "https://www.reddit.com/r/nakyung/"})

    official_checks = [
        ("TWICE", "https://www.twicejapan.com/feature/profile", ["Nayeon", "Jeongyeon", "Momo", "Sana", "Jihyo", "Mina", "Dahyun", "Chaeyoung", "Tzuyu"]),
        ("LE SSERAFIM", "https://www.le-sserafim.jp/profile", ["Kim Chaewon", "Kim Chae Won", "Sakura", "Huh Yunjin", "Huh Yun Jin", "Kazuha", "Hong Eunchae", "Hong Eun Chae"]),
        ("IVE", "https://www.sonymusic.co.jp/artist/IVE/profile/", ["Yujin", "Gaeul", "Rei", "Wonyoung", "Liz", "Leeseo"]),
    ]
    for group, url, names in official_checks:
        for name in names:
            matches = [m for m in members if m["group"] == group and normalize(name) in {a["normalized"] for a in m["aliases"]}]
            if len(matches) == 1:
                matches[0]["aliases"].append({"text": name, "normalized": normalize(name),
                    "kind": "official_stage", "priority": 110, "evidence": url})

    overrides = ROOT / "curated_overrides.json"
    if overrides.exists():
        for correction in json.loads(overrides.read_text(encoding="utf-8")):
            member = next((m for m in members if m["id"] == correction["member_id"]), None)
            if member is None:
                raise ValueError("Override member missing: " + correction["member_id"])
            for field, value in correction.get("set_fields", {}).items():
                member[field] = value
            removed = {normalize(x) for x in correction.get("remove_aliases", [])}
            member["aliases"] = [a for a in member["aliases"] if a["normalized"] not in removed]
            for alias in correction.get("aliases", []):
                member["aliases"].append({"text": alias["text"], "normalized": normalize(alias["text"]),
                    "kind": alias.get("kind", "curated_source_variant"), "priority": 95,
                    "evidence": alias["source_url"]})

    from chinese_support import enrich_chinese_names, save_chinese_sql
    chinese_summary = enrich_chinese_names(members, ROOT, normalize)
    index = {}
    for member in members:
        for alias in member["aliases"]:
            index.setdefault(alias["normalized"], set()).add(member["id"])
    collisions = {key: sorted(ids) for key, ids in index.items() if len(ids) > 1}
    data = {"schema_version": 2, "as_of": AS_OF, "chinese_summary": chinese_summary,
            "coverage_policy": "Editorial selection of mainstream/recent/archival girl groups; current and historical profile entries. Not exhaustive or a current-roster authority.",
            "source_policy": "Names from community profiles; generated aliases are marked separately. Nicknames/English fun names are excluded unless curated. Cross-group identities are not auto-merged.",
            "groups": groups, "members": members, "alias_index": {k: sorted(v) for k, v in index.items()},
            "ambiguous_aliases": collisions, "fetch_failures": failures}
    (ROOT / "idol_aliases.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    database_path = ROOT / "idol_aliases.sqlite"
    conn = sqlite3.connect(database_path)
    # Transactional rebuild of our generated tables; preserve other tables.
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS groups (name TEXT PRIMARY KEY, hangul TEXT, aliases_json TEXT, source_url TEXT);
        CREATE TABLE IF NOT EXISTS members (id TEXT PRIMARY KEY, group_name TEXT, stage_name TEXT, stage_hangul TEXT, full_name TEXT, full_hangul TEXT, historical_section INTEGER, verification TEXT, source_url TEXT);
        CREATE TABLE IF NOT EXISTS aliases (member_id TEXT, text TEXT, normalized TEXT, kind TEXT, priority INTEGER, evidence TEXT, PRIMARY KEY(member_id,text,kind));
        CREATE INDEX IF NOT EXISTS aliases_lookup ON aliases(normalized);
        DELETE FROM metadata; DELETE FROM groups; DELETE FROM members; DELETE FROM aliases;
        """)
        conn.executemany("INSERT INTO metadata VALUES (?,?)", [("as_of", AS_OF), ("schema_version", "2"), ("coverage_policy", data["coverage_policy"]), ("chinese_summary", json.dumps(chinese_summary, ensure_ascii=False))])
        save_chinese_sql(conn, members)
        for g in groups:
            conn.execute("INSERT INTO groups VALUES (?,?,?,?)", (g["name"], g["korean"], json.dumps(g["aliases"], ensure_ascii=False), g["source_url"]))
        for m in members:
            conn.execute("INSERT INTO members VALUES (?,?,?,?,?,?,?,?,?)", (m["id"], m["group"], m["stage_name"], m["stage_name_hangul"], m["full_name"], m["full_name_hangul"], int(m["historical_section"]), m["verification"], m["source_url"]))
            for a in m["aliases"]:
                conn.execute("INSERT OR IGNORE INTO aliases VALUES (?,?,?,?,?,?)", (m["id"], a["text"], a["normalized"], a["kind"], a["priority"], a["evidence"]))
    conn.close()
    render_table(data)
    render_coverage(data)
    print(json.dumps({"groups": len(groups), "members": len(members), "alias_rows": sum(len(m["aliases"]) for m in members), "ambiguous_keys": len(collisions), "chinese": chinese_summary, "failures": failures}, ensure_ascii=False))


def render_coverage(data):
    from collections import Counter
    counts = Counter(m["group"] for m in data["members"])
    kinds = Counter(a["kind"] for m in data["members"] for a in m["aliases"])
    source_urls = {m["source_url"] for m in data["members"]}
    for m in data["members"]:
        source_urls.update(a["evidence"] for a in m["aliases"] if a["evidence"].startswith("https://"))
    generated = sum(n for kind, n in kinds.items() if kind.startswith("generated"))
    lines = ["# 覆盖清单与核对报告", "", f"数据日期：{AS_OF}", "",
             f"- 团体：{len(data['groups'])}", f"- 团体—成员记录：{len(data['members'])}（包含同一人跨团重复记录）",
             f"- 别名记录：{sum(kinds.values())}（不是去重拼写数）",
             f"- 来源支持别名记录：{sum(kinds.values()) - generated}",
             f"- 生成候选记录：{generated}",
             f"- 共享匹配键：{len(data['ambiguous_aliases'])}（含同一人跨团记录和真正同名者）",
             f"- 未解决页面读取失败：{len(data['fetch_failures'])}", "",
             "每团数量代表收录记录，不代表当前团体人数。历史、出道前及改名记录以原资料内容为依据。", "",
             "| 团体 | 团体韩文检索名 | 收录记录数 | 原始来源 |", "| --- | --- | ---: | --- |"]
    for g in data["groups"]:
        lines.append(f"| {g['name']} | {g['korean']} | {counts[g['name']]} | [资料]({g['source_url']}) |")
    chinese = data["chinese_summary"]
    lines.extend(["", "## 中文名首批补充", "",
                  f"- 已补充：{chinese['coverage']} 条团体—成员记录；待补充：{chinese['pending']}",
                  f"- 官方账号实际用法：{chinese['official_usage']}；已取得明确正名证据：{chinese['official_confirmed']}",
                  "- 官方账号用法不等于法定汉字或唯一正名；社区资料不会标成官方确认。",
                  "- 频次仅统计所列不同来源页面，同页面重复、转载或繁简转换不增加票数；不是全网流行度。",
                  "- 相同等级、相同来源页数时采用人工排列顺序，不声称哪个更常见。", "",
                  "## 所有引用页面", ""])
    for url in sorted(source_urls):
        lines.append(f"- [{url}]({url})")
    (ROOT / "覆盖与来源.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_table(data):
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    template = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>女团成员姓名别名数据库</title><style>
body{margin:24px;font:14px/1.6 system-ui,"Microsoft YaHei",sans-serif;color:#232730;background:#f6f7fa}h1{font-size:24px;margin-bottom:4px}p{color:#626b7c}input,select{padding:10px;border:1px solid #ccd2de;border-radius:8px;background:white;margin-right:8px}input{width:340px;max-width:75vw}table{border-collapse:collapse;width:100%;background:white}th,td{padding:10px 12px;border-bottom:1px solid #e5e8ef;text-align:left;vertical-align:top}th{position:sticky;top:0;background:#e9edf5}small{color:#727a89}a{color:#4265b5}.tag{display:inline-block;margin:2px 4px 2px 0;padding:1px 6px;border-radius:4px;background:#edf1f9}.generated{background:#fff1d9}.conflict{color:#a64a2f}details{max-width:520px}summary{cursor:pointer}.controls{margin:18px 0}#count{margin:12px 0}</style>
<h1>女团成员姓名别名数据库</h1><p>核对日期：2026-10-01。团体资料页包含的现任及历史成员均保留；不是现役名单。灰蓝为来源姓名，黄色为生成的搜索候选。点击别名可核对依据。</p>
<div class="controls"><input id="query" placeholder="搜索团体、中英韩文姓名，例如 李娜炅"><select id="group"><option value="">全部团体</option></select><label><input id="ambiguous" type="checkbox" style="width:auto">仅显示同名冲突</label></div><div id="count"></div>
<table><thead><tr><th>团体</th><th>英文艺名 / 韩文</th><th>中文显示名 / 依据</th><th>英文全名 / 韩文全名</th><th>来源姓名 / 常见写法</th><th>生成候选及冲突</th><th>资料</th></tr></thead><tbody id="rows"></tbody></table>
<script>const db=__DATA__;const q=document.getElementById('query'),g=document.getElementById('group'),amb=document.getElementById('ambiguous');
const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const norm=s=>s.normalize('NFKD').toLowerCase().replace(/\\p{M}/gu,'').replace(/[^\\p{L}\\p{N}]/gu,'').normalize('NFC');
for(const x of db.groups){let o=document.createElement('option');o.value=x.name;o.textContent=x.name+' · '+x.korean;g.appendChild(o)}
function tag(a){let gen=a.kind.startsWith('generated');let title=a.kind+' | '+a.evidence;let t='<span class="tag '+(gen?'generated':'')+'" title="'+esc(title)+'">'+esc(a.text)+'</span>';return a.evidence.startsWith('https://')?'<a target="_blank" rel="noopener" href="'+esc(a.evidence)+'">'+t+'</a>':t}
function chinese(m){let status={pending:'待核对',community_usage:'社区资料，未确认官方',official_usage:'官方账号用法，非正名证明',official_confirmed:'明确官方正名'}[m.chinese_name_status];return esc(m.chinese_name||'—')+'<br><small>'+esc(status)+'</small>'+(m.chinese_names.length?'<details><summary>中文写法及依据</summary>'+m.chinese_names.map(n=>esc(n.text)+' · '+n.sources.map(s=>'<a target="_blank" rel="noopener" href="'+esc(s.url)+'">'+esc(s.id)+'</a>').join(' / ')).join('<br>')+'</details>':'')}
function draw(){const term=norm(q.value);let members=db.members.filter(m=>(!g.value||m.group===g.value)&&(!term||norm(m.group).includes(term)||m.aliases.some(a=>a.normalized.includes(term)))&&(!amb.checked||m.aliases.some(a=>db.ambiguous_aliases[a.normalized])));document.getElementById('count').textContent=`${members.length} / ${db.members.length} 条成员记录 · ${db.groups.length} 个团体`;
document.getElementById('rows').innerHTML=members.map(m=>{let sourced=m.aliases.filter(a=>!a.kind.startsWith('generated')),gen=m.aliases.filter(a=>a.kind.startsWith('generated')),coll=[...new Set(m.aliases.filter(a=>db.ambiguous_aliases[a.normalized]).map(a=>a.normalized))];return '<tr><td>'+esc(m.group)+'</td><td>'+esc(m.stage_name)+'<br><small>'+esc(m.stage_name_hangul)+'</small></td><td>'+chinese(m)+'</td><td>'+esc(m.full_name)+'<br><small>'+esc(m.full_name_hangul)+'</small></td><td>'+sourced.map(tag).join(' ')+'</td><td><details><summary>'+gen.length+' 个生成写法</summary>'+gen.map(tag).join(' ')+'</details>'+(coll.length?'<details class="conflict"><summary>'+coll.length+' 个共享匹配键</summary>'+coll.map(k=>esc(k)+': '+esc(db.ambiguous_aliases[k].join(', '))).join('<br>')+'</details>':'')+'</td><td><a target="_blank" rel="noopener" href="'+esc(m.source_url)+'">来源</a><br><small>社区资料提取<br>'+esc(m.id)+'</small></td></tr>'}).join('')}
q.addEventListener('input',draw);g.addEventListener('change',draw);amb.addEventListener('change',draw);draw();</script></html>'''
    (ROOT / "姓名别名表.html").write_text(template.replace("__DATA__", payload), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Refetch the name-only cache")
    parser.add_argument("--inspect", nargs="+", help="Print source name labels for manual extraction review")
    args = parser.parse_args()
    if args.inspect:
        for slug in args.inspect:
            response = requests.get(f"https://kprofiles.com/{slug}/", timeout=35)
            p = TextParser()
            p.feed(response.text)
            print(slug)
            for line in "".join(p.parts).splitlines():
                if re.search(r"(?:Name|이름)\s*:", line):
                    print(line.strip())
            if slug.startswith("triples"):
                lines = [x.strip() for x in "".join(p.parts).splitlines() if x.strip()]
                for i, line in enumerate(lines):
                    if re.match(r"(?:Birth|Legal) Name:", line):
                        print("CONTEXT", lines[max(0, i-3):i+1])
        return
    cache = ROOT / "source_names.json"
    if cache.exists() and not args.refresh:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        build(cached["results"], cached["failures"])
        return
    results, failures = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_with_supplements, group): group for group in GROUPS}
        for future in as_completed(futures):
            group = futures[future]
            try:
                result = future.result()
                if not result["records"]:
                    raise ValueError("No stage-name records; needs manual source review")
                results.append(result)
                print(f'{group[0]}: {len(result["records"])}', flush=True)
            except Exception as exc:
                failures.append({"group": group[0], "url": f"https://kprofiles.com/{group[2]}/", "error": str(exc)})
                print(f"REVIEW {group[0]}: {exc}", flush=True)
    order = {g[0]: i for i, g in enumerate(GROUPS)}
    results.sort(key=lambda r: order[r["name"]])
    cache.write_text(json.dumps({"as_of": AS_OF, "results": results, "failures": failures}, ensure_ascii=False, indent=2), encoding="utf-8")
    build(results, failures)


def fetch_with_supplements(group):
    result = fetch_group(group)
    for slug in SUPPLEMENT_PAGES.get(group[0], []):
        supplement = fetch_group((group[0], group[1], slug, group[3]))
        for rec in supplement["records"]:
            rec["historical_section"] = True
            candidate_full = [normalize(split_name(v)[0]) for k, v in rec["fields"].items() if k in ("birth name", "real name", "full name")]
            match = next((r for r in result["records"] if any(normalize(split_name(v)[0]) in candidate_full for k, v in r["fields"].items() if k in ("birth name", "real name", "full name"))), None)
            if match:
                match.setdefault("supplemental_names", []).append(rec)
            else:
                result["records"].append(rec)
    return result


if __name__ == "__main__":
    main()
