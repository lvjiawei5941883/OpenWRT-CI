#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""本地构建调优补丁（幂等）。

由 Sync-Upstream 在 merge 上游之后调用，保证下列定制不被 `-X theirs` 覆盖：
  1. WRT-CORE.yml 缓存路径纳入 ./wrt/dl（源码包复用，避免每次重新下载）
  2. WRT-CORE.yml job 级 timeout-minutes（防止挂死耗尽 6 小时默认上限）
  3. WRT-CORE.yml Save Build Cache 容错（缓存超限不拖垮整个 job）
  4. prepare-rust.sh 的 rustup target add 加超时与重试（rustup 会静默挂死）
"""

import re
import sys

WRT_CORE = '.github/workflows/WRT-CORE.yml'
PREPARE_RUST = '.github/scripts/prepare-rust.sh'

CACHE_BLOCK = (
    '          path: |\n'
    '            ./wrt/.ccache\n'
    '            ./wrt/staging_dir/host*\n'
    '            ./wrt/staging_dir/tool*\n'
)

JOB_TIMEOUTS = {'core': 240, 'cache-rollover': 15}

RUSTUP_ORIG = 'rustup target add --toolchain "$RUST_TOOLCHAIN" "$RUST_TARGET"\n'

RUSTUP_PATCHED = '\n'.join([
    '# rustup 自身没有超时：网络抖动时会静默挂死，直到 job 级上限被杀',
    'for attempt in 1 2 3; do',
    '\tif timeout 300 rustup target add --toolchain "$RUST_TOOLCHAIN" "$RUST_TARGET"; then',
    '\t\tbreak',
    '\tfi',
    '\tif [ "$attempt" -eq 3 ]; then',
    '\t\techo "rustup target add failed after 3 attempts" >&2',
    '\t\texit 1',
    '\tfi',
    '\techo "rustup target add timeout/failed (attempt $attempt), retrying in 10s" >&2',
    '\tsleep 10',
    'done',
    '',
])


def patch_cache_paths(text):
    """缓存路径追加 ./wrt/dl（restore 与 save 两处）。"""
    if './wrt/dl' in text:
        return text
    if CACHE_BLOCK not in text:
        raise SystemExit('[tuning] 未找到缓存路径块，上游 WRT-CORE.yml 结构可能已变更')
    return text.replace(CACHE_BLOCK, CACHE_BLOCK + '            ./wrt/dl\n')


def patch_save_tolerance(text):
    """Save Build Cache 允许失败：缓存体积超限不应导致固件 job 失败。"""
    marker = '      - name: Save Build Cache\n'
    if marker not in text:
        raise SystemExit('[tuning] 未找到 Save Build Cache 步骤')
    start = text.index(marker)
    end = text.find('        uses:', start)
    segment = text[start:end]
    if 'continue-on-error' in segment:
        return text
    out = []
    done = False
    for line in segment.splitlines(keepends=True):
        out.append(line)
        if not done and line.startswith('        if:'):
            out.append('        continue-on-error: true\n')
            done = True
    if not done:
        raise SystemExit('[tuning] Save Build Cache 步骤缺少 if 条件')
    return text[:start] + ''.join(out) + text[end:]


def patch_job_timeouts(text, wanted):
    """为指定 job 注入 timeout-minutes（已存在则跳过）。"""
    lines = text.splitlines()
    if 'jobs:' not in lines:
        raise SystemExit('[tuning] WRT-CORE.yml 缺少 jobs: 段')
    jobs_at = lines.index('jobs:')

    job_starts = []
    for i in range(jobs_at + 1, len(lines)):
        if re.match(r'^  [A-Za-z0-9_-]+:$', lines[i]):
            job_starts.append(i)

    insert_at = []
    for pos, start in enumerate(job_starts):
        name = lines[start].strip()[:-1]
        if name not in wanted:
            continue
        end = job_starts[pos + 1] if pos + 1 < len(job_starts) else len(lines)
        block = lines[start:end]
        if any(re.match(r'^    timeout-minutes:', line) for line in block):
            continue
        for offset, line in enumerate(block):
            if re.match(r'^    runs-on:', line):
                insert_at.append((start + offset + 1, '    timeout-minutes: %d' % wanted[name]))
                break

    for line_no, payload in sorted(insert_at, reverse=True):
        lines.insert(line_no, payload)

    result = '\n'.join(lines)
    if text.endswith('\n'):
        result += '\n'
    return result


def patch_prepare_rust(text):
    """rustup target add 加 timeout 与重试。"""
    if 'timeout 300 rustup target add' in text:
        return text
    if RUSTUP_ORIG not in text:
        raise SystemExit('[tuning] prepare-rust.sh 未找到 rustup target add 命令行')
    return text.replace(RUSTUP_ORIG, RUSTUP_PATCHED)


def main():
    changed = []

    with open(WRT_CORE, encoding='utf-8') as handle:
        core = handle.read()
    tuned = patch_cache_paths(core)
    tuned = patch_save_tolerance(tuned)
    tuned = patch_job_timeouts(tuned, JOB_TIMEOUTS)
    if tuned != core:
        with open(WRT_CORE, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(tuned)
        changed.append(WRT_CORE)

    with open(PREPARE_RUST, encoding='utf-8') as handle:
        rust = handle.read()
    tuned_rust = patch_prepare_rust(rust)
    if tuned_rust != rust:
        with open(PREPARE_RUST, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(tuned_rust)
        changed.append(PREPARE_RUST)

    print('[tuning] updated: %s' % (', '.join(changed) if changed else 'nothing (already tuned)'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
