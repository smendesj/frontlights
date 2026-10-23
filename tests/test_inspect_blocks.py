"""`inspect` valida os blocos browserTest e checks com as regras do serve e do checks que dependem só do config.

Sem os blocos, a saída do `inspect` não muda. Só marcadores genéricos (repositório público).
"""
import copy
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'frontlights' / 'scripts'))
import checks
import frontlights
import serve

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gitfixture

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills' / 'frontlights' / 'scripts' / 'frontlights.py'
EXAMPLE = json.loads((ROOT / 'skills' / 'frontlights' / 'examples' / 'config.json').read_text(encoding='utf-8'))
PASSWORD = 'senha-ficticia-longa'


def local(config):
    """Exemplo sem GitHub, quadro nem RoadS: o inspect não faz leitura de rede."""
    config = copy.deepcopy(config)
    config.update(repository=None, project=None, roads=None)
    return config


def process(**overrides):
    item = {'name': 'web', 'argv': ['python', 'APP_SCRIPT', '{port}'], 'port': 'auto',
            'health': 'http://127.0.0.1:{port}/health'}
    item.update(overrides)
    return item


def with_browser(*processes, users=None, base_url=None, front_paths=('web/src/**',)):
    block = {'processes': list(processes) or [process()],
             'users': users if users is not None else [{'login': 'usuario@exemplo.test', 'password': PASSWORD}]}
    if front_paths is not None:
        block['frontPaths'] = list(front_paths)
    if base_url is not None:
        block['baseUrl'] = base_url
    return {'repository': None, 'browserTest': block}


def with_checks(**checks):
    return {'repository': None, 'checks': checks}


