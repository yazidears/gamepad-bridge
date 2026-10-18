#!/usr/bin/env python3
"""Build the native capture helpers. Requires macOS 13+ and Command Line Tools."""
import argparse
from pathlib import Path
import platform
import subprocess

BASE = Path(__file__).resolve().parent
CODEC = BASE / 'vendor' / 'codec'
TESTS = ['h264_bit_writer_tests', 'h264_cabac_tests', 'h264_contexts_tests',
         'x264_encoder_tests', 'minih264_tests']


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test', action='store_true', help='also run codec tests')
    options = parser.parse_args()
    if platform.system() != 'Darwin':
        parser.error('capture helpers require macOS')
    # Respect an explicitly selected toolchain; xcrun otherwise uses xcode-select.
    build = BASE / 'build'
    build.mkdir(exist_ok=True)
    common = ['xcrun', 'clang++', '-std=c++20', '-O2', '-mmacosx-version-min=13.0',
              '-I' + str(CODEC)]
    objects = []
    for name in ['bit_writer', 'cabac', 'contexts', 'minih264e', 'encoder']:
        target = build / (name + '.o')
        run(*common, '-c', CODEC / 'drh/encoder/x264' / (name + '.cpp'), '-o', target)
        objects.append(target)
    run(*common, '-fobjc-arc', BASE / 'mac-capture.mm', *objects,
        '-framework', 'Foundation', '-framework', 'ScreenCaptureKit',
        '-framework', 'CoreGraphics', '-framework', 'CoreMedia',
        '-framework', 'CoreVideo', '-o', BASE / 'mac-capture')
    run('xcrun', 'swiftc', '-O', '-parse-as-library', '-swift-version', '5',
        '-target', platform.machine() + '-apple-macos13.0',
        BASE / 'AudioCapture.swift', '-o', BASE / 'audio-capture')
    for name in ['mac-capture', 'audio-capture']:
        run('codesign', '--force', '--sign', '-', BASE / name)
    if options.test:
        for name in TESTS:
            executable = build / name
            run(*common, CODEC / 'tests' / (name + '.cpp'), *objects, '-o', executable)
            subprocess.run([str(executable)], check=True, timeout=60)
            print(name + ': passed', flush=True)
    print('Built mac-capture and audio-capture.')


if __name__ == '__main__':
    main()
