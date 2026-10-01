"""Local identity lookup and bounded YouTube search planning; no UI dependency."""
import datetime as dt
import json
import re
import unicodedata
from urllib.parse import urlencode
from pathlib import Path


def normalize(text):
    return unicodedata.normalize("NFC", "".join(c for c in unicodedata.normalize(
        "NFKD", str(text)).casefold() if c.isalnum() and not unicodedata.combining(c)))


def has_han(text):
    return any(0x3400 <= ord(c) <= 0x9FFF or 0xF900 <= ord(c) <= 0xFAFF
               or 0x20000 <= ord(c) <= 0x3134F for c in str(text))


def matches_name(title, name):
    """Preserve word boundaries: 'Lia' must not match 'Australian', nor 'Rei' 'freight'."""
    if not name or has_han(name):
        return False
    title = unicodedata.normalize("NFC", "".join(c for c in unicodedata.normalize(
        "NFKD", title).casefold() if not unicodedata.combining(c)))
    name = unicodedata.normalize("NFC", "".join(c for c in unicodedata.normalize(
        "NFKD", name).casefold() if not unicodedata.combining(c)))
    if re.search(r"[a-z]", name):
        tokens = re.findall(r"[a-z0-9]+", name)
        if not tokens:
            return False
        # Only adjacent name parts may be joined by a space or one normal separator.
        # Do not bridge ellipses, arbitrary punctuation, other words, or reversed syllables.
        pattern = r"(?:[ \t]+|[-_‐‑–—])?".join(map(re.escape, tokens))
        if "".join(tokens) == "nagyung":
            pattern = r"(?:" + pattern + r"|nag[ \t]+yung)"
        # Unicode word boundaries also reject appended Cyrillic/Hangul letters;
        # ASCII-only boundaries incorrectly accepted names inside mixed-script words.
        return bool(re.search(r"(?<![^\W_])" + pattern + r"(?![^\W_])", title))
    # Never accept a Hangul given name as a substring of another word/person.
    # Common attached fancam labels are a suffix, not part of the identity.
    return bool(name and re.search(r"(?<![^\W_])" + re.escape(name) +
                                  r"(?=$|[^\w]|_|직캠|팬캠|포커스)", title))


def member_display_name(member):
    """Format Korean Romanized full names without modifying identity or Western names."""
    full = member.get("full_name") or member["stage_name"]
    hangul = member.get("full_name_hangul") or ""
    surname = full.split()[0].casefold() if full.split() else ""
    korean_surnames = {"kim", "lee", "yi", "park", "pak", "bak", "choi", "choe", "jung", "jeong", "chung",
        "jang", "chang", "oh", "an", "ahn", "kang", "gang", "shin", "sin", "yoon", "yun", "seo", "suh",
        "han", "baek", "paek", "roh", "ro", "no", "song", "nam", "son", "moon", "mun", "cho", "jo",
        "kwon", "gwon", "lim", "im", "eom", "um", "heo", "huh", "ko", "go", "hwang", "na", "ha",
        "cha", "woo", "yoo", "yu", "seol", "sul", "bae", "sim", "shim"}
    # A Western name can also have a Hangul transcription. That alone does not make
    # it a Korean family-first name; preserve source spelling in that case.
    if surname in korean_surnames and re.fullmatch(r"[가-힣]{3,4}", hangul.replace(" ", "")):
        for raw in member.get("raw_name_fields", {}).values():
            changed = re.search(r"legalized to\s+([A-Za-z][A-Za-z .'-]+)\s*\(", raw)
            if changed:
                full = changed.group(1).strip()
                break
        full = re.sub(r"[-‐‑–—]", " ", full)
        full = re.sub(r"[^A-Za-z\s]", "", full)
        parts = full.split()
        if len(parts) > 1:
            full = parts[0].capitalize() + " " + "".join(parts[1:]).capitalize()
        elif parts:
            full = parts[0].capitalize()
    return full


