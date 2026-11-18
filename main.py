"""Command-line entry point. Importing this module has no side effects."""

import argparse
import json
import os
from pathlib import Path
import sys

from batch_processor import deliver, process, verify

ROOT = Path(__file__).resolve().parent


def load_config():
    values = {}
    path = ROOT / '.env'
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            key, separator, value = line.partition('=')
            if not separator:
                raise ValueError('Configuration requires KEY=value lines.')
            values[key.strip()] = value.strip().strip('\"\'')
    values.update(os.environ)
    return values


def main(argv=None):
    parser = argparse.ArgumentParser(description='Split and validate delimited file batches.')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('demo', help='Run the bundled synthetic example locally.')
    run = commands.add_parser('run')
    run.add_argument('--input', type=Path, required=True)
    run.add_argument('--output', type=Path)
    run.add_argument('--delivery', type=Path)
    run.add_argument('--group-column')
    run.add_argument('--delimiter')
    check = commands.add_parser('verify')
    check.add_argument('batch', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'verify':
            print(json.dumps(verify(args.batch), indent=2))
            return 0
        if args.command == 'demo':
            batch = process(ROOT / 'examples/input/events.txt', ROOT / 'runtime/processed')
            delivery = ROOT / 'runtime/delivery'
        else:
            config = load_config()
            batch = process(args.input, args.output or Path(config.get('OUTPUT_DIR', 'runtime/processed')),
                            args.group_column or config.get('GROUP_COLUMN', 'group'),
                            args.delimiter or config.get('DELIMITER', '|'))
            delivery = args.delivery or config.get('DELIVERY_DIR')
        published = deliver(batch, delivery) if delivery else None
        manifest = verify(batch)
        print(json.dumps({'batch': str(batch), 'delivery': str(published) if published else None,
                          'records': manifest['records'], 'groups': len(manifest['files'])}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
