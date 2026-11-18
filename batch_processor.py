"""Partition delimited files and publish verified batches using local folders."""

from collections import OrderedDict
import hashlib
import json
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory

MAX_LINE_BYTES = 1024 * 1024
MAX_GROUPS = 1000


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def lines(stream):
    while data := stream.readline(MAX_LINE_BYTES + 1):
        if len(data) > MAX_LINE_BYTES:
            raise ValueError('Record exceeds 1 MiB.')
        yield data


def verify(batch):
    """Check inventory, byte lengths, record counts and SHA-256 digests."""
    batch = Path(batch)
    manifest = json.loads((batch / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('version') != 1 or not manifest.get('files'):
        raise ValueError('Invalid manifest.')
    expected = {'manifest.json'}
    total = 0
    for item in manifest['files']:
        name = item['name']
        if not re.fullmatch(r'group-[0-9a-f]{64}\.txt', name) or name in expected:
            raise ValueError('Invalid or repeated output filename.')
        expected.add(name)
        path = batch / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Missing or unsafe output file.')
        if path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
            raise ValueError('Output integrity check failed.')
        with path.open('rb') as stream:
            header = stream.readline(MAX_LINE_BYTES + 1)
            count = sum(1 for _ in lines(stream))
        if hashlib.sha256(header).hexdigest() != manifest['header_sha256']:
            raise ValueError('Header integrity check failed.')
        if count != item['records']:
            raise ValueError('Record count mismatch.')
        total += count
    if {p.name for p in batch.iterdir()} != expected or total != manifest['records']:
        raise ValueError('Batch inventory mismatch.')
    return manifest


def process(source, output, group_column='group', delimiter='|'):
    """Preserve raw record bytes; expose a batch only after full validation."""
    source, output = Path(source), Path(output)
    if len(delimiter) != 1 or delimiter in '\r\n' or ord(delimiter) > 127:
        raise ValueError('Delimiter must be one ASCII character other than newline.')
    separator = delimiter.encode('ascii')
    output.mkdir(parents=True, exist_ok=True)
    handles = OrderedDict()
    groups = {}
    source_hash = hashlib.sha256()
    with TemporaryDirectory(prefix='.staging-', dir=output) as temporary:
        staging = Path(temporary)
        try:
            with source.open('rb') as stream:
                iterator = lines(stream)
                header = next(iterator, b'')
                if not header:
                    raise ValueError('Input is empty.')
                columns = header.decode('utf-8-sig').rstrip('\r\n').split(delimiter)
                if len(columns) != len(set(columns)) or group_column not in columns:
                    raise ValueError('Missing group column or duplicate column names.')
                index = columns.index(group_column)
                source_hash.update(header)
                for number, record in enumerate(iterator, start=2):
                    fields = record.rstrip(b'\r\n').split(separator)
                    if len(fields) != len(columns):
                        raise ValueError(f'Invalid field count at line {number}.')
                    group = fields[index].decode('utf-8')
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', group):
                        raise ValueError(f'Invalid group at line {number}.')
                    source_hash.update(record)
                    if group not in groups:
                        if len(groups) >= MAX_GROUPS:
                            raise ValueError('Too many groups.')
                        name = 'group-' + hashlib.sha256(group.encode()).hexdigest() + '.txt'
                        groups[group] = {'group': group, 'name': name, 'records': 0}
                        (staging / name).write_bytes(header)
                    if group not in handles:
                        if len(handles) >= 32:
                            _, handle = handles.popitem(last=False)
                            handle.close()
                        handles[group] = (staging / groups[group]['name']).open('ab')
                    handles.move_to_end(group)
                    handles[group].write(record)
                    groups[group]['records'] += 1
        finally:
            for handle in handles.values():
                handle.close()
        if not groups:
            raise ValueError('Input contains no records.')
        for item in groups.values():
            path = staging / item['name']
            item.update(bytes=path.stat().st_size, sha256=digest(path))
        manifest = {
            'version': 1, 'source_sha256': source_hash.hexdigest(),
            'header_sha256': hashlib.sha256(header).hexdigest(),
            'group_column': group_column, 'delimiter': delimiter,
            'records': sum(item['records'] for item in groups.values()),
            'files': sorted(groups.values(), key=lambda item: item['group']),
        }
        payload = json.dumps(manifest, sort_keys=True, indent=2) + '\n'
        (staging / 'manifest.json').write_text(payload, encoding='utf-8')
        verify(staging)
        batch_id = hashlib.sha256(payload.encode()).hexdigest()
        destination = output / batch_id
        if destination.exists():
            if verify(destination) != manifest:
                raise ValueError('Existing batch differs from input.')
        else:
            staging.rename(destination)
        return destination


def deliver(batch, destination):
    """Copy to a local delivery folder; verify before making the batch visible."""
    batch, destination = Path(batch), Path(destination)
    manifest = verify(batch)
    destination.mkdir(parents=True, exist_ok=True)
    final = destination / batch.name
    if final.exists():
        if verify(final) != manifest:
            raise ValueError('Delivery already exists with different contents.')
        return final
    with TemporaryDirectory(prefix='.delivery-', dir=destination) as temporary:
        staging = Path(temporary) / 'batch'
        shutil.copytree(batch, staging)
        if verify(staging) != manifest:
            raise ValueError('Delivery verification failed.')
        staging.rename(final)
    return final
