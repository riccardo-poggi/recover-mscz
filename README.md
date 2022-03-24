# Recover MSCZ

Recover MSCZ - A Python data recovery tool for MuseScore .mscz files.

Recover MSCZ is a data recovery tool designed to recover MuseScore .mscz files. It bypasses the file system and directly scans the raw underlying data, looking for MuseScore .mscz files (which are based on the ZIP file format).

## Quick Guide

Only Python 3 is required, no external dependencies.

1. Install the tool by cloning the repo
    ```sh
    git clone https://github.com/riccardo-poggi/recover-mscz.git
    ```
2. cd into the repo directory:
    ```sh
    cd recover-mscz
    ```
3. Scan a partition by running the `recover-mscz.py` script:
    ```
    ./recover-mscz.py -f /dev/sdb1 --disk
    ```


## Usage

The tool works by parsing the given input in chunks, looking for .ZIP End of Central Directory signatures and reconstructing from there the whole .mscz file.

Follows a list of the main command line options.

- The `--chunk-size` option sets the size of the chunks used to scan the input (default 16 MB).
    ```
    ./recover-mscz.py -f /dev/sdb1 --disk --chunk-size 32000000
    ```
    This parameter can be used to tune the performances of the tool.

- The `--seek` option sets a starting offset in bytes. The script will parse the input, starting from the seeked position.
    ```
    ./recover-mscz.py -f /dev/sdb1 --disk --seek 20000
    ```
 
- The `--parse-len` options sets how many bytes to parse (rounded up to the next chunk size):
    ```
    ./recover-mscz.py -f /dev/sdb1 --disk --parse-len 40000
    ```


Check the help for more options:
```
./recover-mscz.py --help
```


## LICENSE

Distributed under MIT License. See [`LICENSE`](https://github.com/riccardo-poggi/recover-mscz/blob/master/LICENSE) for more information.