class IdolCatalogue:
    def __init__(self, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.groups = data["groups"]
        self.members = data["members"]
        self.by_id = {m["id"]: m for m in self.members}
        self.index = data["alias_index"]

    def group_matches(self, text):
        if has_han(text):
            return []
        key = normalize(text)
        if not key:
            return self.groups
        return [g for g in self.groups if any(not has_han(a) and key in normalize(a) for a in
            [g["name"], g.get("korean", ""), *g.get("aliases", [])])]

    def resolve_group(self, text):
        key = normalize(text)
        matches = self.group_matches(text)
        exact = [g for g in matches if key in {normalize(a) for a in
            [g["name"], g.get("korean", ""), *g.get("aliases", [])]}]
        return exact[0] if len(exact) == 1 else matches[0] if len(matches) == 1 else None

    def member_matches(self, text, group=None, exact=False):
        if has_han(text):
            return []
        key = normalize(text)
        return [m for m in self.members if (not group or m["group"] == group) and (
            not key or normalize(member_display_name(m)) == key or any(not has_han(a["text"]) and (a["normalized"] == key if exact
                else key in a["normalized"]) for a in m["aliases"]))]


def date_variants(value):
    if not re.fullmatch(r"\d{6}", value):
        raise ValueError("date_format")
    year, month, day = 2000 + int(value[:2]), int(value[2:4]), int(value[4:])
    try:
        date = dt.date(year, month, day)
    except ValueError:
        raise ValueError("date_format") from None
    return [date.strftime(fmt) for fmt in ("%y%m%d", "%y.%m.%d", "%y-%m-%d",
        "%y/%m/%d", "%Y%m%d", "%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d")]


def search_names(member, group, typed_name):
    if member:
        names = [member["stage_name"], member.get("stage_name_hangul"),
                 member.get("full_name_hangul"), member.get("full_name")]
        # Input prefixes are for identity autocomplete, never search aliases.
        # Selecting Nagyung after typing 'nagy' must not authorize 'Nagy Ferencz'.
        legal_names = [*names, *[a["text"] for a in member["aliases"] if not has_han(a["text"])]]
        if typed_name and normalize(typed_name) in {normalize(a) for a in legal_names if a}:
            names.insert(0, typed_name)
        # Curated spelling variants precede generated transliterations.
        names += [a["text"] for a in member["aliases"] if a["kind"] in (
            "community_variant", "curated_source_variant", "generated_given_name",
            "generated_romanization", "generated_hangul_romanization")]
    else:
        names = [group["name"], group.get("korean"), *group.get("aliases", [])]
    result, seen = [], set()
    for name in names:
        # Keep meaningful surface spellings separate. Search engines may return
        # different results for Nagyung, Na-gyung, Nakyung and Nagyoung.
        key = unicodedata.normalize("NFC", str(name)).strip().casefold()
        if name and not has_han(name) and key not in seen:
            seen.add(key)
            result.append(name)
    return result


def make_search_plan(member, group, typed_name, date, catalogue=None):
    dates = date_variants(date)
    names = search_names(member, group, typed_name)
    # Search every identity spelling with compact and separated 2/4-digit years.
    # Alternate keyword order; local title matching remains global and order-free.
    search_dates = (dates[0], dates[1], dates[4], dates[5])
    queries = []
    for name in names:
        for index, day in enumerate(search_dates):
            queries.append(f"{name} {day}" if index % 2 == 0 else f"{day} {name}")
    queries = list(dict.fromkeys(queries))
    # The dedicated Shorts search works better without a date term. Exact date
    # filtering is still applied to the returned title locally.
    short_queries = list(dict.fromkeys(names))
    return {"names": names, "dates": dates, "queries": queries, "short_queries": short_queries,
            "typed_name": typed_name or group["name"], "date": date,
            "member_id": member["id"] if member else None, "group": group["name"],
            "member": member, "group_names": [group["name"], group.get("korean", ""), *group.get("aliases", [])],
            "other_group_names": [[g["name"], g.get("korean", ""), *g.get("aliases", [])]
                                  for g in catalogue.groups if g["name"] != group["name"]] if catalogue else []}


def search_url(query, shorts=False):
    params = {"search_query": query}
    if shorts:
        # YouTube's Type > Shorts search filter. The value must be double encoded.
        params["sp"] = "EgIQCQ%3D%3D"
    return "https://www.youtube.com/results?" + urlencode(params)


def flatten_search_entries(data):
    if not isinstance(data, dict):
        return []
    if isinstance(data.get("entries"), list):
        return [item for child in data["entries"] for item in flatten_search_entries(child)]
    return [data] if re.fullmatch(r"[A-Za-z0-9_-]{11}", str(data.get("id", ""))) else []


def identity_matches(title, name, plan):
    if not matches_name(title, name):
        return False
    title = unicodedata.normalize("NFKC", title)
    member = plan.get("member")
    if not member:
        return True
    full = member.get("full_name_hangul", "").replace(" ", "")
    given = member.get("stage_name_hangul", "").replace(" ", "")
    # Only apply Korean surname rules when the stage name is the legal given name.
    if not re.fullmatch(r"[가-힣]{3,4}", full) or not given or not full.endswith(given) or full == given:
        return True
    surname = full[:-len(given)]
    # Hashtags often join group and full name, e.g. #트리플에스김나경.
    # Separators or spaced Hangul syllables must not bypass surname validation.
    separator = r"[\s._‐‑–—-]*"
    given_pattern = separator.join(map(re.escape, given))
    wrong = re.findall(r"([김이박최정강조윤장임한오서신권황안송전홍유고문양손배백허남심노하곽성차주우구민진지엄채원천방공현함변염여추도소석선설마길])" + separator + given_pattern, title)
    if any(prefix != surname for prefix in wrong):
        # Explicit wrong surname vetoes an otherwise matching bare given name.
        return False
    latin_surnames = r"kim|lee|yi|park|pak|bak|choi|choe|jung|jeong|chung|jang|chang|oh|an|ahn|kang|gang|shin|sin|yoon|yun|seo|suh|han|baek|paek|roh|ro|no|song|nam|son|moon|mun|cho|jo|kwon|gwon|lim|im|eom|um|heo|huh|ko|go|hwang|na|ha|cha|woo|yoo|yu|seol|sul|bae|sim|shim"
    family = str(member.get("full_name", "")).split()[0].casefold()
    equivalent = {"lee": {"lee", "yi"}, "park": {"park", "pak", "bak"}, "choi": {"choi", "choe"},
                  "jung": {"jung", "jeong", "chung"}, "yoo": {"yoo", "yu"}}.get(family, {family})
    aliases = [a for a in plan["names"] if re.fullmatch(r"[A-Za-z][A-Za-z -]*", a)
               and not a.casefold().startswith(family + " ")]
    for alias in aliases:
        tokens = re.findall(r"[a-z]+", alias.casefold())
        part = separator.join(separator.join(map(re.escape, token)) for token in tokens)
        for match in re.finditer(r"(?<![a-z])(" + latin_surnames + r")" + separator + part + r"(?![a-z])", title.casefold()):
            if match.group(1) not in equivalent:
                return False
        for match in re.finditer(r"(?<![a-z])" + part + r"[\s._‐‑–—-]+(" + latin_surnames + r")(?![a-z])", title.casefold()):
            if match.group(1) not in equivalent:
                return False
    return True


def identity_context_matches(entry, plan):
    """Short ambiguous names need identity evidence, not merely a shared date."""
    member = plan.get("member")
    if not member:
        return True
    title = str(entry.get("title") or "")
    group_in_title = any(matches_name(title, a) for a in plan.get("group_names", []) if a)
    other_in_title = any(matches_name(title, a) for aliases in plan.get("other_group_names", []) for a in aliases if a)
    if other_in_title and not group_in_title:
        return False
    if not entry.get("_is_short") and "/shorts/" not in str(entry.get("webpage_url") or entry.get("url") or ""):
        return True
    full_names = [member.get("full_name"), member.get("full_name_hangul")]
    parts = str(member.get("full_name") or "").split()
    family = parts[0].casefold() if parts else ""
    family_spellings = {"lee": ("lee", "yi", "i"), "park": ("park", "pak", "bak"),
                        "choi": ("choi", "choe"), "jung": ("jung", "jeong", "chung"),
                        "yoo": ("yoo", "yu")}.get(family, (family,))
    full_names += [a for a in plan["names"] if family and any(
        a.casefold().startswith(prefix) and len(a) > len(prefix) for prefix in family_spellings)]
    if group_in_title or any(a and identity_matches(title, a, plan) for a in full_names):
        return True
    # The description/channel may establish the group where the short title does not.
    context = str(entry.get("description") or "") + " " + str(entry.get("uploader") or entry.get("channel") or "")
    return any(matches_name(context, a) for a in plan.get("group_names", []) if a)


def matched_date(title, variant):
    # Separator choices and spaces around them may vary; never match inside a longer date.
    parts = re.split(r"[./-]", variant)
    pattern = r"\s*" + re.escape(variant) + r"\s*"
    if len(parts) == 3:
        pattern = r"\s*[./-]\s*".join(map(re.escape, parts))
    return bool(re.search(r"(?<!\d)" + pattern + r"(?!\d)", title))


def rank_results(entries, plan, require_context=True):
    found = {}
    for entry in entries:
        video_id = str(entry.get("id") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            continue
        title = str(entry.get("title") or "")
        matched_names = [n for n in plan["names"] if identity_matches(title, n, plan)]
        dates = [d for d in plan["dates"] if matched_date(title, d)]
        # Fail closed: YouTube suggestions with missing identity or wrong date never reach the UI.
        if not matched_names or not dates:
            continue
        if require_context and not identity_context_matches(entry, plan):
            continue
        score = (bool(matched_names and dates),
                 matches_name(title, plan["typed_name"]),
                 matched_date(title, plan["date"]),
                 any(matches_name(title, alias) for alias in plan.get("group_names", []) if alias),
                 any(matches_name(title, alias) for alias in (
                     (plan.get("member") or {}).get("full_name", ""),
                     (plan.get("member") or {}).get("full_name_hangul", "")) if alias),
                 bool(dates), bool(matched_names))
        previous = found.get(video_id)
        if previous is None:
            is_short = "/shorts/" in str(entry.get("url", "")) or "/shorts/" in str(entry.get("webpage_url", ""))
            found[video_id] = {**entry, "webpage_url": ("https://www.youtube.com/shorts/" if is_short else "https://www.youtube.com/watch?v=") + video_id,
                              "_score": score, "_order": len(found)}
        else:
            for key, value in entry.items():
                if value and not previous.get(key):
                    previous[key] = value
    return sorted(found.values(), key=lambda e: (e["_score"], -e["_order"]), reverse=True)
