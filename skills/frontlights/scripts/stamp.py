#!/usr/bin/env python3
"""Approval stamp (issue 61): binds a user's approval of a document to the exact content of the file.

Usage: frontlights.py stamp <file> [--root <project>] [--revision rN] [--approve --answer "<literal answer>"
       [--stage N]] [--check] [--expect <sha12>]   (--approve requires --expect and does not combine with --check)

Prints one JSON object: `ok`, `exitCode`, `operation` ("stamp"), `message` (Portuguese, for the user), `path`
(relative to --root when the file is inside it, else as given; forward slashes), `revision` (from --revision, else
null), `sha256` (the first 12 hex characters of the sha256 of the raw bytes) and `bytes` (the size).

  --approve  appends one entry to <root>/.frontlights/approvals.json (a JSON list, created when absent, existing
             entries kept, extra keys included): path, revision, sha256, bytes, answer (verbatim), stage (when
             given) and at (ISO-8601 in America/Sao_Paulo, with its offset, never UTC). Requires --answer and
             --expect with the stamp shown in the question; when the file's stamp differs from it, nothing is
             written and it exits 1 (the file changed since the question: ask the approval again). Together with
             --check it is a usage error (exit 1, nothing written): --check runs later, right before the write.
  --check    compares the file with the last approval recorded for the same path: 0 when the stamp matches, 1 when
             it differs (with `approved`: the revision and sha256 of that approval) or when there is none.
  --expect   0 when the stamp equals the given one, 1 otherwise.

A missing file, an unreadable or malformed approvals file and a usage error exit 1 with `ok: false`, never a
traceback. `--root` defaults to the current directory. Standard library only.
"""
import argparse
import hashlib
import json
import os
import sys
import zoneinfo
from datetime import datetime
from pathlib import Path

ZONE = 'America/Sao_Paulo'
APPROVALS = Path('.frontlights') / 'approvals.json'
STAMP_LENGTH = 12


class Refusal(Exception):
    pass


class JsonParser(argparse.ArgumentParser):
    def error(self, message):
        raise Refusal(f'uso inválido do stamp: {message}')


def build_parser():
    parser = JsonParser(prog='frontlights.py stamp', allow_abbrev=False,
                        description='Carimbo de aprovação: liga a aprovação de um documento ao conteúdo exato.')
    parser.add_argument('file', help='the document to stamp')
    parser.add_argument('--root', default='.', help='the project whose .frontlights/approvals.json is used')
    parser.add_argument('--revision', help='the revision of the document, such as r2')
    parser.add_argument('--approve', action='store_true', help='record the approval (requires --answer and --expect with the stamp shown in the question)')
    parser.add_argument('--answer', help="the user's answer, verbatim")
    parser.add_argument('--stage', type=int, help='the stage of the approval')
    parser.add_argument('--check', action='store_true', help='compare with the last approval of the same path')
    parser.add_argument('--expect', help='the expected 12-character stamp')
    return parser


def zoned_now():
    """Now in ZONE, with its offset; the machine's local zone when ZONE is unavailable (no tzdata)."""
    try:
        return datetime.now(zoneinfo.ZoneInfo(ZONE))
    except (KeyError, OSError, ValueError):
        return datetime.now().astimezone()


def shown_path(file, root):
    """`file` relative to `root` when inside it, else as given; forward slashes in both cases."""
    try:
        return Path(os.path.abspath(file)).relative_to(Path(os.path.abspath(root))).as_posix()
    except ValueError:
        return str(file).replace('\\', '/')


def read_approvals(path):
    if not path.exists():
        return []
    try:
        entries = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise Refusal(f'não consegui ler {APPROVALS.as_posix()}: {type(error).__name__}') from error
    if not isinstance(entries, list):
        raise Refusal(f'{APPROVALS.as_posix()} precisa ser uma lista JSON')
    return entries


def run(args):
    if args.approve and args.check:
        raise Refusal('--approve e --check não se combinam: a aprovação confere o carimbo com --expect, e o --check '
                      'roda depois, logo antes da escrita que a aprovação cobre; nada foi gravado')
    if args.approve and args.answer is None:
        raise Refusal('--approve precisa de --answer com a resposta literal do usuário')
    if args.approve and args.expect is None:
        raise Refusal('--approve precisa de --expect com o carimbo mostrado na pergunta; nada foi gravado')
    root = Path(args.root)
    path = shown_path(args.file, root)
    try:
        data = Path(args.file).read_bytes()
    except OSError as error:
        raise Refusal(f'arquivo não encontrado ou ilegível: {path}') from error
    result = {'ok': True, 'exitCode': 0, 'operation': 'stamp', 'path': path, 'revision': args.revision,
              'sha256': hashlib.sha256(data).hexdigest()[:STAMP_LENGTH], 'bytes': len(data)}
    messages = [f'carimbo de {path}: {result["sha256"]} ({len(data)} bytes)']
    if args.expect is not None:
        if args.expect.strip().lower() == result['sha256']:
            messages.append('confere com o carimbo esperado')
        else:
            result.update(ok=False, exitCode=1)
            messages.append(f'difere do carimbo esperado {args.expect.strip()[:64]}')
    if args.check:
        approvals = [entry for entry in read_approvals(root / APPROVALS)
                     if isinstance(entry, dict) and entry.get('path') == path]
        if not approvals:
            result.update(ok=False, exitCode=1)
            messages.append(f'nenhuma aprovação registrada para {path}; é preciso pedir a aprovação')
        else:
            last = approvals[-1]
            if last.get('sha256') == result['sha256']:
                messages.append(f'confere com a aprovação {last.get("revision")}')
            else:
                result.update(ok=False, exitCode=1,
                              approved={'revision': last.get('revision'), 'sha256': last.get('sha256')})
                messages.append(f'o arquivo mudou desde a aprovação {last.get("revision")}; '
                                'é preciso uma nova aprovação')
    if args.approve and result['exitCode'] != 0:
        messages.append('o arquivo mudou desde a pergunta; nada foi gravado, é preciso pedir a aprovação de novo '
                        f'com o novo carimbo {result["sha256"]}')
    elif args.approve:
        target = root / APPROVALS
        entries = read_approvals(target)
        entry = {'path': path, 'revision': args.revision, 'sha256': result['sha256'], 'bytes': len(data),
                 'answer': args.answer}
        if args.stage is not None:
            entry['stage'] = args.stage
        entry['at'] = zoned_now().isoformat(timespec='seconds')
        entries.append(entry)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.tmp')
        temporary.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        os.replace(temporary, target)
        result['approval'] = entry
        messages.append(f'aprovação registrada em {APPROVALS.as_posix()}')
    result['message'] = '; '.join(messages)
    return result


def main(argv=None):
    try:
        result = run(build_parser().parse_args(argv))
    except Refusal as error:
        result = {'ok': False, 'exitCode': 1, 'operation': 'stamp', 'message': str(error)}
    except Exception as error:  # noqa: BLE001  (a refusal in JSON, never a traceback)
        result = {'ok': False, 'exitCode': 1, 'operation': 'stamp',
                  'message': f'stamp parou num {type(error).__name__} inesperado'}
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return int(result['exitCode'])


if __name__ == '__main__':
    sys.exit(main())
