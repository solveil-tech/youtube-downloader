"""Sourced Chinese display names; keep attestations separate from script conversions."""
import json
from pathlib import Path

STATUS_RANK = {"community_usage": 1, "official_usage": 2, "official_confirmed": 3}


def enrich_chinese_names(members, root, normalize):
    catalogue = json.loads((Path(root) / "chinese_names.json").read_text(encoding="utf-8"))
    by_id = {m["id"]: m for m in members}
    for member in members:
        member.update(chinese_name=None, chinese_name_status="pending",
                      chinese_name_selection=None, chinese_names=[])
    for batch in catalogue["batches"]:
        source = catalogue["sources"][batch["source"]]
        status = batch["status"]
        if status not in STATUS_RANK:
            raise ValueError("Unknown Chinese name status: " + status)
        if status.startswith("official") and source["type"] not in (
                "official_account_usage", "official_name_confirmation"):
            raise ValueError("Community sources cannot confirm official names")
        if status == "official_confirmed" and source["type"] != "official_name_confirmation":
            raise ValueError("Official usage is not proof of a confirmed Hanzi name")
        for member_id, spelling, simplified in batch["names"]:
            if member_id not in by_id:
                raise ValueError("Chinese name member missing: " + member_id)
            member = by_id[member_id]
            candidate = next((n for n in member["chinese_names"] if n["text"] == spelling), None)
            if candidate is None:
                candidate = {"text": spelling, "display_simplified": simplified,
                             "status": status, "sources": []}
                member["chinese_names"].append(candidate)
            elif candidate["display_simplified"] != simplified:
                raise ValueError("Inconsistent Chinese script conversion: " + spelling)
            if STATUS_RANK[status] > STATUS_RANK[candidate["status"]]:
                candidate["status"] = status
            evidence = {"id": batch["source"], **source}
            if evidence not in candidate["sources"]:
                candidate["sources"].append(evidence)

    for member in members:
        candidates = member["chinese_names"]
        if not candidates:
            continue
        # Combine only explicitly curated simplified equivalents, not unrelated Hanzi.
        support = {}
        for candidate in candidates:
            key = candidate["display_simplified"]
            support.setdefault(key, set()).update(s["url"] for s in candidate["sources"])
            candidate["cited_page_count"] = len({s["url"] for s in candidate["sources"]})
        winner = max(candidates, key=lambda n: (
            STATUS_RANK[n["status"]], len(support[n["display_simplified"]])))
        member.update(chinese_name=winner["display_simplified"],
                      chinese_name_status=winner["status"],
                      chinese_name_selection="evidence tier, distinct cited pages, curated order on ties")
        existing = {(a["text"], a["kind"]) for a in member["aliases"]}
        for candidate in candidates:
            url = candidate["sources"][0]["url"]
            entries = [(candidate["text"], "chinese_" + candidate["status"], url)]
            if candidate["display_simplified"] != candidate["text"]:
                entries.append((candidate["display_simplified"], "generated_chinese_script", url))
            for text in {candidate["text"], candidate["display_simplified"]}:
                if len(text) == 3 and text[0] in "李金朴宋白張张盧卢林俞兪孫孙安許许洪劉刘黃黄崔申周寧宁":
                    entries.append((text[1:], "generated_given_chinese", url))
            for text, kind, evidence in entries:
                if (text, kind) not in existing:
                    member["aliases"].append({"text": text, "normalized": normalize(text),
                        "kind": kind, "priority": 105 if kind == "chinese_official_usage" else 90,
                        "evidence": evidence})
                    existing.add((text, kind))
    return {"policy": catalogue["policy"], "coverage": sum(bool(m["chinese_names"]) for m in members),
            "pending": sum(not m["chinese_names"] for m in members),
            "official_usage": sum(m["chinese_name_status"] == "official_usage" for m in members),
            "official_confirmed": sum(m["chinese_name_status"] == "official_confirmed" for m in members)}


def save_chinese_sql(conn, members):
    conn.execute("""CREATE TABLE IF NOT EXISTS member_chinese (
        member_id TEXT PRIMARY KEY, display_name TEXT, status TEXT NOT NULL,
        selection_rule TEXT, candidates_json TEXT NOT NULL)""")
    conn.execute("DELETE FROM member_chinese")
    conn.executemany("INSERT INTO member_chinese VALUES (?,?,?,?,?)", [
        (m["id"], m["chinese_name"], m["chinese_name_status"], m["chinese_name_selection"],
         json.dumps(m["chinese_names"], ensure_ascii=False)) for m in members])
