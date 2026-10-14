"""O bloco do resumo mora num projeto só (o RoadS) e a pergunta precisa aparecer em qualquer projeto: o registro do
usuário, assinado com a chave dele, diz onde o bloco está. Aqui: o bloco do próprio projeto vale primeiro, o registro
vale quando não há bloco, um registro forjado ou copiado não vale, e todas as operações seguintes usam o projeto do
registro.

Seam: `progress_report.run` (`status`, `home` e as demais operações) e a CLI.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'))
import progress_report as pr
import test_progress_report as base

ROOT = Path(__file__).resolve().parents[1]


class HomeTestCase(base.ProgressTestCase):
    """`self.project` declares the block (the RoadS, here); `self.other` is any project the session may open."""

    def setUp(self):
        super().setUp()
        self.other = Path(self.tmp.name) / 'other'
        (self.other / '.frontlights').mkdir(parents=True)

    def other_config(self, **sync):
        config = {'repository': 'OWNER/OTHER', 'project': None, 'roads': None, 'roadmapSync': dict(sync)} if sync else \
            {'repository': 'OWNER/OTHER', 'project': None, 'roads': None}
        (self.other / '.frontlights' / 'config.json').write_text(json.dumps(config), encoding='utf-8')

    def status_from_other(self):
        return pr.run('status', str(self.other))

    def register(self, target=None):
        result = pr.run('home', str(self.other), home_set=str(target or self.project))
        self.assertTrue(result['ok'], result)
        return result


class WithoutRegistrationTests(HomeTestCase):
    def test_a_project_without_the_block_and_without_a_registration_does_not_ask_and_says_how_to_fix_it(self):
        self.other_config()
        result = self.status_from_other()
        self.assertEqual((result['ask'], result['source'], result['homeState']), (False, None, 'none'))
        self.assertIn('home --set', result['hint'])
        self.assertNotIn('operationsRoot', result)

    def test_a_project_without_any_config_behaves_the_same(self):
        (self.other / '.frontlights' / 'config.json').unlink(missing_ok=True)
        result = self.status_from_other()
        self.assertEqual((result['ask'], result['source'], result['homeState']), (False, None, 'none'))

    def test_the_project_that_declares_the_block_reports_itself(self):
        result = pr.run('status', str(self.project))
        self.assertEqual((result['ask'], result['source'], result['homeState']), (True, 'project', 'own'))
        self.assertEqual(Path(result['operationsRoot']), self.project.resolve())
        self.assertNotIn('home', result)


class RegistrationTests(HomeTestCase):
    def test_a_registered_home_makes_any_project_ask_and_names_where_the_block_is(self):
        self.other_config(enabled=True)
        self.register()
        for configured in (True, False):
            if not configured:
                (self.other / '.frontlights' / 'config.json').unlink()
            result = self.status_from_other()
            with self.subTest(other_has_config=configured):
                self.assertEqual((result['ask'], result['source'], result['homeState']), (True, 'home', 'registered'))
                self.assertEqual(Path(result['operationsRoot']), self.project.resolve())
                self.assertEqual(Path(result['home']['root']), self.project.resolve())
                self.assertEqual(result['approval'], 'unapproved')
                self.assertEqual(result['project'], 'OWNER/REPOSITORY')

    def test_the_own_block_of_a_project_wins_even_when_it_is_disabled(self):
        self.register()
        self.other_config(progress={'enabled': False})
        result = self.status_from_other()
        self.assertEqual((result['ask'], result['source'], result['homeState']), (False, 'project', 'own'))
        self.assertEqual(Path(result['operationsRoot']), self.other.resolve())

    def test_the_registration_refuses_a_project_without_an_enabled_valid_block_and_writes_nothing(self):
        self.other_config(enabled=True)
        cases = {'no block': self.other, 'not a folder': self.other / 'missing'}
        for name, target in cases.items():
            result = pr.run('home', str(self.project), home_set=str(target))
            with self.subTest(name):
                self.assertFalse(result['ok'])
        self.write_config(progress=self.block(enabled=False))
        self.assertFalse(pr.run('home', str(self.other), home_set=str(self.project))['ok'])
        self.write_config(progress=self.block(pushCommand='not a list'))
        self.assertFalse(pr.run('home', str(self.other), home_set=str(self.project))['ok'])
        self.assertFalse(pr.home_path().exists())

    def test_set_and_clear_together_are_refused(self):
        result = pr.run('home', str(self.other), home_set=str(self.project), home_clear=True)
        self.assertFalse(result['ok'])
        self.assertFalse(pr.home_path().exists())

    def test_show_reports_the_registration_and_whether_it_still_works(self):
        self.assertEqual(pr.run('home', str(self.other))['homeState'], 'none')
        self.register()
        shown = pr.run('home', str(self.other))
        self.assertEqual((shown['homeState'], shown['valid'], shown['name']), ('registered', True, 'OWNER/REPOSITORY'))
        self.write_config(progress=self.block(enabled=False))
        self.assertFalse(pr.run('home', str(self.other))['valid'])

    def test_clear_removes_it_and_the_question_goes_away(self):
        self.other_config(enabled=True)
        self.register()
        self.assertTrue(self.status_from_other()['ask'])
        cleared = pr.run('home', str(self.other), home_clear=True)
        self.assertEqual((cleared['ok'], cleared['homeState']), (True, 'none'))
        self.assertFalse(self.status_from_other()['ask'])
        self.assertIn('no registration', pr.run('home', str(self.other), home_clear=True)['message'])

    def test_the_block_losing_its_declaration_is_said_plainly(self):
        self.register()
        self.write_config(progress=None)
        result = self.status_from_other()
        self.assertEqual((result['ask'], result['source']), (False, 'home'))
        self.assertIn('no longer declares one', result['message'])


class TrustTests(HomeTestCase):
    def test_a_record_that_this_machine_did_not_sign_is_not_trusted(self):
        self.register()
        record = json.loads(pr.home_path().read_text(encoding='utf-8'))
        for name, changed in (('unsigned', {**record, 'signature': ''}),
                              ('foreign signature', {**record, 'signature': 'f' * 64}),
                              ('another root, same signature', {**record, 'root': str(self.other)}),
                              ('no signature field', {'root': record['root']}),
                              ('non-ASCII signature', {**record, 'signature': 'éé' + record['signature'][2:]}),
                              ('lone surrogate signature', {**record, 'signature': '\ud800' + record['signature'][1:]}),
                              ('not an object', [1, 2])):
            pr.home_path().write_text(json.dumps(changed), encoding='utf-8')
            result = self.status_from_other()
            with self.subTest(name):
                self.assertEqual((result['ask'], result['source'], result['homeState']), (False, None, 'invalid'))
                self.assertIn('not trusted', result['hint'])

    def test_an_unreadable_record_or_a_missing_key_is_invalid_not_a_crash(self):
        self.register()
        pr.home_path().write_text('not json', encoding='utf-8')
        self.assertEqual(self.status_from_other()['homeState'], 'invalid')
        self.register()
        pr.user_key_path().unlink()
        self.assertEqual(self.status_from_other()['homeState'], 'invalid')

    def test_a_record_committed_to_a_repository_is_worthless_on_another_key(self):
        self.register()
        carried = pr.home_path().read_text(encoding='utf-8')
        pr.user_key_path().write_text('another-machine-key', encoding='utf-8')
        pr.home_path().write_text(carried, encoding='utf-8')
        self.assertEqual(self.status_from_other()['homeState'], 'invalid')

    def test_no_key_of_a_project_config_can_point_the_session_at_another_folder(self):
        for where in ('top', 'sync'):
            for key in ('progressHome', 'home', 'progressRoot', 'root'):
                config = {'repository': 'OWNER/OTHER', 'project': None, 'roads': None, 'roadmapSync': {'enabled': True}}
                (config if where == 'top' else config['roadmapSync'])[key] = str(self.project)
                (self.other / '.frontlights' / 'config.json').write_text(json.dumps(config), encoding='utf-8')
                result = self.status_from_other()
                with self.subTest(where=where, key=key):
                    self.assertEqual((result['ask'], result['source'], result['homeState']), (False, None, 'none'))
        self.register()
        self.other_config(enabled=True, progress='not an object')
        self.assertEqual(self.status_from_other()['source'], 'home')     # a non-object block is no block of its own

    def test_a_signature_made_for_an_approval_is_not_a_signature_of_a_home(self):
        self.register()
        record = json.loads(pr.home_path().read_text(encoding='utf-8'))
        key = pr.read_user_key()
        pr.home_path().write_text(json.dumps({**record, 'signature': pr.sign(key, record['root'])}), encoding='utf-8')
        self.assertEqual(self.status_from_other()['homeState'], 'invalid')

    def test_a_project_config_that_cannot_be_read_is_not_swapped_for_the_registry(self):
        self.register()
        (self.other / '.frontlights' / 'config.json').write_text('{not json', encoding='utf-8')
        result = self.status_from_other()
        self.assertEqual((result['ok'], result['ask'], result['source'], result['homeState']), (True, False, 'project', 'own'))
        self.assertIn('could not be read', result['message'])

    def test_a_lone_surrogate_in_a_record_is_invalid_or_unapproved_not_a_crash(self):
        self.register()
        record = json.loads(pr.home_path().read_text(encoding='utf-8'))
        pr.home_path().write_text(json.dumps({**record, 'root': '\ud800x'}), encoding='utf-8')
        result = self.status_from_other()
        self.assertEqual((result['ok'], result['homeState']), (True, 'invalid'))
        self.assertEqual(pr.run('home', str(self.other))['homeState'], 'invalid')
        self.approved()
        approval = self.project / '.frontlights' / 'progress-report' / 'approval.json'
        stored = json.loads(approval.read_text(encoding='utf-8'))
        approval.write_text(json.dumps({**stored, 'blockHash': '\ud800' + stored['blockHash'][1:]}), encoding='utf-8')
        status = pr.run('status', str(self.project))
        self.assertEqual((status['ok'], status['approval']), (True, 'unapproved'))

    def test_a_non_ascii_signature_in_an_approval_record_is_unapproved_not_a_crash(self):
        self.approved()
        approval = self.project / '.frontlights' / 'progress-report' / 'approval.json'
        record = json.loads(approval.read_text(encoding='utf-8'))
        approval.write_text(json.dumps({**record, 'signature': 'éé' + record['signature'][2:]}), encoding='utf-8')
        result = pr.run('status', str(self.project))
        self.assertEqual((result['ok'], result['approval']), (True, 'unapproved'))

    def test_a_project_config_cannot_register_a_home_by_itself(self):
        # The registration lives only in the user's home directory: a config in the project has no key for it.
        self.other_config(enabled=True, progress={'enabled': True, 'home': str(self.project)})
        result = self.status_from_other()
        self.assertEqual(result['source'], 'project')
        self.assertFalse(result['valid'])


class OperationsFollowTheHomeTests(HomeTestCase):
    def setUp(self):
        super().setUp()
        self.other_config(enabled=True)
        self.register()

    def test_approve_window_and_collect_from_another_project_run_in_the_home(self):
        approved = pr.run('approve', str(self.other))
        self.assertTrue(approved['ok'], approved)
        self.assertTrue((self.project / '.frontlights' / 'progress-report' / 'approval.json').is_file())
        self.assertFalse((self.other / '.frontlights' / 'progress-report').exists())
        self.assertEqual(self.status_from_other()['approval'], 'approved')
        self.roads.answer = (200, base.state())
        window = pr.run('window', str(self.other), transport=None)
        self.assertTrue(window['ok'], window)
        self.assertEqual(len(self.roads.requests), 1)
        self.assertEqual(self.roads.requests[0]['authorization'], f'Bearer {base.SECRET}')
        collected = pr.run('collect', str(self.other), date_from='2026-09-28', date_to='2026-09-30')
        self.assertTrue(collected['ok'], collected)
        self.assertEqual([entry['name'] for entry in self.logged()], ['usage'])

    def test_the_collectors_run_from_the_home_root_not_from_the_project_the_session_opened(self):
        pr.run('approve', str(self.other))
        (self.tools / 'cwd.py').write_text('import os, sys\nopen(sys.argv[1], "w").write(os.getcwd())\n', encoding='utf-8')
        marker = self.out / 'cwd.txt'
        self.edit_block(collectors=[{'name': 'cwd', 'command': [sys.executable, str(self.tools / 'cwd.py'), str(marker)]}])
        pr.run('approve', str(self.other))
        self.assertTrue(pr.run('collect', str(self.other), date_from='2026-09-28', date_to='2026-09-30')['ok'])
        self.assertEqual(Path(marker.read_text(encoding='utf-8')).resolve(), self.project.resolve())

    def test_a_project_with_its_own_block_never_uses_the_home_for_the_operations(self):
        self.other_config(enabled=True, progress={'enabled': False})
        result = pr.run('window', str(self.other))
        self.assertFalse(result['ok'])
        self.assertEqual(self.roads.requests, [])


class CommandLineTests(HomeTestCase):
    def test_a_relative_folder_is_registered_as_the_real_absolute_path(self):
        script = ROOT / 'skills' / 'frontlights' / 'scripts' / 'progress_report.py'
        env = {**os.environ, 'FRONTLIGHTS_HOME': str(Path(self.tmp.name) / 'rel-home'), 'FRONTLIGHTS_API_SECRET': base.SECRET}
        done = subprocess.run([sys.executable, str(script), 'home', '--set', '../project'], cwd=self.other,
                              capture_output=True, text=True, encoding='utf-8', env=env)
        result = json.loads(done.stdout)
        self.assertEqual((done.returncode, result['homeState']), (0, 'registered'))
        self.assertEqual(Path(result['root']), self.project.resolve())
        self.assertTrue(Path(result['root']).is_absolute())

    def test_the_script_registers_shows_and_clears_the_home(self):
        script = ROOT / 'skills' / 'frontlights' / 'scripts' / 'progress_report.py'
        env = {**os.environ, 'FRONTLIGHTS_HOME': str(Path(self.tmp.name) / 'cli-home'), 'FRONTLIGHTS_API_SECRET': base.SECRET}

        def call(*args):
            done = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, encoding='utf-8', env=env)
            return done.returncode, json.loads(done.stdout)

        self.assertEqual(call('home')[1]['homeState'], 'none')
        code, set_result = call('home', '--set', str(self.project))
        self.assertEqual((code, set_result['homeState']), (0, 'registered'))
        code, status = call('status', '--root', str(self.other))
        self.assertEqual((code, status['ask'], status['source']), (0, True, 'home'))
        code, refused = call('home', '--set', str(self.other))
        self.assertEqual((code, refused['ok']), (1, False))
        code, cleared = call('home', '--clear')
        self.assertEqual((code, cleared['homeState']), (0, 'none'))


class HomeDocumentationTests(unittest.TestCase):
    def test_the_reference_and_the_skill_use_the_home_in_any_project(self):
        reference = ' '.join((ROOT / 'skills' / 'frontlights' / 'references' / 'progress-report.md')
                             .read_text(encoding='utf-8').split())
        for phrase in ('operationsRoot', 'home --set', 'registered home', 'explicit yes', 'homeState'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, reference)
        skill = ' '.join((ROOT / 'skills' / 'frontlights' / 'SKILL.md').read_text(encoding='utf-8').split())
        stage1 = skill.split('## 1.')[1].split('## 2.')[0]
        for phrase in ('operationsRoot', 'in any project', 'homeState'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, stage1)

    def test_the_stage_one_question_to_register_is_in_the_skill_and_the_eval(self):
        flat = lambda *parts: ' '.join(ROOT.joinpath(*parts).read_text(encoding='utf-8').split())
        question = 'Registrar o projeto que guarda o bloco do Resumo para a diretoria?'
        self.assertIn(question, flat('skills', 'frontlights', 'SKILL.md'))
        self.assertIn(question, flat('evals', 'progress-home.md'))
        self.assertIn('Agora não', flat('skills', 'frontlights', 'SKILL.md'))

    def test_the_eval_the_runbook_and_the_record_cover_the_case(self):
        flat = lambda *parts: ' '.join(ROOT.joinpath(*parts).read_text(encoding='utf-8').split())
        self.assertIn('registered', flat('evals', 'progress-home.md'))
        self.assertIn('18. Progress question in any project, and a start by plain words (`evals/progress-home.md`)',
                      flat('evals', 'runbook.md'))
        self.assertIn('| 18. Pergunta do resumo em qualquer projeto e início por linguagem natural | Pendente |',
                      flat('docs', 'acceptance.md'))


if __name__ == '__main__':
    unittest.main()
