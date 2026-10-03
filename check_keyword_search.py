"""Offline checks for optional inputs, exact aliases and date tolerance."""
import itertools
import unittest
from idol_search import IdolCatalogue, make_keyword_search_plan, rank_results

class Checks(unittest.TestCase):
    def setUp(self):
        self.db = IdolCatalogue('idol_names/idol_aliases.json')
        self.member = self.db.by_id['fromis9:nagyung']
        self.group = self.db.resolve_group('fro')

    def entry(self, title, publish='20260920', verified=True):
        return {'id': 'AAAAAAAAAAA', 'title': title, 'publish_date': publish, '_publish_verified': verified}

    def test_all_input_combinations(self):
        for a, b, c, d in itertools.product((False, True), repeat=4):
            accepted = (a and b) or (a and d) or (b and c) or (b and d) or (c and d)
            args = (self.member if c else None, self.group if a else None, 'nagyung' if c else '', '260919' if d else '', 'DM' if b else '')
            if accepted:
                plan = make_keyword_search_plan(*args)
                self.assertTrue(plan['queries'])
                self.assertTrue(rank_results([self.entry('fromis9 nagyung DM 260919')], plan))
            else:
                with self.assertRaises(ValueError):
                    make_keyword_search_plan(*args)

    def test_solo_without_group(self):
        plan = make_keyword_search_plan(self.member, None, 'nagyung', '', 'DM')
        self.assertEqual(plan['group_names'], [])
        self.assertTrue(all('fromis' not in q.casefold() for q in plan['queries']))
        self.assertTrue(rank_results([self.entry('nagyung DM solo')], plan))
        self.assertFalse(rank_results([self.entry('nagyderence DM')], plan))

    def test_required_vs_optional(self):
        plan = make_keyword_search_plan(self.member, self.group, 'nagyung', '260919', 'DM',
                                        required={'member': True, 'date': True})
        self.assertTrue(rank_results([self.entry('nagyung 2026.09.19')], plan))
        self.assertFalse(rank_results([self.entry('fromis9 DM 260919')], plan))
        self.assertFalse(rank_results([self.entry('nagyung DM')], plan))
        self.assertTrue(any('DM' not in q and 'fromis' not in q for q in plan['queries']))

    def test_tolerance_requires_verified_publish(self):
        strict = make_keyword_search_plan(self.member, None, 'nagyung', '260919')
        plan = make_keyword_search_plan(self.member, None, 'nagyung', '260919', date_tolerance=True)
        for day in ('20260919', '20261003'):
            self.assertTrue(rank_results([self.entry('nagyung solo', day)], plan))
        for day in ('20260918', '20261004', ''):
            self.assertFalse(rank_results([self.entry('nagyung solo', day)], plan))
        self.assertFalse(rank_results([self.entry('nagyung solo', verified=False)], plan))
        self.assertTrue(rank_results([self.entry('nagyung solo', verified=False)], plan, allow_unverified=True))
        self.assertFalse(rank_results([self.entry('nagyung solo')], strict))
        self.assertFalse(rank_results([self.entry('nagyung 260919')], plan)[0]['_deep_result'])

    def test_literal_input_first(self):
        plan = make_keyword_search_plan(self.member, None, 'nagyung', '260919')
        aliases = self.entry('이나경 2026.09.19')
        literal = {**self.entry('nagyung 260919'), 'id': 'BBBBBBBBBBB'}
        self.assertEqual(rank_results([aliases, literal], plan)[0]['id'], literal['id'])

    def test_429_stops_immediate_repeat(self):
        from unittest.mock import patch, Mock
        import youtube_search as module
        with patch.object(module, '_cooldown_until', 0), patch.object(module, '_next_request', 0):
            fetch = Mock(return_value=Mock(status_code=429, url='https://www.google.com/sorry/'))
            with self.assertRaises(module.YouTubeRateLimit):
                module.limited_request(fetch, 'https://www.youtube.com/watch', lambda: False)
            with self.assertRaises(module.YouTubeRateLimit):
                module.limited_request(fetch, 'https://www.youtube.com/watch', lambda: False)
            self.assertEqual(fetch.call_count, 1)

if __name__ == '__main__':
    unittest.main(verbosity=2)
