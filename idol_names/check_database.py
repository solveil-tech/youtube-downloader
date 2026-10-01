"""Check generated data integrity and key search-name regressions."""
from collections import Counter
import json
from pathlib import Path
import sqlite3

from build_database import normalize

ROOT = Path(__file__).resolve().parent
data = json.loads((ROOT / "idol_aliases.json").read_text(encoding="utf-8"))
members = {m["id"]: m for m in data["members"]}
assert len(members) == len(data["members"]), "Duplicate member IDs"
assert not data["fetch_failures"], "Unresolved source fetches"

counts = Counter(m["group"] for m in members.values())
expected = {"fromis_9": 9, "TWICE": 9, "BLACKPINK": 4, "IVE": 6,
            "LE SSERAFIM": 6, "tripleS": 24, "WJSN": 13,
            "9MUSES": 14, "IZ*ONE": 12, "LOONA": 12, "Weeekly": 7}
for group, count in expected.items():
    assert counts[group] == count, (group, counts[group], count)

required = {
    "nagyung": "fromis9:nagyung",
    "nakyung": "fromis9:nagyung",
    "leenagyung": "fromis9:nagyung",
    "Lee Na-gyung": "fromis9:nagyung",
    "Lee Na Gyung": "fromis9:nagyung",
    "이나경": "fromis9:nagyung",
    "나경": "fromis9:nagyung",
    "Kyungri": "9muses:gyeongree",
    "Euaerin": "9muses:euerin",
    "Hyuna": "9muses:moon",
    "Monday": "weeekly:lunedi",
    "Haram": "babymonster:rami",
    "Olivia Hye": "loona:hyeju",
    "LE": "exid:elly",
    "선예": "wondergirls:sunye",
    "선의": "wjsn:xuanyi",
    "Yujin": "ive:anyujin",
    "李娜炅": "fromis9:nagyung",
    "娜炅": "fromis9:nagyung",
    "李采映": "fromis9:chaeyoung",
    "李彩煐": "fromis9:chaeyoung",
    "白知憲": "fromis9:jiheon",
    "白知宪": "fromis9:jiheon",
    "张员瑛": "ive:jangwonyoung",
    "張員瑛": "ive:jangwonyoung",
    "金玟庭": "aespa:winter",
    "金旼炡": "aespa:winter",
    "宫脇咲良": "lesserafim:sakura",
    "許允眞": "lesserafim:huhyunjin",
    "许允真": "lesserafim:huhyunjin",
    "允真": "lesserafim:huhyunjin",
}
for alias, member_id in required.items():
    assert member_id in data["alias_index"].get(normalize(alias), []), (alias, member_id)

assert "wondergirls:sunye" not in data["alias_index"].get(normalize("순예"), [])
assert len(data["alias_index"][normalize("김채원")]) >= 3, "Same full-name identities must remain separate"
for key, ids in data["alias_index"].items():
    assert ids and all(member_id in members for member_id in ids)
    assert len(ids) == len(set(ids))
    for member_id in ids:
        assert any(a["normalized"] == key for a in members[member_id]["aliases"])
for member in members.values():
    assert member["stage_name_hangul"], member["id"]
    assert member["chinese_name_status"] in {"pending", "community_usage", "official_usage", "official_confirmed"}
    assert bool(member["chinese_name"]) == bool(member["chinese_names"])
    for candidate in member["chinese_names"]:
        assert candidate["sources"] and candidate["cited_page_count"] >= 1
        if candidate["status"].startswith("official"):
            assert any(s["type"].startswith("official") for s in candidate["sources"])
    for alias in member["aliases"]:
        assert alias["text"] and alias["normalized"] == normalize(alias["text"])
        assert alias["evidence"], (member["id"], alias)

conn = sqlite3.connect(ROOT / "idol_aliases.sqlite")
assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
assert conn.execute("SELECT count(*) FROM members").fetchone()[0] == len(members)
assert conn.execute("SELECT count(*) FROM member_chinese").fetchone()[0] == len(members)
assert data["schema_version"] == 2
assert members["fromis9:chaeyoung"]["chinese_name"] == "李采映"
assert members["aespa:winter"]["chinese_name_status"] == "community_usage"
assert data["chinese_summary"]["coverage"] == 39
for member in members.values():
    sql_row = conn.execute("SELECT display_name,status,candidates_json FROM member_chinese WHERE member_id=?", (member["id"],)).fetchone()
    assert sql_row[:2] == (member["chinese_name"], member["chinese_name_status"])
    assert json.loads(sql_row[2]) == member["chinese_names"]
for alias in ("李娜炅", "白知宪", "張員瑛", "许允真"):
    rows = {r[0] for r in conn.execute("SELECT DISTINCT member_id FROM aliases WHERE normalized=?", (normalize(alias),))}
    assert rows == set(data["alias_index"][normalize(alias)])
sql_matches = {x[0] for x in conn.execute("SELECT DISTINCT member_id FROM aliases WHERE normalized=?", (normalize("Nakyung"),))}
assert sql_matches == set(data["alias_index"][normalize("Nakyung")])
alias_count = conn.execute("SELECT count(*) FROM aliases").fetchone()[0]
print(f"CHECK_OK groups={len(data['groups'])} membership_records={len(members)} aliases={alias_count}")
for alias in ("leenagyung", "nakyung", "김채원", "Monday", "Kyungri", "李娜炅", "李彩煐", "白知宪"):
    print(alias, "=>", data["alias_index"].get(normalize(alias), []))
conn.close()
