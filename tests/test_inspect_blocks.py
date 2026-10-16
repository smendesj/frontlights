"""`inspect` valida os blocos browserTest e checks com as regras do serve e do checks que dependem só do config.

Sem os blocos, a saída do `inspect` não muda. Só marcadores genéricos (repositório público).
"""
import copy
import json
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


def stable(result):
    """Tira o horário da leitura, o único campo que muda entre duas execuções."""
    result = dict(result)
    result.pop('fetched_at')
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
                patch.object(frontlights.Path, 'write_text', forbidden):
            patches = [patch.object(checks, name, forbidden) for name in names]
            for item in patches:
                item.start()
            try:
                for config in ({'repository': None}, {'repository': None, 'browserTest': None, 'checks': None}):
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
        self.assertEqual(sorted(json.loads(run.stdout)), ['fetched_at', 'path_risk', 'repository', 'sources',
                                                          'verification_candidates', 'verification_commands'])


class InspectValidBlocksTests(unittest.TestCase):
    def test_example_config_is_accepted_and_does_not_change_the_output(self):
        with tempfile.TemporaryDirectory() as root:
            plain = {k: v for k, v in local(EXAMPLE).items() if k not in ('browserTest', 'checks')}
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


class FrontPathsWarningTests(unittest.TestCase):
    def test_a_browser_test_without_front_paths_warns_that_the_gate_will_guess(self):
        result = inspect_file(with_browser(front_paths=None), ROOT)
        self.assertEqual(len(result['warnings']), 1)
        self.assertIn('browserTest.frontPaths', result['warnings'][0])
        self.assertIn('browser-gate', result['warnings'][0])

    def test_declaring_them_silences_it_and_no_browser_test_has_nothing_to_warn_about(self):
        self.assertNotIn('warnings', inspect_file(with_browser(), ROOT))
        self.assertNotIn('warnings', inspect_file({'repository': None}, ROOT))


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
        self.assertEqual(len(result['warnings']), 1)
        self.assertIn('browserTest.processes', result['warnings'][0])
        self.assertIn('serve', result['warnings'][0])
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
        self.assertIn('browserTest.processes', json.loads(run.stdout)['warnings'][0])

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


def isolated(**overrides):
    """Bloco browserTest.isolated válido: instância própria, porta automática, banco copiado e descartado."""
    block = {'baseUrl': 'http://127.0.0.1:{port}/',
             'processes': [process(name='web', argv=['python', 'APP_SCRIPT', '{port}'])],
             'copyDatabase': {'argv': ['python', 'COPY_DB_SCRIPT'], 'timeoutSeconds': 600},
             'dropDatabase': {'argv': ['python', 'DROP_DB_SCRIPT'], 'timeoutSeconds': 120}}
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
    """browserTest.isolated: o teste assistido em instância própria, com banco copiado a cada teste e descartado.

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


if __name__ == '__main__':
    unittest.main()
