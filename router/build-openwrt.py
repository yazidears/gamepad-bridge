#!/usr/bin/env python3
"""Build the experimental Devolo MIPS router binaries on Apple Silicon macOS."""
import argparse
import hashlib
import os
from pathlib import Path
import platform
import shutil
import struct
import sys
import subprocess
import tarfile
import urllib.request

ZIG_URL = 'https://ziglang.org/download/0.13.0/zig-macos-aarch64-0.13.0.tar.xz'
ZIG_SHA256 = '46fae219656545dfaf4dce12fb4e8685cec5b51d721beee9389ab4194d43394c'
HOSTAP_COMMIT = 'd945ddd368085f255e68328f2d3b020ceea359af'
LIBNL_COMMIT = '40493a655d8caa2ccf5206dde1e733abe2920432'
ROOT = Path(__file__).resolve().parent


def run(args, **kwargs):
    subprocess.run([str(x) for x in args], check=True, **kwargs)


def checkout(url, commit, path, env):
    run(['git', 'clone', '--no-checkout', url, path], env=env)
    run(['git', '-C', path, 'checkout', '--detach', commit], env=env)


def verify_elf(path):
    data = path.read_bytes()
    if data[:6] != b'\x7fELF\x01\x02' or struct.unpack('>H', data[18:20])[0] != 8:
        raise RuntimeError(f'Expected big-endian ELF32 MIPS: {path}')
    flags = struct.unpack_from('>I', data, 36)[0]
    if flags & 0xF0000000 != 0x70000000:
        raise RuntimeError(f'Expected MIPS32r2 ABI: {path}')
    phoff = struct.unpack_from('>I', data, 28)[0]
    phsize, phnum = struct.unpack_from('>HH', data, 42)
    if any(struct.unpack_from('>I', data, phoff + i * phsize)[0] in (2, 3)
           for i in range(phnum)):
        raise RuntimeError(f'Expected a self-contained static executable: {path}')



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, default=ROOT / 'build' / 'openwrt-mips')
    args = parser.parse_args()
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        parser.error('This recipe supports Apple Silicon macOS only.')
    if sys.version_info < (3, 12):
        parser.error('Python 3.12 or newer is required for safe archive extraction.')
    work = args.work_dir.expanduser().resolve()
    if any(c.isspace() for c in str(work)):
        parser.error('Choose a work directory without whitespace for upstream make.')
    if work.exists():
        parser.error('Use a new work directory; existing directories are never overwritten.')
    for command in ('git', 'make'):
        if not shutil.which(command):
            parser.error(f'Missing {command}; install the Xcode command line tools.')
    env = dict(os.environ)
    if not env.get('DEVELOPER_DIR') and Path('/Library/Developer/CommandLineTools').exists():
        env['DEVELOPER_DIR'] = '/Library/Developer/CommandLineTools'
    work.mkdir(parents=True)
    archive = work / 'zig.tar.xz'
    print('Downloading pinned Zig 0.13.0...', flush=True)
    urllib.request.urlretrieve(ZIG_URL, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ZIG_SHA256:
        raise RuntimeError('Zig SHA-256 mismatch; refusing to extract or execute it.')
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter='data')
    zig = work / 'zig-macos-aarch64-0.13.0' / 'zig'
    libnl = work / 'libnl-tiny'
    hostap = work / 'hostap'
    checkout('https://github.com/openwrt/libnl-tiny.git', LIBNL_COMMIT, libnl, env)
    checkout('https://chromium.googlesource.com/external/w1.fi/cgit/hostap', HOSTAP_COMMIT, hostap, env)
    run(['git', '-C', hostap, 'apply', ROOT / 'patches/hostap-gamepad.patch'], env=env)
    # A wrapper keeps CC usable by upstream Makefiles, including paths with spaces.
    import shlex
    cc = work / 'cc-mips'
    cc.write_text('#!/bin/sh\nexec ' + shlex.quote(str(zig)) + ' cc -target mips-linux-musl -mcpu=mips32r2 -msoft-float -mnan=2008 "$@"\n')
    cc.chmod(0o755)
    objects = []
    for source in sorted(libnl.glob('*.c')):
        obj = work / (source.stem + '.o')
        run([cc, '-D_GNU_SOURCE', '-Os', '-I' + str(libnl / 'include'), '-c', source, '-o', obj], env=env)
        objects.append(obj)
    library = work / 'libnl-tiny.a'
    run([zig, 'ar', 'rcs', library, *objects], env=env)
    config = '''CONFIG_DRIVER_NL80211=y
CONFIG_LIBNL_TINY=y
CONFIG_EAP=y
CONFIG_WPS=y
CONFIG_IPV6=y
CONFIG_TENDONIN=y
CONFIG_TLS=internal
CONFIG_INTERNAL_LIBTOMMATH=y
CONFIG_INTERNAL_LIBTOMMATH_FAST=y
CONFIG_NO_RADIUS=y
CONFIG_NO_ACCOUNTING=y
CONFIG_NO_VLAN=y
CONFIG_IEEE80211N=y
CONFIG_NO_RANDOM_POOL=y
CONFIG_DEBUG_FILE=y
'''
    # Make syntax does not safely support spaces in these source/library paths.
    config += f'CC={cc}\nCFLAGS += -D_GNU_SOURCE -Os -I{libnl}/include -DCONFIG_LIBNL20 -DCONFIG_LIBNL_TINY\n'
    config += 'LDFLAGS += -Wl,--strip-all -Wl,--dynamic-linker=/lib/ld-musl-mips-sf.so.1\n'
    (hostap / 'hostapd/.config').write_text(config)
    run(['make', '-C', hostap / 'hostapd', '-j4', 'LIBS+=' + str(library), 'hostapd', 'hostapd_cli'], env=env)
    output = work / 'bin'
    output.mkdir()
    for name in ('hostapd', 'hostapd_cli'):
        shutil.copy2(hostap / 'hostapd' / name, output / name)
    run([cc, '-O2', '-I' + str(ROOT), '-Wl,--strip-all', '-Wl,--dynamic-linker=/lib/ld-musl-mips-sf.so.1', ROOT / 'frame-proxy.c', '-o', output / 'gamepad-frame-proxy'], env=env)
    for binary in output.iterdir():
        verify_elf(binary)
    shutil.copy2(hostap / 'COPYING', output / 'HOSTAP-COPYING')
    shutil.copytree(libnl, output / 'libnl-tiny-source', ignore=shutil.ignore_patterns('.git'))
    (output / 'LIBNL-TINY-NOTICE').write_text(
        f'libnl-tiny source: https://github.com/openwrt/libnl-tiny at {LIBNL_COMMIT}\n'
        'License notices are in the accompanying source files (LGPL-2.1).\n'
        'Keep source and provide relinkable hostap objects when redistributing statically linked binaries.\n'
        'The complete build tree contains the objects and configuration used for this build.\n')
    print(f'Built and verified MIPS ELF binaries in {output}')
    print('Experimental original-radio ABI only; not a general OpenWrt package. No device was modified.')


if __name__ == '__main__':
    main()
