#!/usr/bin/env python3
"""
Recover MSCZ - A Python data recovery tool for MuseScore .mscz files.

MIT License

Copyright (c) 2022 Riccardo Poggi

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from contextlib import contextmanager
from pathlib import Path
import subprocess
import zipfile
import shutil
import struct
import re
import os

import logging as log

__version__ = '0.1'


def get_mscx_filename(archive):
    """Return the mscx file name stored inside the archive, if available."""

    # The file name is in the second local file header with format: title.mscx

    file_name = None
    for n, lf_m in enumerate(re.finditer(zipfile.stringFileHeader, archive)):
        if n == 0:
            # skip the first local file header
            continue
        if n == 2:
            # stop after the second local file header
            break

        h_start = lf_m.start()
        h_end = lf_m.start() + zipfile.sizeFileHeader

        buffer = archive[h_start:h_end]
        lf = struct.unpack(zipfile.structFileHeader, buffer)

        file_name = archive[h_end:h_end + lf[zipfile._FH_FILENAME_LENGTH]]

    try:
        file_name = file_name.decode('utf-8')
    except AttributeError:
        pass

    return file_name


def get_safe_to_save_path(path):
    """Return a path that doesn't overwrite any other existing file."""
    if not path.is_file():
        return path

    # add counter '_(1)' in file name stem or increment counter by 1
    sub_stem = re.sub(
        r'(?<=_\()\d+(?=\))',
        lambda m: str(int(m.group(0)) + 1),
        path.stem
    )

    if sub_stem == path.stem:
        new_stem = path.stem + '_(1)'
    else:
        new_stem = sub_stem

    return get_safe_to_save_path(path.with_stem(new_stem))


def get_disk_size(disk_path):
    """Return the size of a disk (e.g. /dev/sbd1) in bytes."""
    result = subprocess.run(['/usr/bin/df', '--all'], capture_output=True)
    for line in result.stdout.decode('utf-8').split('\n'):
        fs, _ = line.split(maxsplit=1)
        if fs == str(disk_path):
            fs, blocks, used, avail, perc, mnt = line.split()
            return int(blocks) * 1024


def human_readable_size(size, power=2):
    """Return formatted string with a human redable size."""

    units = {
        2: ['B', 'KiB', 'MiB', 'GiB', 'TiB'],
        10: ['B', 'KB', 'MB', 'GB', 'TB'],
    }

    kilo = {
        2: 1024,
        10: 1000
    }

    for unit, decimal_places in zip(units[power], [0, 0, 1, 1, 1]):
        if size < kilo[power]:
            break

        size /= kilo[power]

    return f'{size:.{decimal_places}f}{unit}'


@contextmanager
def pbar(total, width=30):
    def bar(current, msg=''):
        progress = current / total
        fill = '=' * int((width - 2) * progress)
        perc = round(progress * 100)

        if perc == 100:
            fill = '=' * (width - 2)
        bar = f'|{fill: <28}| {perc}%'

        out = bar

        if msg:
            out = f'{msg} {out}'

        print(out, end='\r')

    try:
        yield bar
    finally:
        print()


def main(args):

    # the chunks will have a margin of overlap to make sure that the EOCD
    # signature is not missed.
    #
    # technically we don't need twice the length of the signature, but melius
    # abundare quam deficere
    margin = len(zipfile.stringEndArchive) * 2

    chunk_start = args.seek
    chunk_end = None

    if args.disk:
        file_size = get_disk_size(args.file_path)
    else:
        file_size = args.file_path.stat().st_size
        if file_size == 0:
            # let's try if it was a disk
            file_size = get_disk_size(args.file_path)


    if args.parse_len is not None:
        parse_size = args.parse_len
    else:
        parse_size = file_size - args.seek

    log.info(f'Input file: {args.file_path}, '
             f'size: {human_readable_size(file_size, 10)}, '
             f'to be parsed: {human_readable_size(parse_size, 10)}')

    with open(args.file_path, 'rb') as f:
        with pbar(total=parse_size) as bar:
            while True:
                if chunk_end is not None:
                    chunk_start = chunk_end - margin

                msg = f'Reading chunk at {hex(chunk_start)}'
                log.debug(msg)
                bar(chunk_start - args.seek, msg=msg)

                f.seek(chunk_start)
                chunk = f.read(args.chunk_size)
                chunk_end = f.tell()

                if chunk_end - chunk_start <= margin:
                    print()
                    log.info('Reached EOF' + ' ' * 30)
                    break

                for m in re.finditer(zipfile.stringEndArchive, chunk):

                    # go back to beginning of the header
                    f.seek(chunk_start + m.start(), os.SEEK_SET)

                    buffer = f.read(zipfile.sizeEndCentDir)
                    ecd = struct.unpack(zipfile.structEndArchive, buffer)

                    # MuseScore files have exactly 3 entries:
                    # - container.xml
                    # - title.mscx
                    # - thumbnail.png
                    #
                    # so the following is a quick check
                    if not (ecd[zipfile._ECD_ENTRIES_THIS_DISK] ==
                            ecd[zipfile._ECD_ENTRIES_TOTAL] == 3):
                        continue

                    archive_size = (ecd[zipfile._ECD_SIZE] +
                                    ecd[zipfile._ECD_OFFSET] +
                                    ecd[zipfile._ECD_COMMENT_SIZE] +
                                    zipfile.sizeEndCentDir)

                    f.seek(-archive_size, os.SEEK_CUR)

                    # extract the bytes corresponding to the zip archive
                    archive = f.read(archive_size)

                    # this is too slow
                    # z = zipfile.ZipFile(io.BytesIO(archive))
                    # file_name = z.namelist()[1]

                    # this is faster
                    file_name = get_mscx_filename(archive)

                    if file_name is not None:
                        file_path = Path(file_name)

                        if file_path.suffix == '.mscx':
                            # hurray! we found one!
                            log.info(f'Found a .ZIP corresponding to a .mscz '
                                     f'file at {hex(f.tell())}, '
                                     f'size: {archive_size} bytes')

                            # the actual file suffix is .mscz
                            # reuse the same stem and change suffix
                            file_path = file_path.with_suffix('.mscz')

                            output_path = args.output_dir / file_path

                            output_path = get_safe_to_save_path(output_path)

                            log.info(f"Saving '{file_path} "
                                     f"file to {output_path}")
                            with open(output_path, 'wb') as out_file:
                                out_file.write(archive)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description="Recover .mscz MuseScore files"
    )

    parser.add_argument(
        '--file-path',
        '-f',
        type=Path,
        required=True,
        help='path to the file to parse'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('out'),
        help='path to the output directory [default: %(default)s]'
    )
    parser.add_argument(
        '--seek',
        '-s',
        type=int,
        default=0,
        help='start bytes infile offset [default: %(default)s]'
    )
    parser.add_argument(
        '--chunk-size',
        '-c',
        type=int,
        default=int(16e6),
        help='chunk size in bytes [default: %(default)s]'
    )
    parser.add_argument(
        '--parse-len',
        '-l',
        type=int,
        help='how many bytes to parse (approximately)'
    )
    parser.add_argument(
        '--disk',
        action='store_true',
        help='flag if the file is a disk, e.g. /dev/sdb1'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='set logging output at DEBUG level'
    )

    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    log.basicConfig(
        format='[%(levelname)s] %(message)s',
        level=log.DEBUG if args.verbose else log.INFO
    )

    main(args)
