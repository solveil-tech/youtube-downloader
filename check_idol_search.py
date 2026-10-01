"""Offline regression checks; safe to run from the source-check BAT."""
import unittest
from pathlib import Path
from idol_search import IdolCatalogue, date_variants, make_search_plan, matches_name, member_display_name, rank_results


class SearchChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = IdolCatalogue(Path(__file__).parent / "idol_names" / "idol_aliases.json")

    def test_identity(self):
        self.assertEqual(self.db.resolve_group("fro")["name"], "fromis_9")
        self.assertEqual(self.db.resolve_group("fromis9")["name"], "fromis_9")
        self.assertEqual(self.db.member_matches("李娜炅", exact=True), [])
        self.assertEqual(self.db.member_matches("娜炅", exact=True), [])
        self.assertEqual(self.db.member_matches("이나경", exact=True)[0]["id"], "fromis9:nagyung")
        self.assertGreater(len(self.db.member_matches("nakyung", exact=True)), 1)
        self.assertEqual(len(self.db.member_matches("nakyung", "fromis_9", exact=True)), 1)

    def test_date(self):
        self.assertIn("2026.09.19", date_variants("260919"))
        self.assertIn("26/09/19", date_variants("260919"))
        for bad in ("260231", "261301", "2609190", "26.919", "abcdef", ""):
            with self.assertRaises(ValueError):
                date_variants(bad)

    def test_plan(self):
        group = self.db.resolve_group("fromis9")
        member = self.db.by_id["fromis9:nagyung"]
        plan = make_search_plan(member, group, "nagyung", "260919")
        self.assertIn("nakyung", [name.casefold() for name in plan["names"]])
        self.assertIn("nagyoung", [name.casefold() for name in plan["names"]])
        self.assertIn("nakyeong", [name.casefold() for name in plan["names"]])
        self.assertEqual(set(plan["short_queries"]), set(plan["names"]))
        for date in plan["dates"]:
            self.assertTrue(any(date in query for query in plan["queries"]) or date not in (plan["dates"][0], plan["dates"][1], plan["dates"][4], plan["dates"][5]))
        group_plan = make_search_plan(None, group, "", "260919")
        self.assertIsNone(group_plan["member_id"])
        self.assertIn("fromis_9", group_plan["names"])

    def test_partial_input_is_not_an_alias(self):
        member = self.db.by_id["fromis9:nagyung"]
        group = self.db.resolve_group("fro")
        wrong = {"id": "AAAAAAAAAAA", "title": "2026.10.01|cs nagy ferencz"}
        for prefix in ("n", "na", "nag", "nagy", "Lee Na", "ferencz"):
            plan = make_search_plan(member, group, prefix, "261001", self.db)
            self.assertNotIn(prefix, plan["names"])
            self.assertEqual(rank_results([wrong], plan), [], prefix)
            self.assertEqual(len(rank_results([{"id": "BBBBBBBBBBB", "title": "nagyung 261001 fancam"}], plan)), 1)

    def test_order_and_duplicates(self):
        plan = make_search_plan(self.db.by_id["fromis9:nagyung"], self.db.resolve_group("fro"), "nagyung", "260919")
        entries = [
            {"id": "AAAAAAAAAAA", "title": "nagyung 250919"},
            {"id": "BBBBBBBBBBB", "title": "이나경 2026.09.19"},
            {"id": "CCCCCCCCCCC", "title": "nagyung 260919 fancam"},
            {"id": "CCCCCCCCCCC", "title": "nagyung 260919 fancam", "channel": "Test"},
            {"id": "DDDDDDDDDDD", "title": "nagyung 12609190"},
        ]
        ranked = rank_results(entries, plan)
        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0]["id"], "CCCCCCCCCCC")
        self.assertEqual(ranked[1]["id"], "BBBBBBBBBBB")
        self.assertEqual(ranked[0]["channel"], "Test")
        self.assertNotIn("DDDDDDDDDDD", {e["id"] for e in ranked})

    def test_strict_filter(self):
        for title in ("jin.....kyu 260919", "kyu.....jin 260919", "kyu music jin 260919", "장규.....진 260919"):
            self.assertFalse(matches_name(title, "Kyujin"))
            self.assertFalse(matches_name(title, "Kyu-jin"))
            self.assertFalse(matches_name(title, "규진"))
        self.assertTrue(matches_name("Kyujin 260919", "Kyujin"))
        self.assertTrue(matches_name("Jang Kyu Jin 260919", "Jang Kyu-jin"))
        self.assertFalse(matches_name("Australian tour 260919", "Lia"))
        self.assertFalse(matches_name("Freight train 260919", "Rei"))
        self.assertFalse(matches_name("nagyderence 260919", "nagyung"))
        for title in ("nagyungfake 261001", "nagyderence 261001", "nag music yung 261001", "nagyungабв 261001", "nagyung가 261001", "xx나경yy 261001", "나경이야기 261001"):
            self.assertFalse(matches_name(title, "nagyung"), title)
            self.assertFalse(matches_name(title, "nag yung"), title)
            self.assertFalse(matches_name(title, "나경"), title)
        self.assertTrue(matches_name("261001 nag yung fancam", "nagyung"))
        self.assertTrue(matches_name("260919 stage NAGYUNG", "nagyung"))
        self.assertTrue(matches_name("stage NAGYUNG 260919", "nagyung"))
        self.assertTrue(matches_name("260919 stage NAG YUNG", "nag yung"))
        self.assertFalse(matches_name("260919 stage NAG music YUNG", "nag yung"))
        self.assertFalse(matches_name("fromis91 260919", "fromis_9"))
        self.assertTrue(matches_name("[LEE NA GYUNG] 260919", "Lee Na-gyung"))
        self.assertTrue(matches_name("[fromis9] 260919", "fromis_9"))
        self.assertTrue(matches_name("이나경직캠 260919", "이나경"))
        group = self.db.resolve_group("fro")
        plan = make_search_plan(self.db.by_id["fromis9:nagyung"], group, "nagyung", "260919")
        spaced_plan = make_search_plan(self.db.by_id["fromis9:nagyung"], group, "nag yung", "260919")
        self.assertEqual(spaced_plan["names"][0], "nag yung")
        entries = [
            {"id": "EEEEEEEEEEE", "title": "ข่าวบันเทิง 260919"},
            {"id": "FFFFFFFFFFF", "title": "भारतीय संगीत 260919"},
            {"id": "GGGGGGGGGGG", "title": "nagyung 250919"},
            {"id": "HHHHHHHHHHH", "title": "nagyung music video"},
            {"id": "IIIIIIIIIII", "title": "nagyung 26.09.19 fancam"},
            {"id": "JJJJJJJJJJJ", "title": "fromis_9 260919 full performance"},
        ]
        self.assertEqual([e["id"] for e in rank_results(entries, plan)], ["IIIIIIIIIII"])
        group_plan = make_search_plan(None, group, "", "260919")
        self.assertEqual([e["id"] for e in rank_results(entries, group_plan)], ["JJJJJJJJJJJ"])

    def test_display_names(self):
        self.assertEqual(member_display_name(self.db.by_id["nmixx:kyujin"]), "Jang Kyujin")
        self.assertEqual(member_display_name(self.db.by_id["fromis9:nagyung"]), "Lee Nagyung")
        self.assertEqual(member_display_name(self.db.by_id["twice:jeongyeon"]), "Yoo Jeongyeon")
        self.assertEqual(member_display_name(self.db.by_id["ifeye:wonhwayeon"]), "Won Hwayeon")
        self.assertEqual(member_display_name(self.db.by_id["katseye:daniela"]), "Daniela Andrea Avanzini Llorente")
        self.assertEqual(member_display_name({"stage_name": "Anne", "full_name": "Anne-Marie McDonald", "full_name_hangul": "앤마리"}), "Anne-Marie McDonald")
        self.assertEqual(self.db.member_matches("Yoo Jeong Yeon", "TWICE", exact=True)[0]["id"], "twice:jeongyeon")
        self.assertEqual(self.db.member_matches("Lee Nagyung", "fromis_9", exact=True)[0]["id"], "fromis9:nagyung")
        for full in ("Lee Na-gyung", "Lee Na gyung", "Lee Nagyung"):
            self.assertEqual(member_display_name({"stage_name": "Nagyung", "full_name": full, "full_name_hangul": "이나경"}), "Lee Nagyung")

    def test_wrong_surname_and_shorts(self):
        from idol_search import flatten_search_entries, search_url
        plan = make_search_plan(self.db.by_id["fromis9:nagyung"], self.db.resolve_group("fro"), "nagyung", "260919")
        bad = ["김나경 260919", "최나경 260919", "Kim Nagyung 260919", "Park Na Gyung 260919", "KimNagyung 260919", "Nagyung Kim 260919",
               "#트리플에스김나경 260919", "김 나경 260919", "김-나경 260919", "김 나 경 nagyung 260919",
               "Kim_Nagyung 260919", "Kim.Nakyung 260919", "Nakyung_Kim 260919", "Kim Na Gyung 260919",
               "Ｋｉｍ Nagyung 260919", "Kim Nag Yung Nakyung 260919"]
        for title in bad:
            self.assertEqual(rank_results([{"id": "AAAAAAAAAAA", "title": title}], plan), [], title)
        entry = {"id": "BBBBBBBBBBB", "title": "이나경 직캠 260919", "url": "https://www.youtube.com/shorts/BBBBBBBBBBB", "duration": 14}
        self.assertEqual(rank_results([entry], plan)[0]["webpage_url"], entry["url"])
        self.assertEqual(flatten_search_entries({"entries": [{"entries": [entry]}, None]}), [entry])
        self.assertNotIn("sp=", search_url("nagyung 260919"))
        self.assertIn("sp=EgIQCQ%253D%253D", search_url("nagyung", shorts=True))

    def test_browser_shorts_renderer(self):
        from youtube_search import parse_search_renderers, initial_data
        data = {"contents": [{"richShelfRenderer": {"contents": [
            {"shortsLockupViewModel": {
                "entityId": "shorts-shelf-item-VouYqZeL9yw",
                "onTap": {"innertubeCommand": {"reelWatchEndpoint": {"videoId": "VouYqZeL9yw"}}},
                "overlayMetadata": {"primaryText": {"content": "Fromis_9 Nakyung Like You Better 261001 #fromis_9 #nakyung"}},
                "thumbnailViewModel": {"image": {"sources": [{"url": "https://i.ytimg.com/vi/VouYqZeL9yw/frame0.jpg"}]}}}},
            {"shortsLockupViewModel": {"entityId": "shorts-shelf-item-AAAAAAAAAAA",
                "accessibilityText": "fromis9 Nakyung 261001, 1.1 thousand views - play Short"}},
            {"shortsLockupViewModel": {"entityId": "shorts-shelf-item-BBBBBBBBBBB",
                "overlayMetadata": {"primaryText": {"content": "Jiheon 261001"}}}},
            {"shortsLockupViewModel": {"entityId": "shorts-shelf-item-CCCCCCCCCCC",
                "overlayMetadata": {"primaryText": {"content": "nagyderence 261001"}}}}
        ]}}]}
        plan = make_search_plan(self.db.by_id["fromis9:nagyung"], self.db.resolve_group("fro"), "nagyung", "261001")
        entries = parse_search_renderers(data, shorts_only=True)
        ranked = rank_results(entries, plan)
        self.assertEqual({entry["id"] for entry in ranked}, {"VouYqZeL9yw", "AAAAAAAAAAA"})
        self.assertTrue(all("/shorts/" in entry["webpage_url"] for entry in ranked))
        self.assertEqual(entries[0]["thumbnails"][0]["url"], "https://i.ytimg.com/vi/VouYqZeL9yw/frame0.jpg")
        import json
        self.assertEqual(initial_data("<script>var ytInitialData = " + json.dumps(data) + ";</script>"), data)

    def test_short_identity_context(self):
        plan = make_search_plan(self.db.by_id["fromis9:nagyung"], self.db.resolve_group("fro"), "nagyung", "261001", self.db)
        for title in ("Nakyung 261001", "나경 261001", "tripleS Nakyung 261001", "트리플에스 나경 261001"):
            entry = {"id": "AAAAAAAAAAA", "title": title, "_is_short": True}
            self.assertEqual(rank_results([entry], plan), [], title)
        for title in ("Fromis_9 Nakyung 261001", "이나경 261001", "Lee Nakyung 261001", "yinagyung 261001"):
            self.assertEqual(len(rank_results([{"id": "AAAAAAAAAAA", "title": title, "_is_short": True}], plan)), 1, title)
        entry = {"id": "AAAAAAAAAAA", "title": "Nakyung 261001", "_is_short": True, "description": "fromis_9 fancam"}
        self.assertEqual(len(rank_results([entry], plan)), 1)

    def test_short_metadata(self):
        import json
        from unittest.mock import patch, Mock
        from youtube_search import complete_short_metadata
        entry = {"id": "VouYqZeL9yw", "title": "fromis9 Nakyung 261001", "_is_short": True}
        player = {"videoDetails": {"videoId": entry["id"], "title": entry["title"], "author": "Celeb247", "lengthSeconds": "14", "shortDescription": "fromis_9"},
                  "microformat": {"playerMicroformatRenderer": {"uploadDate": "2026-10-01T06:31:46-07:00"}}}
        with patch("youtube_search.requests.get", return_value=Mock(text="var ytInitialPlayerResponse = " + json.dumps(player) + ";")):
            completed = complete_short_metadata(entry)
        self.assertEqual((completed["uploader"], completed["duration"], completed["upload_date"]), ("Celeb247", 14, "20261001"))
        self.assertTrue(completed["_metadata_complete"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
