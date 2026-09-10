# SPDX-License-Identifier: MIT
"""Build the Neo disk handoff from the pinned U-Boot source fixture."""
import argparse
from pathlib import Path
import subprocess


def build(uboot, linux, output):
    if output.exists():
        raise ValueError('DTB destination already exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    preprocessed = output.with_suffix('.pre.dts')
    flags = ('NEO_SMP', 'NEO_CPUFREQ', 'NEO_CPUFREQ_E_MAX=6', 'NEO_CPUFREQ_P_MAX=17',
             'NEO_CPU_THERMAL', 'NEO_PMP_V2', 'NEO_PMP_THERMAL', 'NEO_TEMPERATURES',
             'NEO_TOUCHPAD', 'NEO_SMC', 'NEO_USB2', 'NEO_USB2_BOTH', 'NEO_PCIE', 'NEO_WIFI_ROM',
             'NEO_NVME', 'NEO_WIFI_STATIC_BYPASS')
    subprocess.run(['aarch64-linux-gnu-gcc', '-E', '-nostdinc', '-undef', '-D__DTS__',
                    *('-D' + flag for flag in flags), '-x', 'assembler-with-cpp',
                    '-I', str(uboot), '-I', str(linux / 'include'),
                    str(uboot / 'doc/board/apple/j700-first-light/boot.dts'),
                    '-o', str(preprocessed)], check=True)
    subprocess.run(['dtc', '-I', 'dts', '-O', 'dtb', '-o', str(output), str(preprocessed)], check=True)
    for property_name in ('asahi,j700-pcie-id-test', 'linux-enablement-mac,disk-boot'):
        subprocess.run(['fdtput', str(output), '/chosen', property_name], check=True)
    compatible = subprocess.check_output(['fdtget', str(output), '/', 'compatible'], text=True).split()
    for marker in ('asahi,display-only', 'asahi,j700-static-bypass-test'):
        subprocess.run(['fdtget', str(output), '/chosen', marker], check=True)
    for name, expected in (('static-dart-bypass-test', '50000'), ('owned-streams', '2')):
        actual = subprocess.check_output(
            ['fdtget', '-t', 'x', str(output), '/soc/iommu@390000000',
             'linux-enablement-mac,' + name], text=True).strip()
        if actual != expected:
            raise ValueError('Neo Wi-Fi DART stream policy changed: ' + name)
    if 'apple,j700' not in compatible:
        raise ValueError('Neo DTB has the wrong model')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('uboot', 'linux', 'output'):
        parser.add_argument(name, type=Path)
    build(**vars(parser.parse_args()))
