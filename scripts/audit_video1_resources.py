#!/usr/bin/env python3
"""Bounded /proc CPU, memory and available DRM counter capture inside Docker."""
import argparse
import json
import os
from pathlib import Path
import time


def snapshot():
    processes = {}
    for entry in Path('/proc').glob('[0-9]*'):
        try:
            raw = (entry/'stat').read_text()
            name = raw.split('(', 1)[1].rsplit(')', 1)[0]
            fields = raw.rsplit(')', 1)[1].split()
            row = dict(name=name, ticks=int(fields[11])+int(fields[12]),
                       rss_bytes=int(fields[21])*os.sysconf('SC_PAGE_SIZE'))
            if name in ('gzserver', 'gzclient', 'rviz2'):
                engines = {}
                for fd in (entry/'fdinfo').glob('*'):
                    try:
                        info = dict(line.split(':', 1) for line in fd.read_text().splitlines() if ':' in line)
                        client = info.get('drm-client-id')
                        if client:
                            engines[client.strip()] = {k: int(v.strip().split()[0]) for k, v in info.items()
                                                       if k.startswith('drm-engine-')}
                    except (OSError, ValueError):
                        continue
                row['drm_counters'] = engines or 'UNAVAILABLE'
            processes[entry.name] = row
        except (OSError, ValueError, IndexError):
            continue
    cpu = [int(v) for v in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    memory = {line.split(':')[0]: int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()
              if line.startswith(('MemAvailable:', 'MemTotal:', 'SwapTotal:', 'SwapFree:'))}
    return dict(wall=time.time(), monotonic=time.monotonic(), cpu_ticks=cpu,
                memory=memory, processes=processes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--seconds', type=float, default=30)
    args = parser.parse_args()
    previous = snapshot()
    end = time.monotonic()+args.seconds
    with Path(args.output).open('w', buffering=1) as output:
        while time.monotonic() < end:
            time.sleep(min(5, max(0, end-time.monotonic())))
            current = snapshot()
            dt = current['monotonic']-previous['monotonic']
            delta = [a-b for a, b in zip(current['cpu_ticks'], previous['cpu_ticks'])]
            current['host_cpu_busy_percent'] = 100*(1-(delta[3]+delta[4])/sum(delta)) if sum(delta) else None
            for pid, row in current['processes'].items():
                before = previous['processes'].get(pid)
                row['cpu_percent_one_core_100'] = (100*(row['ticks']-before['ticks'])/
                    (dt*os.sysconf('SC_CLK_TCK'))) if before and before['name']==row['name'] else None
            output.write(json.dumps(current)+'\n')
            previous = current


if __name__ == '__main__':
    main()
