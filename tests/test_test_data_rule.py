"""The standing rule that a browser or cross-account test uses the test accounts that exist, creates on demand the
test data its flow needs and keeps it for reuse (issue 74, S2: nothing is removed at the end of a pass; the moved
profile is still undone): it is written once, in the reference, and nothing else in the skill contradicts it."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills' / 'frontlights'


def flat(*parts):
    return ' '.join(ROOT.joinpath(*parts).read_text(encoding='utf-8').split())


def section(text, title):
    match = re.search(rf'^## {re.escape(title)}\n(.*?)(?=^## |\Z)', text, re.S | re.M)
    return ' '.join(match.group(1).split()) if match else ''


class TestDataRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = (SKILL / 'references' / 'browser-testing.md').read_text(encoding='utf-8')
        cls.rule = section(cls.reference, 'Test data the run creates')

    def test_the_section_says_what_is_created_how_where_and_that_it_stays(self):
        for phrase in ('never a reason to skip a case', 'non-owner', 'second account or tenant',
                       "the product's own endpoints", 'the local development database', 'Never production',
                       "real person's or customer's", 'dados-de-teste.json', 'kind and id, for reuse',
                       'is not removed at the end of a pass', 'the same accounts and data serve ANTES and DEPOIS',
                       'any test account that already exists',
                       'git-ignored local file', 'Every brief handed to a subagent'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.rule)

    def test_a_brief_may_not_forbid_creating_users_or_stop_for_a_missing_login(self):
        self.assertIn('A brief never says "não crie usuário", "pare se faltar login" or "espere a decisão"', self.rule)
        self.assertIn('a brief that runs the test says to create what is missing', self.rule)

    def test_the_old_stop_and_ask_for_a_missing_login_or_account_is_gone(self):
        text = ' '.join(self.reference.split())
        self.assertNotIn('is a config gap: ask', text)
        self.assertNotIn('(the only admin demoted, say), stop and ask', text)
        self.assertIn('create another test user that can before the move', text)
        self.assertIn('is test data the run creates', text)
        self.assertIn('never demote the account that performs the undo', text)

    def test_the_watched_run_question_tells_the_user_it_happens(self):
        watched = section(self.reference, 'Watched run: before and after, with the user watching')
        self.assertIn('creates the test data the `Fluxo:` needs', watched)
        self.assertIn('which stays on the local development database for reuse', watched)

    def test_the_record_sits_with_the_other_evidence_and_the_rule_is_pointed_to(self):
        self.assertIn('`perfil-original.json` and `dados-de-teste.json`', section(self.reference, 'Evidence'))
        self.assertIn('Test data the run creates', ' '.join(self.reference.split()).split('## Environment')[0])
        # redesenho, issue 3: a frase "creates on demand the test users and data its flow needs, which stay for
        # reuse" saiu do SKILL.md; a regra vive na referência e a etapa 6 aponta para o "Watched run" dela
        self.assertIn('test data the `Fluxo:` needs to run completely, and keeps it for reuse', ' '.join(self.reference.split()))
        self.assertIn('(`references/browser-testing.md`, "Watched run")', flat('skills', 'frontlights', 'SKILL.md'))
        # redesenho, issue 5: a regra que todo brief leva vive em worker.md, a casa única do brief
        self.assertIn('create what the flow needs', flat('skills', 'frontlights', 'references', 'worker.md'))

    def test_the_data_stays_and_only_the_moved_profile_is_undone(self):
        self.assertNotIn('right after the last case of a run with no watcher', self.rule)
        self.assertNotIn('"Precisa de alteração" only once the changed flow has run again', self.rule)
        self.assertIn('The profile a `Fluxo:` moved is still undone', self.rule)

    def test_the_rule_holds_no_login_or_password_value(self):
        self.assertIsNone(re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', self.rule))
        self.assertNotRegex(self.rule, r'(?i)\b(senha|password)\s*[:=]\s*\S')


if __name__ == '__main__':
    unittest.main()
