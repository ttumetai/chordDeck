#!/usr/bin/env python3
"""
使用 chord-extractor (Chordino/NNLS-Chroma) 从音频中提取和弦序列。

用法:
    VAMP_PATH=~/vamp-plugins uv run python extract_chords.py <音频文件> [--out 结果.csv]
"""
import argparse
import csv
import logging
import os
import sys

# chord-extractor 只在 Linux x64 上自带 .so，macOS 需自行指定插件目录
os.environ.setdefault('VAMP_PATH', os.path.expanduser('~/vamp-plugins'))

from chord_extractor.extractors import Chordino, TuningMode  # noqa: E402


def format_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def main() -> int:
    parser = argparse.ArgumentParser(description='Chordino 和弦提取测试')
    parser.add_argument('audio', help='音频文件路径 (wav/mp3/ogg/flac...)')
    parser.add_argument('--out', help='可选：把完整和弦变化序列写入 CSV')
    parser.add_argument('--top', type=int, default=25, help='控制台展示前 N 条和弦变化')
    args = parser.parse_args()

    if not os.path.isfile(args.audio):
        print(f'文件不存在: {args.audio}', file=sys.stderr)
        return 1

    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')

    # 参数为 Chordino 对通用流行歌曲的推荐值（README 同款默认）
    chordino = Chordino(
        use_nnls=True,
        roll_on=1,
        tuning_mode=TuningMode.GLOBAL,
        spectral_whitening=1,
        spectral_shape=0.7,
        boost_n_likelihood=0.1,
    )

    changes = chordino.extract(args.audio)
    print(f'\n共识别出 {len(changes)} 次和弦变化: {args.audio}\n')

    header = f'{"时间":>8}  {"和弦":<8}'
    print(header)
    print('-' * len(header))
    for c in changes[:args.top]:
        print(f'{format_time(c.timestamp):>8}  {c.chord:<8}')
    if len(changes) > args.top:
        print(f'... 其余 {len(changes) - args.top} 条见输出文件/全量结果')

    if args.out:
        with open(args.out, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp_sec', 'time', 'chord'])
            for c in changes:
                writer.writerow([f'{c.timestamp:.3f}', format_time(c.timestamp), c.chord])
        print(f'\n完整序列已写入: {args.out}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