def inspect_file(config, root):
    """Grava o config em uma pasta própria (fora da raiz inspecionada) e chama o inspect com o caminho real."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'config.json'
        path.write_text(json.dumps(config), encoding='utf-8')
        return frontlights.inspect(config, root, path)


SETUP_CODES = ('legacy_workflows_dir', 'browser_test_missing', 'project_unresolved', 'frontlights_not_ignored',
               'branch_prefix_missing')


def block_warnings(result):
    """Os avisos dos blocos, sem os da configuração (setup_warnings), que dependem da pasta e do Git."""
    return [w for w in result.get('warnings', []) if not w.startswith(SETUP_CODES)]


def stable(result):
    """Tira o horário da leitura, o único campo que muda entre duas execuções, e os avisos de configuração."""
    result = dict(result)
    result.pop('fetched_at')
    warnings = block_warnings(result)
    result.pop('warnings', None)
    if warnings:
        result['warnings'] = warnings
    return result


class InspectWithoutBlocksTests(unittest.TestCase):
    """Sem browserTest nem checks, nada muda: mesma saída e nenhum validador chamado."""

    def test_output_without_blocks_is_unchanged(self):
        with tempfile.TemporaryDirectory() as root:
            result = frontlights.inspect({'repository': None}, root)
            path_risk = frontlights.path_risk(Path(root).absolute(), frontlights.os.path.realpath(root))
        self.assertEqual(stable(result), {
            'repository': None, 'sources': {'github': {'status': 'unconfigured'},
                                            'project': {'status': 'unconfigured'},
                                            'roads': {'status': 'unconfigured'}},
            'verification_commands': {}, 'verification_candidates': [], 'path_risk': path_risk})

    def test_null_blocks_count_as_absent(self):
        with tempfile.TemporaryDirectory() as root:
            plain = frontlights.inspect({'repository': None}, root)
            nulls = frontlights.inspect({'repository': None, 'browserTest': None, 'checks': None}, root)
        self.assertEqual(stable(nulls), stable(plain))

    def test_no_validator_runs_and_nothing_is_read_without_blocks(self):
        def forbidden(*args, **kwargs):
            raise AssertionError('validador chamado sem os blocos')
        names = ('read_config', 'load_user_secrets', 'require_maskable_user_secrets', 'require_local_declarations',
                 'command_settings', 'smoke_settings', 'optional_name')
        with tempfile.TemporaryDirectory() as root, patch.object(serve, 'load_block', forbidden), \
                patch.object(serve, 'load_preview_block', forbidden), \
                patch.object(frontlights.Path, 'write_text', forbidden):
            patches = [patch.object(checks, name, forbidden) for name in names]
            for item in patches:
                item.start()
            try:
                for config in ({'repository': None},
                               {'repository': None, 'browserTest': None, 'checks': None, 'preview': None}):
                    with self.subTest(config=config):
                        frontlights.inspect(config, root)
                        frontlights.inspect(config, root, Path(root) / 'ausente.json')
            finally:
                for item in patches:
                    item.stop()

    def test_cli_output_without_blocks_has_the_same_keys(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / 'config.json'
            config.write_text(json.dumps({'repository': None}), encoding='utf-8')
            run = subprocess.run([sys.executable, str(SCRIPT), 'inspect', '--config', str(config), '--root', root],
                                 capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run.returncode, 0, run.stderr)
        keys = sorted([*stable(dict(json.loads(run.stdout), fetched_at=None)), 'fetched_at'])
        self.assertEqual(keys, ['fetched_at', 'path_risk', 'repository', 'sources', 'verification_candidates',
                                'verification_commands'])


class InspectValidBlocksTests(unittest.TestCase):
    def test_example_config_is_accepted_and_does_not_change_the_output(self):
        with tempfile.TemporaryDirectory() as root:
            plain = {k: v for k, v in local(EXAMPLE).items() if k not in ('browserTest', 'checks', 'preview')}
            self.assertEqual(stable(inspect_file(local(EXAMPLE), root)),
                             stable(frontlights.inspect(plain, root)))

    def test_validators_read_the_real_config_file(self):
        with tempfile.TemporaryDirectory() as root, \
                patch.object(checks, 'load_user_secrets', wraps=checks.load_user_secrets) as secrets, \
                patch.object(serve, 'load_block', wraps=serve.load_block) as block:
            path = Path(root) / 'config.json'
            path.write_text(json.dumps(local(EXAMPLE)), encoding='utf-8')
            frontlights.inspect(local(EXAMPLE), root, path)
        secrets.assert_called_once_with(path)
        block.assert_called_once_with(path, need_processes=False)

    def test_blocks_without_a_config_path_are_refused(self):
        with tempfile.TemporaryDirectory() as root, self.assertRaisesRegex(ValueError, 'caminho do config'):
            frontlights.inspect(local(EXAMPLE), root)

    def test_example_config_through_the_cli(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / 'config.json'
            config.write_text(json.dumps(local(EXAMPLE)), encoding='utf-8')
            run = subprocess.run([sys.executable, str(SCRIPT), 'inspect', '--config', str(config), '--root', root],
                                 capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIsNone(json.loads(run.stdout)['repository'])


class InspectRefusesInvalidBlocksTests(unittest.TestCase):
    """Bloco inválido é recusado como as outras recusas de config do inspect (ValueError; erro JSON na CLI)."""

    def refuse(self, config, pattern):
        with tempfile.TemporaryDirectory() as root, patch.object(frontlights, 'run') as network, \
                self.assertRaisesRegex(ValueError, pattern) as caught:
            inspect_file(config, root)
        network.assert_not_called()
        return str(caught.exception)

    def test_auto_port_without_placeholder_in_health(self):
        self.refuse(with_browser(process(health='http://127.0.0.1:8080/health')), r'\{port\}')

    def test_short_test_secret(self):
        message = self.refuse(with_browser(users=[{'login': 'usuario@exemplo.test', 'password': 'abc'}]),
                              'menos de 4 caracteres')
        self.assertNotIn('abc', message)

    def test_secret_with_the_checks_mask_marker(self):
        self.refuse(with_browser(users=[{'login': 'usuario@exemplo.test', 'password': 'x[oculto]x'}]),
                    'marcador de máscara')

    def test_processes_must_be_a_list(self):
        self.refuse({'repository': None, 'browserTest': {'processes': 'web'}}, 'browserTest.processes')

    def test_non_local_health_host(self):
        self.refuse(with_browser(process(port=8080, health='http://10.0.0.5:8080/health')), 'não é local')

    def test_non_local_base_url(self):
        self.refuse(with_browser(base_url='http://app.example.com/'), 'baseUrl')

    def test_embedded_shell_in_checks(self):
        for argv in (['sh', '-c', 'x'], ['cmd', '/c', 'x'], ['python', '-c', 'x'], ['npm', 'test', '&&', 'x']):
            with self.subTest(argv=argv):
                self.refuse(with_checks(regression={'argv': argv}), 'shell embutido')
                self.refuse(with_checks(integration={'argv': argv}), 'shell embutido')

    def test_argv_as_a_string(self):
        self.refuse(with_checks(regression={'argv': 'python -m unittest'}), 'lista de argumentos')

    def test_bad_smoke_paths(self):
        self.refuse(with_checks(smoke={'paths': ['http://10.0.0.5/']}), 'checks.smoke.paths')

    def test_bad_backend_name(self):
        self.refuse(with_checks(backend=7), 'checks.backend')

    def test_checks_must_be_an_object(self):
        message = self.refuse(with_checks() | {'checks': ['regression']}, 'checks')
        self.assertEqual(message, 'checks precisa ser um objeto com regression, integration ou smoke.')

    def test_refusal_never_shows_the_test_password(self):
        # o nome do processo repete a senha, e a mensagem de recusa cita o nome
        config = with_browser(process(name=PASSWORD, health='http://127.0.0.1:8080/health'))
        message = self.refuse(config, r'\{port\}')
        self.assertNotIn(PASSWORD, message)

    def test_refusal_never_shows_the_percent_encoded_test_password(self):
        password = 's3nh@#&'
        encoded = quote(password, safe='')
        config = with_browser(process(name=encoded, health='http://127.0.0.1:8080/health'),
                              users=[{'login': 'usuario@exemplo.test', 'password': password}])
        message = self.refuse(config, r'\{port\}')
        self.assertIn(checks.MASK, message)
        self.assertNotIn(encoded, message)
        self.assertNotIn(password, message)

    def test_cli_reports_the_refusal_as_json_without_the_password(self):
        config = with_browser(process(name=PASSWORD, health='http://127.0.0.1:8080/health'))
        config['checks'] = {'regression': {'argv': ['sh', '-c', 'x']}}
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'config.json'
            path.write_text(json.dumps(config), encoding='utf-8')
            run = subprocess.run([sys.executable, str(SCRIPT), 'inspect', '--config', str(path), '--root', root],
                                 capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stdout, '')
        self.assertNotIn('Traceback', run.stderr)
        self.assertNotIn(PASSWORD, run.stderr)
        self.assertIn('error', json.loads(run.stderr))


class RefusalListTests(unittest.TestCase):
    """Redesenho, issue 10: as recusas do `inspect` são uma lista só no código (`frontlights.INSPECT_REFUSALS`); o
    `inspect --help` a imprime e `docs/security.md`, "Recusas do `inspect`", traz as mesmas linhas entre marcadores."""

    def test_the_code_list_the_help_and_the_security_doc_are_the_same(self):
        expected = list(frontlights.INSPECT_REFUSALS)
        self.assertTrue(expected)
        done = subprocess.run([sys.executable, str(SCRIPT), 'inspect', '--help'], capture_output=True, text=True,
                              encoding='utf-8', check=True)
        helped = done.stdout.split('Recusa (saída 1):', 1)[1].strip().splitlines()
        self.assertEqual([line[2:] for line in helped if line.startswith('- ')], expected)
        doc = (ROOT / 'skills' / 'frontlights' / 'docs' / 'security.md').read_text(encoding='utf-8')
        block = doc.split('<!-- inspect-refusals -->', 1)[1].split('<!-- /inspect-refusals -->', 1)[0]
        self.assertEqual([line[2:] for line in block.strip().splitlines()], expected)


class FrontPathsWarningTests(unittest.TestCase):
    def test_a_browser_test_without_front_paths_warns_that_the_gate_will_guess(self):
        result = inspect_file(with_browser(front_paths=None), ROOT)
        self.assertEqual(len(block_warnings(result)), 1)
        self.assertIn('browserTest.frontPaths', block_warnings(result)[0])
        self.assertIn('browser-gate', block_warnings(result)[0])

    def test_declaring_them_silences_it_and_no_browser_test_has_nothing_to_warn_about(self):
        self.assertEqual(block_warnings(inspect_file(with_browser(), ROOT)), [])
        self.assertEqual(block_warnings(inspect_file({'repository': None}, ROOT)), [])


class AccountsOnlyBrowserTestTests(unittest.TestCase):
    """Um projeto que sobe o próprio ambiente declara só as contas (e a baseUrl) em browserTest.

    O `inspect` não falha por falta de `processes`: avisa que o `serve` não tem o que subir. Os segredos
    de teste continuam mascaráveis e os hosts continuam locais; `processes` declarado e inválido continua recusado.
    """

    def accounts_only(self, **block):
        block.setdefault('users', [{'login': 'usuario@exemplo.test', 'password': PASSWORD}])
        block.setdefault('frontPaths', ['web/src/**'])
        return {'repository': None, 'browserTest': block}

    def test_inspect_goes_on_and_warns_that_serve_has_nothing_to_start(self):
        with tempfile.TemporaryDirectory() as root:
            result = inspect_file(self.accounts_only(baseUrl='http://127.0.0.1:4200'), root)
        self.assertEqual(len(block_warnings(result)), 1)
        self.assertIn('browserTest.processes', block_warnings(result)[0])
        self.assertIn('serve', block_warnings(result)[0])
        self.assertNotIn(PASSWORD, json.dumps(result))

    def test_a_block_with_processes_has_no_warning(self):
        with tempfile.TemporaryDirectory() as root:
            result = inspect_file(with_browser(), root)
        self.assertNotIn('warnings', result)

    def test_the_cli_exits_zero_for_an_accounts_only_block(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / 'config.json'
            config.write_text(json.dumps(self.accounts_only()), encoding='utf-8')
            run = subprocess.run([sys.executable, str(SCRIPT), 'inspect', '--config', str(config), '--root', root],
                                 capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('browserTest.processes', block_warnings(json.loads(run.stdout))[0])

    def test_the_secret_rules_still_apply(self):
        with tempfile.TemporaryDirectory() as root, self.assertRaises(ValueError) as caught:
            inspect_file(self.accounts_only(users=[{'login': 'usuario@exemplo.test', 'password': 'abc'}]), root)
        self.assertIn('menos de 4 caracteres', str(caught.exception))

    def test_hosts_must_still_be_local(self):
        with tempfile.TemporaryDirectory() as root, self.assertRaises(ValueError) as caught:
            inspect_file(self.accounts_only(baseUrl='https://app.cliente-real.io'), root)
        self.assertIn('não é local', str(caught.exception))

    def test_declared_but_empty_or_malformed_processes_are_still_refused(self):
        for value in ([], 'web', None):
            with self.subTest(processes=value), tempfile.TemporaryDirectory() as root, \
                    self.assertRaises(ValueError) as caught:
                inspect_file(self.accounts_only(processes=value), root)
            self.assertIn('browserTest.processes', str(caught.exception))

    def test_serve_refuses_to_start_without_processes_and_says_what_to_do(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            path.write_text(json.dumps(self.accounts_only()), encoding='utf-8')
            with self.assertRaises(serve.Refusal) as caught:
                serve.load_block(path)
        message = str(caught.exception)
        self.assertIn('não declara browserTest.processes', message)
        self.assertIn('Suba o ambiente você mesmo', message)
        self.assertEqual(caught.exception.category, serve.USAGE)


def preview_block(**overrides):
    """Bloco preview válido: worktree e branch próprias, baseUrl local e um processo de porta fixa."""
    block = {'worktree': '.claude/worktrees/previa', 'branch': 'previa', 'baseUrl': 'http://127.0.0.1:8070/',
             'processes': [process(name='previa', argv=['python', 'APP_SCRIPT', '8070'], port=8070,
                                   health='http://127.0.0.1:8070/health')]}
    block.update(overrides)
    return block


class PreviewBlockTests(unittest.TestCase):
    """Revisão da issue 34 (B6): o inspect valida o bloco de topo preview com as regras do `serve preview`.

    Ausente ou null, nada é lido; presente, o bloco inválido é recusado com a mensagem mascarada.
    """

    def refuse(self, config, pattern):
        return InspectRefusesInvalidBlocksTests.refuse(self, config, pattern)

    def test_a_valid_block_is_accepted_and_does_not_change_the_output(self):
        for base in (with_browser(), {'repository': None}):
            with self.subTest(browserTest='browserTest' in base), tempfile.TemporaryDirectory() as root:
                config = dict(copy.deepcopy(base), preview=preview_block())
                expected = inspect_file(base, root) if 'browserTest' in base else frontlights.inspect(base, root)
                self.assertEqual(stable(inspect_file(config, root)), stable(expected))

    def test_the_preview_rules_of_the_serve_apply(self):
        missing = preview_block()
        missing.pop('processes')
        cases = {'texto': 'previa', 'lista': ['previa'], 'worktree que sai da raiz': preview_block(worktree='../fora'),
                 'worktree absoluta': preview_block(worktree='C:/fora'), 'worktree na raiz': preview_block(worktree='.'),
                 'branch main': preview_block(branch='main'), 'branch com espaço': preview_block(branch='a b'),
                 'baseUrl não local': preview_block(baseUrl='https://app.example.com/'),
                 'sem processes': missing, 'processes vazios': preview_block(processes=[]),
                 'processo sem health': preview_block(processes=[process(health=None)]),
                 # 3rd review of issue 34 (M): fixed ports, the tab is only reloaded
                 'baseUrl com {port}': preview_block(baseUrl='http://127.0.0.1:{port}/'),
                 'processo auto': preview_block(processes=preview_block()['processes'] + [process(name='api')]),
                 'baseUrl sem processo na porta': preview_block(baseUrl='http://127.0.0.1:8071/'),
                 # 4th review of issue 34: a fixed process never receives {port}
                 'processo fixo com {port} no argv': preview_block(processes=[process(
                     name='previa', argv=['python', 'APP_SCRIPT', '{port}'], port=8070,
                     health='http://127.0.0.1:8070/health')])}
        for case, block in cases.items():
            with self.subTest(case=case):
                self.refuse(dict(with_browser(), preview=block), 'preview')
        with self.subTest(case='sem browserTest'):
            self.refuse({'repository': None, 'preview': preview_block(branch='main')}, r'preview\.branch')

    def test_a_block_without_a_config_path_is_refused(self):
        with tempfile.TemporaryDirectory() as root, self.assertRaisesRegex(ValueError, 'caminho do config'):
            frontlights.inspect({'repository': None, 'preview': preview_block()}, root)

    def test_the_refusal_never_shows_the_test_login_or_password(self):
        login = 'usuario@exemplo.test'
        named = process(name=f'{login}-{PASSWORD}', argv=f'python APP_SCRIPT {PASSWORD}')
        message = self.refuse(dict(with_browser(), preview=preview_block(processes=[named])), 'argv')
        self.assertNotIn(login, message)
        self.assertNotIn(PASSWORD, message)

    def test_hostile_authorization_records_are_skipped_and_the_cli_answers_json(self):
        """2nd review of issue 34 (B3): a record nested too deep for json and one past 2 MiB are skipped by the
        reading of protected_branches that validates preview.branch; the inspect never ends in a traceback."""
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / '.frontlights'
            folder.mkdir()
            (folder / 'authorization-fundo.json').write_text('[' * 100000, encoding='utf-8')
            (folder / 'authorization-grande.json').write_text(
                json.dumps({'protected_branches': ['grande*'], 'padding': 'x' * (2 * 1024 * 1024 + 1)}),
                encoding='utf-8')
            config = Path(root) / 'config.json'
            config.write_text(json.dumps({'repository': None, 'preview': preview_block(branch='grande-previa')}),
                              encoding='utf-8')
            run = subprocess.run([sys.executable, str(SCRIPT), 'inspect', '--config', str(config), '--root', root],
                                 capture_output=True, text=True, encoding='utf-8')
        self.assertNotIn('Traceback', run.stderr)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIsNone(json.loads(run.stdout)['repository'])

    def test_the_example_declares_the_block_with_generic_markers(self):
        block = EXAMPLE['preview']
        self.assertEqual((block['worktree'], block['branch']), ('.claude/worktrees/previa', 'previa'))
        self.assertTrue(block['baseUrl'].startswith('http://127.0.0.1:'))
        ports = {item['port'] for item in block['processes']}
        self.assertTrue(ports and all(isinstance(port, int) for port in ports))
        self.assertTrue(all(item['health'].startswith('http://127.0.0.1:') for item in block['processes']))
        others = frontlights.fixed_ports(EXAMPLE['browserTest']['processes'])
        others.update(frontlights.fixed_ports(EXAMPLE['browserTest']['isolated']['processes']))
        self.assertFalse(ports & set(others))


class BrowserTestOffThePreviewPortsTests(unittest.TestCase):
    """3ª revisão da issue 34 (B): com o bloco preview presente, o inspect recusa porta fixa de browserTest.processes
    ou da browserTest.baseUrl igual a uma porta fixa da prévia, mesmo sem browserTest.isolated."""

    def refuse(self, config, pattern):
        return InspectRefusesInvalidBlocksTests.refuse(self, config, pattern)

    def preview(self):
        """Prévia com dois processos: `previa` em port 8070 (a da baseUrl) e `api` só com a porta do health, 8072."""
        api = {'name': 'api', 'argv': ['python', 'API_SCRIPT'], 'health': 'http://127.0.0.1:8072/health'}
        return preview_block(processes=preview_block()['processes'] + [api])

    def test_a_fixed_port_of_the_browser_test_processes_on_a_preview_port_is_refused(self):
        cases = {'port inteiro na porta da baseUrl da prévia': (
                     process(port=8070, health='http://127.0.0.1:8070/health'), 8070, 'preview.baseUrl'),
                 'porta do health num processo da prévia': (
                     {'name': 'web', 'argv': ['python', 'APP_SCRIPT'], 'health': 'http://localhost:8072/'}, 8072,
                     'o processo api de preview.processes')}
        for case, (item, port, side) in cases.items():
            with self.subTest(case=case):
                message = self.refuse(dict(with_browser(process(name='outro'), item), preview=self.preview()),
                                      rf'browserTest\.processes.*web.*{port}')
                self.assertIn(side, message)
                self.assertIn('o teste assistido nunca roda nas portas da prévia', message)

    def test_a_fixed_browser_test_base_url_on_a_preview_port_is_refused(self):
        for base_url, port, side in (('http://127.0.0.1:8070/', 8070, 'o processo previa de preview.processes'),
                                     ('http://localhost:8072/app', 8072, 'o processo api de preview.processes')):
            with self.subTest(baseUrl=base_url):
                message = self.refuse(dict(with_browser(base_url=base_url), preview=self.preview()),
                                      rf'browserTest\.baseUrl.*{port}')
                self.assertIn(side, message)
                self.assertIn('o teste assistido nunca roda nas portas da prévia', message)

    def test_the_refusal_never_shows_the_test_login_or_password(self):
        login = 'usuario@exemplo.test'
        named = process(name=f'{login}-{PASSWORD}', port=8070, health='http://127.0.0.1:8070/health')
        message = self.refuse(dict(with_browser(named), preview=self.preview()), r'browserTest\.processes.*8070')
        self.assertNotIn(login, message)
        self.assertNotIn(PASSWORD, message)

    def test_distinct_or_automatic_ports_are_accepted(self):
        configs = {'browserTest em auto': with_browser(process(), base_url='http://127.0.0.1:{port}/'),
                   'portas fixas diferentes': with_browser(
                       process(port=8080, health='http://127.0.0.1:8080/health'),
                       {'name': 'api', 'argv': ['python', 'API_SCRIPT'], 'health': 'http://127.0.0.1:8081/'},
                       base_url='http://127.0.0.1:8080/')}
        for case, config in configs.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as root:
                inspect_file(dict(config, preview=self.preview()), root)
        with self.subTest(case='sem bloco preview'), tempfile.TemporaryDirectory() as root:
            inspect_file(with_browser(process(port=8070, health='http://127.0.0.1:8070/health'),
                                      base_url='http://127.0.0.1:8070/'), root)


def isolated(**overrides):
    """Bloco browserTest.isolated válido: instância própria e porta automática, no banco de desenvolvimento local."""
    block = {'baseUrl': 'http://127.0.0.1:{port}/',
             'processes': [process(name='web', argv=['python', 'APP_SCRIPT', '{port}'])]}
    block.update(overrides)
    return block


def with_isolated(block=None, *processes, preview=None, **overrides):
    """browserTest com a subchave isolated (`block` substitui o bloco inteiro; `overrides`, campos dele)."""
    config = with_browser(*processes)
    config['browserTest']['isolated'] = isolated(**overrides) if block is None else block
    if preview is not None:
        config['preview'] = preview
    return config


class IsolatedBlockTests(unittest.TestCase):
    """browserTest.isolated: o teste assistido em instância própria, no banco de desenvolvimento local, sem cópia.

    Ausente ou null, nada muda; presente, o inspect recusa o bloco inválido antes de qualquer coisa rodar.
    """

    def refuse(self, config, pattern):
        return InspectRefusesInvalidBlocksTests.refuse(self, config, pattern)

    def test_a_valid_block_is_accepted_and_does_not_change_the_output(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(stable(inspect_file(with_isolated(), root)), stable(inspect_file(with_browser(), root)))

    def test_a_null_block_counts_as_absent(self):
        with tempfile.TemporaryDirectory() as root:
            config = with_browser()
            config['browserTest']['isolated'] = None
            self.assertEqual(stable(inspect_file(config, root)), stable(inspect_file(with_browser(), root)))

    def test_the_block_must_be_an_object(self):
        for value in ('instancia', ['web'], 7, True):
            with self.subTest(value=value):
                self.refuse(with_isolated(value), r'browserTest\.isolated precisa ser um objeto')

    def test_base_url_must_be_local_http_without_credentials(self):
        for value in ('http://10.0.0.5:{port}/', 'https://app.example.com/', 'ftp://127.0.0.1:{port}/',
                      'http://conta@127.0.0.1:{port}/', 'http://[::1/', '', 7, None):
            with self.subTest(baseUrl=value):
                self.refuse(with_isolated(baseUrl=value), r'browserTest\.isolated\.baseUrl')

    def test_local_base_urls_are_accepted(self):
        fixed = [process(port=8443, health='https://127.0.0.1:8443/health')]
        for value, processes in (('http://localhost:{port}/', None), ('https://127.0.0.1:8443/app', fixed),
                                 ('http://[::1]:{port}/', None)):
            overrides = {'baseUrl': value} if processes is None else {'baseUrl': value, 'processes': processes}
            with self.subTest(baseUrl=value), tempfile.TemporaryDirectory() as root:
                inspect_file(with_isolated(**overrides), root)

    def test_a_port_placeholder_in_the_base_url_needs_an_automatic_process(self):
        """Issue 34, S4 (revisão da sessão): {port} na baseUrl só tem a que porta se referir com um processo auto."""
        fixed = [process(port=8090, health='http://127.0.0.1:8090/health')]
        self.refuse(with_isolated(processes=fixed), r'browserTest\.isolated\.baseUrl.*\{port\}')
        with tempfile.TemporaryDirectory() as root:
            inspect_file(with_isolated(processes=fixed, baseUrl='http://127.0.0.1:8090/'), root)

    def test_a_fixed_base_url_port_never_is_the_preview_port(self):
        """Issue 34, S4: a baseUrl fixa da instância isolada nunca é a da prévia nem a de um processo fixo dela."""
        fixed = [process(port=8090, health='http://127.0.0.1:8090/health')]
        preview = {'worktree': '.claude/worktrees/previa', 'branch': 'previa', 'baseUrl': 'http://127.0.0.1:8090/',
                   'processes': [process(name='previa', port=8091, health='http://127.0.0.1:8091/health')]}
        self.refuse(with_isolated(processes=fixed, baseUrl='http://127.0.0.1:8090/', preview=preview),
                    r'browserTest\.isolated\.baseUrl.*8090.*prévia')
        preview['baseUrl'] = 'http://127.0.0.1:8095/'
        self.refuse(with_isolated(processes=[process(port=8091, health='http://127.0.0.1:8091/health')],
                                  baseUrl='http://127.0.0.1:8091/', preview=preview),
                    r'browserTest\.isolated\.baseUrl.*8091.*preview\.processes')

    def test_a_fixed_base_url_port_never_is_a_port_of_the_serve(self):
        """Revisão da issue 34 (M2): a baseUrl fixa da isolada nunca é a porta de browserTest.processes nem da
        browserTest.baseUrl, mesmo com os processos isolados em auto."""
        serve_fixed = process(port=8080, health='http://127.0.0.1:8080/health')
        message = self.refuse(with_isolated(None, serve_fixed, baseUrl='http://127.0.0.1:8080/'),
                              r'browserTest\.isolated\.baseUrl.*8080.*browserTest\.processes')
        self.assertIn('web', message)
        config = with_isolated(processes=[process(port=8080, health='http://127.0.0.1:8080/health')],
                               baseUrl='http://127.0.0.1:8080/')
        config['browserTest']['baseUrl'] = 'http://127.0.0.1:8080/'
        self.refuse(config, r'browserTest\.isolated\.baseUrl.*8080.*browserTest\.baseUrl')
        config['browserTest']['baseUrl'] = 'http://127.0.0.1:{port}/'
        with tempfile.TemporaryDirectory() as root:
            inspect_file(config, root)

    def test_a_fixed_base_url_port_is_the_port_of_an_isolated_process(self):
        """Revisão da issue 34 (M2): a baseUrl fixa aponta para um processo que a sessão sobe na instância isolada."""
        cases = {'processos auto': [process()],
                 'processo fixo em outra porta': [process(port=8090, health='http://127.0.0.1:8090/health')]}
        for case, processes in cases.items():
            with self.subTest(case=case):
                message = self.refuse(with_isolated(processes=processes, baseUrl='http://127.0.0.1:8095/'),
                                      r'browserTest\.isolated\.baseUrl.*8095')
                self.assertIn('browserTest.isolated.processes', message)
        accepted = {'porta inteira': process(port=8095, health='http://127.0.0.1:8095/health'),
                    'porta do health': {'name': 'web', 'argv': ['python', 'APP_SCRIPT'],
                                        'health': 'http://localhost:8095/health'}}
        for case, item in accepted.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as root:
                inspect_file(with_isolated(processes=[process(name='api'), item], baseUrl='http://127.0.0.1:8095/'),
                             root)

    def test_process_working_folders_stay_inside_the_worktree(self):
        """Revisão da issue 34 (B7): o serve nunca sobe esses processos, então o inspect contém o cwd deles."""
        for cwd in ('../fora', 'web/../../fora', r'web\..\..\fora', 'C:/fora', 'C:fora', '/fora', r'\fora',
                    r'\\servidor\pasta'):
            with self.subTest(cwd=cwd):
                message = self.refuse(with_isolated(processes=[process(name='front', cwd=cwd)]),
                                      r'browserTest\.isolated\.processes.*front.*cwd')
                self.assertIn('relativo', message)
        for cwd in ('web', 'apps/web', r'apps\web', ''):
            with self.subTest(cwd=cwd), tempfile.TemporaryDirectory() as root:
                inspect_file(with_isolated(processes=[process(name='front', cwd=cwd)]), root)

    def test_processes_follow_the_serve_rules(self):
        cases = {'ausentes': None, 'vazios': [], 'texto': 'web',
                 'argv como texto (shell)': [process(argv='python APP_SCRIPT {port}')],
                 'sem health': [process(health=None)],
                 'auto sem {port} no health': [process(health='http://127.0.0.1:8080/health')]}
        for case, value in cases.items():
            with self.subTest(case=case):
                self.refuse(with_isolated(processes=value), r'browserTest\.isolated\.processes')

    def test_process_health_must_be_local(self):
        for health in ('http://10.0.0.5:{port}/health', 'https://app.example.com:{port}/'):
            with self.subTest(health=health):
                message = self.refuse(with_isolated(processes=[process(health=health)]),
                                      r'browserTest\.isolated\.processes')
                self.assertIn('local', message)

    def test_database_copy_and_drop_are_refused_with_a_message_to_delete_them(self):
        """Issue 69, S2: o teste assistido roda no banco de desenvolvimento local; os campos de cópia saem."""
        step = {'argv': ['python', 'DB_SCRIPT'], 'timeoutSeconds': 60}
        for fields in (('copyDatabase',), ('dropDatabase',), ('copyDatabase', 'dropDatabase')):
            for value in (step, None):
                with self.subTest(fields=fields, value=value):
                    message = self.refuse(with_isolated(**{field: value for field in fields}),
                                          r'browserTest\.isolated')
                    for field in fields:
                        self.assertIn(field, message)
                    self.assertIn('apague', message)
                    self.assertIn('banco de desenvolvimento local', message)
        with tempfile.TemporaryDirectory() as root:
            inspect_file(with_isolated(), root)

    def test_a_fixed_port_of_the_preview_is_refused(self):
        """Nunca nas portas da prévia: a porta fixa vem de `port` ou, sem ele, da porta do health."""
        fixed = [process(port=8080, health='http://127.0.0.1:8080/health'),
                 {'name': 'web', 'argv': ['python', 'APP_SCRIPT'], 'health': 'http://127.0.0.1:8080/'}]
        for mine in fixed:
            for theirs in (process(port=8080, health='http://127.0.0.1:8080/health'),
                           {'name': 'web', 'argv': ['python', 'APP_SCRIPT'], 'health': 'http://127.0.0.1:8080/'}):
                with self.subTest(isolated=mine, preview=theirs):
                    preview = {'processes': [process(name='api'), theirs]}
                    message = self.refuse(with_isolated(processes=[mine], preview=preview),
                                          r'browserTest\.isolated\.processes')
                    self.assertIn('8080', message)
                    self.assertIn('preview.processes', message)

    def test_a_fixed_port_of_the_browser_test_processes_is_refused(self):
        theirs = process(port=8080, health='http://127.0.0.1:8080/health')
        mine = {'name': 'web', 'argv': ['python', 'APP_SCRIPT'], 'health': 'http://localhost:8080/health'}
        message = self.refuse(with_isolated(None, theirs, processes=[mine]), r'browserTest\.isolated\.processes')
        self.assertIn('8080', message)
        self.assertIn('browserTest.processes', message)

    def test_automatic_or_distinct_ports_never_collide(self):
        fixed = process(argv=['python', 'APP_SCRIPT', '8080'], port=8080, health='http://127.0.0.1:8080/health')
        preview = preview_block(baseUrl='http://127.0.0.1:8080/', processes=[fixed])
        # the serve process of the assisted test never shares the preview port either (3rd review of issue 34, B)
        serve_fixed = process(port=8081, health='http://127.0.0.1:8081/health')
        configs = {'isolada automática': with_isolated(None, serve_fixed, preview=preview),
                   'portas fixas diferentes': with_isolated(
                       None, serve_fixed, preview=preview,
                       processes=[process(port=8090, health='http://127.0.0.1:8090/health')],
                       baseUrl='http://127.0.0.1:8090/')}
        for case, config in configs.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as root:
                inspect_file(config, root)
        # the inspect refuses these preview blocks on their own (PreviewBlockTests); the isolated rule only reads
        # what it can and never fails on them
        lenient = {'prévia sem processes legíveis': with_isolated(
                       preview={'processes': 'web'}, processes=[process(port=8080, health='http://127.0.0.1:8080/')],
                       baseUrl='http://127.0.0.1:8080/'),
                   'prévia que não é objeto': with_isolated(preview=['web'])}
        for case, config in lenient.items():
            with self.subTest(case=case):
                frontlights.validate_isolated_block(config)

    def test_refusals_never_show_the_test_login_or_password(self):
        """Login e senha fictícios de browserTest.users num argv (e no nome que a recusa cita) saem mascarados."""
        login = 'usuario@exemplo.test'
        secret = ['--login', login, '--password', PASSWORD]
        named = {'name': f'{login}-{PASSWORD}', 'argv': ['python', 'APP_SCRIPT'] + secret,
                 'health': 'http://127.0.0.1:8080/health'}
        cases = {'copyDatabase recusado': (with_isolated(copyDatabase={'argv': ['python', 'COPY_DB_SCRIPT'] + secret}),
                                           r'copyDatabase'),
                 'processo com health não local': (
                     with_isolated(processes=[dict(named, health='http://10.0.0.5:8080/health')]), 'não é local'),
                 'processo na porta da prévia': (
                     with_isolated(processes=[named], preview={'processes': [dict(named, argv=['python', 'X'])]}),
                     'preview.processes')}
        for case, (config, pattern) in cases.items():
            with self.subTest(case=case):
                message = self.refuse(config, pattern)
                self.assertNotIn(login, message)
                self.assertNotIn(PASSWORD, message)

    def test_the_example_declares_the_block_with_generic_markers_and_is_accepted(self):
        block = EXAMPLE['browserTest']['isolated']
        self.assertEqual(block['baseUrl'], 'http://127.0.0.1:{port}/')
        self.assertTrue(all(item['port'] == 'auto' and item['health'].startswith('http://127.0.0.1:{port}/')
                            for item in block['processes']))
        self.assertNotIn('copyDatabase', block)
        self.assertNotIn('dropDatabase', block)
        with tempfile.TemporaryDirectory() as root:
            inspect_file(local(EXAMPLE), root)


def codes(result):
    return sorted(w.split(':')[0] for w in result.get('warnings', []) if w.startswith(SETUP_CODES))


def fake_gh(issues, boards=None):
    """Um gh de mentira: responde às consultas GraphQL de `closeout` (apelidos i<n>) com a tabela `issues`
    ({n: {state, title, parent, children: [n | 'outro/repo#n']}}) e ao `project list` com `boards`."""
    def node(n):
        item = issues.get(n)
        if item is None:
            return None
        kids = []
        for kid in item.get('children', []):
            if isinstance(kid, str):
                repo, _, k = kid.partition('#')
                kids.append({'number': int(k), 'state': 'OPEN', 'repository': {'nameWithOwner': repo}})
            else:
                kids.append({'number': kid, 'state': issues[kid]['state'],
                             'repository': {'nameWithOwner': 'OWNER/REPOSITORY'}})
        parent = item.get('parent')
        return {'number': n, 'state': item['state'], 'title': item['title'], 'body': '',
                'parent': None if parent is None else {'number': parent,
                                                       'repository': {'nameWithOwner': 'OWNER/REPOSITORY'}},
                'subIssues': {'totalCount': len(kids), 'nodes': kids}}

    def gh(argv):
        if argv[:2] == ['project', 'list']:
            return boards
        query = next(a for a in argv if a.startswith('query='))
        wanted = [int(n) for n in re.findall(r'i(\d+): issue', query)]
        return {'data': {'repository': {f'i{n}': node(n) for n in wanted}}}
    return gh


class SetupWarningsTests(unittest.TestCase):
    """Issue 11, S1: o inspect nomeia o que falta na configuração, um código por linha em `warnings`."""

    def test_a_config_without_browser_test_or_board_says_so_and_null_declares_them(self):
        with tempfile.TemporaryDirectory() as root, patch.object(frontlights, 'run', side_effect=OSError):
            self.assertEqual(codes(frontlights.inspect({'repository': 'OWNER/REPOSITORY'}, root)),
                             ['browser_test_missing', 'project_unresolved'])
            self.assertEqual(codes(frontlights.inspect({'repository': 'OWNER/REPOSITORY', 'project': None,
                                                        'browserTest': None}, root)), [])
            self.assertEqual(codes(frontlights.inspect({'repository': None, 'browserTest': None}, root)), [])

    def test_a_legacy_workflows_folder_is_named(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / '.workflows').mkdir()
            result = frontlights.inspect({'repository': None, 'browserTest': None}, root)
            self.assertEqual(codes(result), ['legacy_workflows_dir'])
            self.assertIn('renomeie', result['warnings'][0])
            (Path(root) / '.frontlights').mkdir()
            self.assertIn('use .frontlights/', frontlights.inspect({'repository': None, 'browserTest': None},
                                                                   root)['warnings'][0])

    def test_in_git_the_ignore_line_and_the_branch_prefix_are_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            root = gitfixture.init(Path(folder) / 'repo')
            config = {'repository': None, 'browserTest': None}
            self.assertEqual(codes(frontlights.inspect(config, root)),
                             ['branch_prefix_missing', 'frontlights_not_ignored'])
            (root / '.git' / 'info').mkdir(exist_ok=True)
            (root / '.git' / 'info' / 'exclude').write_text('/.frontlights/\n', encoding='utf-8')
            self.assertEqual(codes(frontlights.inspect(config, root)), ['branch_prefix_missing'])
            self.assertEqual(codes(frontlights.inspect(dict(config, branchPrefix='nome/'), root)), [])
            (root / '.frontlights').mkdir()
            (root / '.frontlights' / 'authorization.json').write_text(json.dumps({'branch_prefix': 'nome/'}),
                                                                     encoding='utf-8')
            self.assertEqual(codes(frontlights.inspect(config, root)), [])


class InspectOfflineAndFamilyTests(unittest.TestCase):
    """Issue 11, S1: `--offline` não lê a rede; `--issue <n>` traz a família por `closeout.expand`."""

    FAMILY = {10: {'state': 'OPEN', 'title': 'Pai', 'children': [11, 12, 'outro/repo#5']},
              11: {'state': 'OPEN', 'title': 'Filha aberta', 'parent': 10, 'children': [13]},
              12: {'state': 'CLOSED', 'title': 'Filha fechada', 'parent': 10},
              13: {'state': 'OPEN', 'title': 'Neta', 'parent': 11}}

    def test_offline_reads_nothing_and_names_each_configured_source(self):
        def forbidden(*args, **kwargs):
            raise AssertionError('leitura de rede no modo offline')
        config = {'repository': 'OWNER/REPOSITORY', 'project': None, 'browserTest': None,
                  'roads': {'observations_url': 'https://roads.example.com/x', 'token_env': 'NADA'}}
        with tempfile.TemporaryDirectory() as root, patch.object(frontlights, 'run', forbidden), \
                patch.object(frontlights.urllib.request, 'build_opener', forbidden):
            result = frontlights.inspect(config, root, offline=True, issue=10, gh=forbidden)
        self.assertEqual(result['sources'], {'github': {'status': 'offline'}, 'project': {'status': 'unconfigured'},
                                             'roads': {'status': 'offline'}})
        self.assertEqual(result['family'], {'status': 'offline', 'issue': 10})

    def test_the_family_lists_open_descendants_history_and_excluded(self):
        with tempfile.TemporaryDirectory() as root, patch.object(frontlights, 'run', side_effect=OSError):
            result = frontlights.inspect({'repository': 'OWNER/REPOSITORY', 'project': None, 'browserTest': None},
                                         root, issue=10, gh=fake_gh(self.FAMILY))
        family = result['family']
        self.assertEqual((family['status'], family['issue'], family['title'], family['open_count']),
                         ('available', 10, 'Pai', 2))
        self.assertEqual(family['open'], [{'number': 11, 'title': 'Filha aberta', 'parent': 10},
                                          {'number': 13, 'title': 'Neta', 'parent': 11}])
        self.assertEqual((family['history'], family['excluded'], family['truncated']), ([12], ['outro/repo#5'], False))

    def test_an_issue_without_sub_issues_has_an_empty_family_and_a_failed_read_is_unavailable(self):
        lone = {7: {'state': 'OPEN', 'title': 'Sozinha'}}
        self.assertEqual(frontlights.issue_family('OWNER/REPOSITORY', 7, fake_gh(lone))['open_count'], 0)
        self.assertEqual(frontlights.issue_family('OWNER/REPOSITORY', 8, fake_gh(lone))['status'], 'unavailable')
        broken = frontlights.issue_family('OWNER/REPOSITORY', 7, lambda argv: {'message': 'erro'})
        self.assertEqual(broken['status'], 'unavailable')
        self.assertEqual(frontlights.issue_family(None, 7)['status'], 'unconfigured')

    def test_the_cli_takes_offline_and_issue(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / 'config.json'
            config.write_text(json.dumps({'repository': 'OWNER/REPOSITORY', 'browserTest': None}), encoding='utf-8')
            run = subprocess.run([sys.executable, str(SCRIPT), 'inspect', '--config', str(config), '--root', root,
                                  '--offline', '--issue', '3', '--summary'],
                                 capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run.returncode, 0, run.stderr)
        out = json.loads(run.stdout)
        self.assertEqual((out['sources']['github'], out['family']['status']), ({'status': 'offline'}, 'offline'))
        self.assertEqual(codes(out), ['project_unresolved'])

    def test_without_a_config_the_cli_points_to_init_config(self):
        with tempfile.TemporaryDirectory() as root:
            run = subprocess.run([sys.executable, str(SCRIPT), 'inspect', '--root', root],
                                 capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run.returncode, 0, run.stderr)
        out = json.loads(run.stdout)
        self.assertEqual(out['status'], 'config_missing')
        self.assertIn('init-config', out['hint'])
        self.assertIn('references/setup.md', out['hint'])


class InitConfigTests(unittest.TestCase):
    """Issue 11, S1: `init-config` grava só na worktree principal, `repository` do origin, nunca `project`."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.root = gitfixture.init(self.folder / 'repo')
        (self.root / 'LEIA.md').write_text('x\n', encoding='utf-8')
        gitfixture.git(self.root, 'add', '.')
        gitfixture.git(self.root, 'commit', '-q', '-m', 'base')

    def config(self):
        return json.loads((self.root / '.frontlights' / 'config.json').read_text(encoding='utf-8'))

    def test_repository_from_origin_never_the_project_key_and_the_boards_come_back(self):
        gitfixture.git(self.root, 'remote', 'add', 'origin', 'https://github.com/OWNER/REPOSITORY.git')
        boards = {'projects': [{'number': 3, 'title': 'Quadro', 'url': 'https://github.com/orgs/OWNER/projects/3'}]}
        result = frontlights.init_config(self.root, gh=fake_gh({}, boards))
        self.assertEqual(self.config(), {'repository': 'OWNER/REPOSITORY'})
        self.assertEqual(result['boards'], [{'number': 3, 'title': 'Quadro',
                                             'url': 'https://github.com/orgs/OWNER/projects/3'}])
        self.assertIn('project_unresolved', ' '.join(result['warnings']))
        self.assertIn('quadro', result['message'])

    def test_ssh_remote_prefix_and_unreadable_boards(self):
        gitfixture.git(self.root, 'remote', 'add', 'origin', 'git@github.com:OWNER/REPOSITORY.git')
        result = frontlights.init_config(self.root, prefix='nome/', gh=lambda argv: None)
        self.assertEqual(self.config(), {'repository': 'OWNER/REPOSITORY', 'branchPrefix': 'nome/'})
        self.assertIsNone(result['boards'])

    def test_no_remote_is_a_local_project(self):
        result = frontlights.init_config(self.root, gh=fake_gh({}))
        self.assertEqual((self.config(), result['boards']), ({'repository': None}, []))

    def test_refusals_write_nothing(self):
        gitfixture.git(self.root, 'remote', 'add', 'upstream', 'https://github.com/OWNER/A.git')
        gitfixture.git(self.root, 'remote', 'add', 'fork', 'https://github.com/OWNER/B.git')
        with self.assertRaises(frontlights.Stage6Refusal) as caught:
            frontlights.init_config(self.root, gh=fake_gh({}))
        self.assertEqual(caught.exception.reason, 'ambiguous_remote')
        self.assertFalse((self.root / '.frontlights' / 'config.json').exists())
        frontlights.init_config(self.root, repository='OWNER/A', gh=fake_gh({}, {'projects': []}))
        with self.assertRaises(frontlights.Stage6Refusal) as caught:
            frontlights.init_config(self.root, repository=None)
        self.assertEqual(caught.exception.reason, 'config_exists')
        linked = self.folder / 'linked'
        gitfixture.git(self.root, 'worktree', 'add', '-q', '-b', 'outra', str(linked))
        with self.assertRaises(frontlights.Stage6Refusal) as caught:
            frontlights.init_config(linked, repository=None)
        self.assertEqual(caught.exception.reason, 'not_main_worktree')
        self.assertFalse((linked / '.frontlights').exists())

    def test_a_non_github_origin_is_ambiguous_and_the_cli_answers_json(self):
        gitfixture.git(self.root, 'remote', 'add', 'origin', 'https://example.com/x.git')
        run = subprocess.run([sys.executable, str(SCRIPT), 'init-config', '--root', str(self.root)],
                             capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run.returncode, 1)
        self.assertEqual(json.loads(run.stdout)['reason'], 'ambiguous_remote')
        run = subprocess.run([sys.executable, str(SCRIPT), 'init-config', '--root', str(self.root),
                              '--repository', 'null'], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.config(), {'repository': None})


