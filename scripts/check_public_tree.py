#!/usr/bin/env python3
"""Check publishable Git content for likely private material; never print values."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_DIRS = {'.local', '..local', 'private', 'backups', 'runs', 'vendor', '.venv', '__pycache__'}
FORBIDDEN_SUFFIXES = {'.bin', '.hex', '.elf', '.o', '.map', '.zip', '.7z', '.jpg', '.jpeg', '.png', '.pem', '.key', '.p12', '.pfx'}
PATTERNS = {
    'private key': re.compile(r'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----'),
    'GitHub token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'API token': re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b'),
    'AWS access key': re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    'credentialed URL': re.compile(r'https?://[^\s/:@]+:[^\s/@]+@'),
    'personal absolute path': re.compile(r'/(?:home|Users)/[A-Za-z0-9_.-]+(?:/|\b)'),
    'private workspace reference': re.compile(r'\.open' r'claw|codex-remote-' r'attachments'),
    'private IPv4 address': re.compile(r'(?<![\d.])(?:10\.(?:\d{1,3}\.){2}\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?![\d.])'),
    'literal chip UID': re.compile(r'(?i)[\"\'](?:uid|uid_hex|chip_uid)[\"\']\s*:\s*[\"\'][0-9a-f]{24}[\"\']'),
}


def git(*args: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def inspect_content(name: str, data: bytes) -> list[str]:
    path = Path(name)
    issues = []
    if set(path.parts) & FORBIDDEN_DIRS or path.suffix.lower() in FORBIDDEN_SUFFIXES:
        issues.append(f'{name}: private/generated/third-party artifact path')
    if path.name == '.env' or (path.name.startswith('.env.') and path.name != '.env.example'):
        issues.append(f'{name}: environment credentials file')
    try:
        content = data.decode('utf-8')
    except UnicodeDecodeError:
        issues.append(f'{name}: non-text content requires explicit publication review')
        return issues
    for number, line in enumerate(content.splitlines(), 1):
        for label, pattern in PATTERNS.items():
            if pattern.search(line):
                issues.append(f'{name}:{number}: {label}')
    return issues


def inspect_tree(staged: bool) -> tuple[list[str], int]:
    options = ['ls-files', '-z'] if staged else ['ls-files', '--cached', '--others', '--exclude-standard', '-z']
    names = sorted(set(git(*options).decode().split('\0')) - {''})
    issues = []
    checked = 0
    for name in names:
        if staged:
            data = git('show', ':' + name)
        else:
            path = ROOT / name
            if not path.exists():
                continue
            if path.is_symlink():
                issues.append(f'{name}: symlink requires explicit publication review')
                continue
            data = path.read_bytes()
        issues.extend(inspect_content(name, data))
        checked += 1
    return issues, checked


def inspect_history() -> tuple[list[str], int]:
    issues = []
    checked = 0
    for item in git('rev-list', '--objects', '--all').decode().splitlines():
        oid, _, name = item.partition(' ')
        if git('cat-file', '-t', oid).strip() != b'blob':
            continue
        issues.extend(inspect_content(name or oid, git('cat-file', 'blob', oid)))
        checked += 1
    return issues, checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true', help='Inspect index contents, not working copies.')
    parser.add_argument('--history', action='store_true', help='Also inspect all reachable Git blobs.')
    args = parser.parse_args()
    issues, count = inspect_tree(args.staged)
    if args.history:
        extra, total = inspect_history()
        issues.extend(extra)
        count += total
    if issues:
        print('\n'.join(sorted(set(issues))))
        print('Review required. Matching values were not printed.')
        return 1
    print(f'Checked {count} text files/blobs: no configured patterns found. Manual review still required.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
