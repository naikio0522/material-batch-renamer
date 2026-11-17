"""Version metadata for packages created by this project's build script.

The checksum detects accidental changes after packaging. This marker is not a
digital signature and cannot prove the origin of a deliberately forged file.
Nothing in this module executes the selected executable.
"""
import hashlib
import json
import re
import struct
from pathlib import Path

PREFIX = b'\nMATERIAL_RENAMER_BUILD_V1\n'
SUFFIX = b'MRNV1END'
MAX_METADATA = 1024


def _hash_prefix(path, length):
    digest = hashlib.sha256()
    remaining = length
    with Path(path).open('rb') as stream:
        if stream.read(2) != b'MZ': raise ValueError('安装包不是 Windows 程序。')
        stream.seek(0)
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk: raise ValueError('安装包不完整。')
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def append_build_metadata(path, version):
    """Append version data to a newly built one-file executable."""
    if not isinstance(version, str) or not re.fullmatch(r'[0-9]{1,5}(?:\.[0-9]{1,5}){1,3}', version):
        raise ValueError('软件内部版本号无效。')
    file = Path(path)
    length = file.stat().st_size
    if length < 2: raise ValueError('安装包不完整。')
    with file.open('rb') as stream:
        stream.seek(max(0, length - len(SUFFIX)))
        if stream.read() == SUFFIX: raise ValueError('该安装包已有版本标记。')
    metadata = {'version': version, 'binary_sha256': _hash_prefix(file, length)}
    encoded = json.dumps(metadata, separators=(',', ':'), sort_keys=True).encode('ascii')
    payload = PREFIX + encoded
    if len(payload) > MAX_METADATA: raise ValueError('安装包版本标记过长。')
    with file.open('ab') as stream:
        stream.write(payload + struct.pack('<I', len(payload)) + SUFFIX)


def read_build_version(path):
    """Return package version after checking marker and the original file bytes."""
    file = Path(path)
    length = file.stat().st_size
    if length < len(SUFFIX) + 4: raise ValueError('安装包缺少版本标记，请使用配套打包工具重新生成。')
    with file.open('rb') as stream:
        stream.seek(-len(SUFFIX) - 4, 2)
        raw_size = stream.read(4)
        if stream.read(len(SUFFIX)) != SUFFIX:
            raise ValueError('安装包缺少版本标记，请使用配套打包工具重新生成。')
        size = struct.unpack('<I', raw_size)[0]
        if size < len(PREFIX) + 2 or size > MAX_METADATA or size + 4 + len(SUFFIX) >= length:
            raise ValueError('安装包版本标记无效。')
        base_length = length - size - 4 - len(SUFFIX)
        stream.seek(base_length)
        data = stream.read(size)
    if not data.startswith(PREFIX): raise ValueError('安装包版本标记无效。')
    try:
        metadata = json.loads(data[len(PREFIX):].decode('ascii'))
        version = metadata['version']
        recorded_hash = metadata['binary_sha256']
        if (not isinstance(version, str) or not re.fullmatch(r'[0-9]{1,5}(?:\.[0-9]{1,5}){1,3}', version)
                or not isinstance(recorded_hash, str) or not re.fullmatch(r'[0-9a-f]{64}', recorded_hash)):
            raise ValueError()
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise ValueError('安装包版本标记无效。') from None
    if _hash_prefix(file, base_length) != recorded_hash:
        raise ValueError('安装包内容与打包时不一致，请重新打包。')
    return version
