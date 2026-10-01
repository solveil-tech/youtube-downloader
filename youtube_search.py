"""Read current YouTube search renderers, including Shorts skipped by yt-dlp."""
import json
import re
import requests
from idol_search import search_url

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def text_value(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("content") or value.get("simpleText") or
                   "".join(str(run.get("text", "")) for run in value.get("runs", []) if isinstance(run, dict)))
    return ""


def parse_search_renderers(data, shorts_only=False):
    entries = {}
    for node in objects(data):
        short = node.get("shortsLockupViewModel") or node.get("reelItemRenderer")
        video = node.get("videoRenderer") if not shorts_only else None
        renderer = short or video
        if not isinstance(renderer, dict):
            continue
        endpoints = [obj.get("reelWatchEndpoint", {}) for obj in objects(renderer)]
        video_id = renderer.get("videoId") or next((e.get("videoId") for e in endpoints if e.get("videoId")), None)
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", str(video_id or "")):
            entity = str(renderer.get("entityId", ""))
            video_id = entity.removeprefix("shorts-shelf-item-")
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", str(video_id)):
            continue
        title = text_value(renderer.get("overlayMetadata", {}).get("primaryText")) or text_value(renderer.get("title")) or text_value(renderer.get("headline"))
        if not title:
            title = re.sub(r", (?:No|[\d,.]+(?: (?:thousand|million|billion))?) views? - play Short$", "", str(renderer.get("accessibilityText", "")))
        if not title:
            continue
        thumbnails = []
        for obj in objects(renderer):
            for key in ("sources", "thumbnails"):
                values = obj.get(key, [])
                if isinstance(values, list):
                    thumbnails.extend(t for t in values if isinstance(t, dict) and str(t.get("url", "")).startswith("https://i.ytimg.com/"))
        prefix = "https://www.youtube.com/shorts/" if short else "https://www.youtube.com/watch?v="
        author = text_value(renderer.get("ownerText")) or text_value(renderer.get("longBylineText")) or text_value(renderer.get("shortBylineText"))
        duration = None
        length = text_value(renderer.get("lengthText"))
        if re.fullmatch(r"\d+(?::\d+){1,2}", length):
            duration = 0
            for part in length.split(":"):
                duration = duration * 60 + int(part)
        entries[video_id] = {"id": video_id, "title": title, "url": prefix + video_id,
                             "webpage_url": prefix + video_id, "thumbnails": thumbnails,
                             "uploader": author or None, "duration": duration, "_is_short": bool(short)}
    return list(entries.values())


def initial_data(html):
    match = re.search(r'(?:var\s+ytInitialData\s*=|window\["ytInitialData"\]\s*=|ytInitialData\s*=)\s*', html)
    if not match:
        raise ValueError("YouTube search page contains no result data")
    return json.JSONDecoder().raw_decode(html[match.end():])[0]


def search_config(html):
    result = {}
    for match in re.finditer(r'ytcfg\.set\(\s*', html):
        try:
            value, _ = json.JSONDecoder().raw_decode(html[match.end():])
            if isinstance(value, dict):
                result.update(value)
        except ValueError:
            continue
    return result


def complete_short_metadata(entry, cancelled=lambda: False):
    """Fetch public player metadata, not media/formats; never invent missing fields."""
    if cancelled():
        return entry
    response = requests.get("https://www.youtube.com/watch", params={"v": entry["id"], "hl": "en"},
                            headers={"User-Agent": USER_AGENT}, timeout=(5, 12))
    response.raise_for_status()
    match = re.search(r'(?:var\s+ytInitialPlayerResponse\s*=|ytInitialPlayerResponse\s*=)\s*', response.text)
    if not match:
        raise ValueError("YouTube page contains no player metadata")
    player = json.JSONDecoder().raw_decode(response.text[match.end():])[0]
    details = player.get("videoDetails", {})
    if details.get("videoId") != entry["id"]:
        raise ValueError("YouTube returned metadata for another video")
    micro = player.get("microformat", {}).get("playerMicroformatRenderer", {})
    completed = {**entry, "title": details.get("title") or entry["title"],
                 "uploader": details.get("author") or entry.get("uploader"),
                 "channel": details.get("author"), "channel_id": details.get("channelId"),
                 "description": details.get("shortDescription") or ""}
    length = details.get("lengthSeconds")
    if str(length or "").isdigit():
        completed["duration"] = int(length)
    date = micro.get("uploadDate") or micro.get("publishDate")
    if date and re.match(r"\d{4}-\d{2}-\d{2}", date):
        completed["upload_date"] = date[:10].replace("-", "")
    completed["_metadata_complete"] = bool(completed.get("uploader") and
                                           completed.get("duration") is not None and completed.get("upload_date"))
    return completed


def continuation_token(data):
    for node in objects(data):
        item = node.get("continuationItemRenderer")
        if isinstance(item, dict):
            for endpoint in objects(item):
                token = endpoint.get("continuationCommand", {}).get("token")
                if token:
                    return token
    return None


def search_short_pages(query, cancelled=lambda: False, max_pages=3):
    entries, seen_tokens = {}, set()
    with requests.Session() as session:
        session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-GB,en;q=0.9"})
        response = session.get(search_url(query, shorts=True), params={"hl": "en", "gl": "GB"}, timeout=(5, 12))
        response.raise_for_status()
        data, config = initial_data(response.text), search_config(response.text)
        context = config.get("INNERTUBE_CONTEXT")
        for _ in range(max_pages):
            if cancelled():
                return []
            for entry in parse_search_renderers(data, shorts_only=True):
                entries.setdefault(entry["id"], entry)
            token = continuation_token(data)
            if not token or token in seen_tokens or not isinstance(context, dict):
                break
            seen_tokens.add(token)
            if cancelled():
                return []
            try:
                response = session.post("https://www.youtube.com/youtubei/v1/search", params={"prettyPrint": "false"},
                                        json={"context": context, "continuation": token}, timeout=(5, 12))
                response.raise_for_status()
                data = response.json()
            except (requests.RequestException, ValueError):
                # A failed later page must not discard successful first-page results.
                break
    return list(entries.values())