class SetupReferenceTests(unittest.TestCase):
    """Issue 11, S2: `references/setup.md` (~200 palavras) só quando o inspect relata config ou bloco ausente."""

    def setUp(self):
        skill = ROOT / 'skills' / 'frontlights'
        self.text = ' '.join((skill / 'references' / 'setup.md').read_text(encoding='utf-8').split())
        self.skill = (skill / 'SKILL.md').read_text(encoding='utf-8')

    def test_it_is_short_and_read_only_on_a_setup_report(self):
        self.assertLessEqual(len(self.text.split()), 220)
        self.assertTrue(self.text.startswith('# Setup Read when: `inspect` reports `config_missing` or a setup warning'))
        self.assertIn('| references/setup.md | `inspect` reports `config_missing` or a setup warning |', self.skill)
        for code in ('browser_test_missing', 'project_unresolved', 'branch_prefix_missing'):
            with self.subTest(code=code):
                self.assertIn(code, self.text)
                self.assertIn(code, (ROOT / 'skills' / 'frontlights' / 'scripts' / 'frontlights.py').read_text(
                    encoding='utf-8'))

    def test_init_config_never_writes_the_board_and_the_board_is_asked(self):
        self.assertIn('`frontlights.py init-config` writes `.frontlights/config.json` in the main worktree', self.text)
        self.assertIn('never the `project` key', self.text)
        self.assertIn('(`references/issues.md`, "Project board")', self.text)

    def test_browser_test_null_with_a_visible_file_is_one_question_never_a_skipped_gate(self):
        self.assertIn('`browserTest: null` with a visible file in the diff (`browser-gate` says `unconfigured`) is one '
                      'question, never a skipped gate, the closing inside its options', self.text)
        self.assertIn('the block itself is proved by `serve.py start` and `stop` at the first opening of stage 6', self.text)

    def test_the_test_password_is_masked_in_the_stamped_draft(self):
        self.assertIn('approved by link and stamp as a draft under `.frontlights/`, every '
                      '`browserTest.users[].password` shown as `***`', self.text)
        self.assertIn('The real value goes only into the final config, after the approval, and is never printed', self.text)


if __name__ == '__main__':
    unittest.main()
