# Private J713 filesystem variant

This recipe derives a fresh-install image from the admitted Omarchy full-OS
release in `extract_base.py`. It retains the standard first-boot provisioning
and vendor-firmware services while replacing stock Asahi boot writers with the
accepted cleanroom J713 kernel and complete matching module set.

All image operations run in a disposable native Linux builder. The only loop
attachments are regular input/output image files; no physical disk is accepted.
Use the pinned base image, package closure, source graph and build receipts from
the candidate. Do not replace them with an unrecorded current branch or image.

The sequence is `build_kernel.py`, `extract_base.py`, `build_kernel_package.sh`, `build_u_boot.py`, `prepare_root.sh`,
`verify_root.sh`, then `build_boot.py`. Each output directory must be new. Pass
`HOST_UID`/`HOST_GID` to the container so artifacts are returned to their owner.
`prepare_root.sh` removes vendor firmware packages and caches. Its final
`repack_images.sh` step formats new zero-initialized filesystems, copies only
the cleaned live files and creates the new factory snapshot. Deleting files
from the original images alone would retain firmware in unallocated blocks.
`verify_no_firmware.py` audits all subvolumes and boot files;
`verify_initramfs.py` inspects every early, compressed and trailing CPIO archive
for firmware absence and requires the matching thermal module.
`verification.json` binds the exact
root, boot and initramfs bytes; compare it with the sealed payload receipt.

The kernel source artifacts must include Image, config, the J713 DTB and the
complete modules_install output, without a build-directory symlink. The input
manifest records every kernel/package/boot digest and rejects vendor firmware
inputs. Regulatory database files are retained; they are not vendor firmware.
The accepted source
revisions are recorded by the installer model profile and candidate receipts.

`build_boot.py` embeds Image, initramfs and a root-UUID GRUB configuration using
the accepted GRUB build, then invokes the accepted enablement checkout's
`build_chainload.sh --disk-boot`. The emitted ESP contains this boot.bin plus the
matching standalone EFI image. Do not carry stock boot.bin backups forward.
`build_u_boot.py` pins `bootloader/u-boot.config`: the memory-only preloaded EFI
path is disabled, and `load nvme ${fw_dev_part}` records the real ESP device path
before `bootefi`. The selected partition comes from m1n1's generated ESP UUID.
GRUB can therefore load `/vendorfw/firmware.cpio` from its own `$cmdpath` device,
after its embedded firmware-free initramfs. The kernel's
`firmware_class.path=/vendorfw` makes those per-install files available early.
The macOS installer obtains and validates them directly from Apple before
partitioning; no firmware CPIO is included in these published artifacts.

This candidate boots to graphical.target using Mesa llvmpipe and the patched
Aquamarine software EGL fallback. It uses the model-level root image
UUID `4f4d5801-524f-4f54-8713-000000000001`, not an old installation's UUID.
The accepted kernel has no Asahi GPU driver. Factory rollback contains the same
custom kernel; future kernel changes need a newly verified complete boot bundle.
Physical installation and paired Recovery boot are separate owner smoke tests.

## Kernel compilation

`build_kernel.py` builds the private fork locally; it does not download a stock
kernel package or compile anything on the destination Mac. Prepare a workspace
with a clean `source/` Git checkout at `kernel/build-lock.json`'s revision and a
Rust toolchain matching that lock (including rust-src). Clang/LLD and bindgen
versions are checked as well. No network access is needed during compilation.

```sh
python3 builder/cleanroom/build_kernel.py /path/to/workspace \
  --rust-toolchain /path/to/rust-1.98.0
```

The build uses 10 workers by default (`OMARCHY_BUILD_JOBS` overrides it), writes
objects to `build/`, logs to `build.log`, and stages the complete kernel payload
under `artifacts/<kernel-release>/`. A workspace lock prevents concurrent builds.
Existing artifact releases are never overwritten. Failed compilation can resume
from the same object directory; preserve any partial artifact directory before
retrying a failed staging step.

`kernel/j713-base.config` is the hash-pinned hardware configuration from the
kernel that booted J713. `kernel/omarchy.config` layers on the distribution's
iwd crypto interfaces, UFW IPv4/IPv6 nftables support, Docker NAT/bridge support,
and console log levels. Kconfig resolves dependencies before `verify_kernel.py`
checks the resulting config, including the disabled internal-speaker driver.
This does not add an accelerated GPU or claim support for internal speakers.

Image, J713 DTB, config, System.map, every configured module and depmod indexes
are staged together. Verification checks module completeness and vermagic,
ARM64 Image format, payload permissions and all receipt hashes. The receipt
records source revision, toolchain versions and configuration/build identities.
`build_kernel_package.sh` validates this payload before producing the package;
`verify_inputs.py` repeats validation before an image is modified.

When changing the source or requirements, assign a new kernel release in the
fragment and lock, update the PKGBUILD release and package filename pins, and
build a fresh artifact set. The final initramfs and embedded EFI/boot.bin must
also be rebuilt: updating a root filesystem's kernel package alone does not
replace the kernel embedded in this boot chain.

The image removes the debug `earlycon`/`loglevel=7` arguments while
retaining kernel diagnostics in dmesg and the journal. The standard provisioning service hands off to SDDM and the Omarchy uwsm
session after successful setup. `speakersafetyd` is masked for this
unsupported-speaker image; no synthetic safety profile or hardware output is
enabled. These image settings are applied before the factory snapshot.

Build/config checks do not prove hardware Wi-Fi association or first-boot UI
behavior. The existing installation has passed a software-rendered Hyprland/Omarchy
session smoke test with this graphics patch, including a captured desktop and
owner-confirmed touchpad operation. The new kernel and newly assembled payload
still require their own boot validation.

## Software graphics

`graphics/aquamarine-software-egl.patch` applies to Aquamarine v0.14.0,
revision `a79fb21b2e2a82dd061a6d071802bcf38bd5c383`. When the DRM renderer
cannot match an EGLDevice, it retries the existing GBM allocator. This supports
Mesa's software renderer on simpledrm without a fabricated GPU identifier.
Both renderer initialization and display-format discovery use the fallback.

The local `~/omarchy/graphics-build/` workspace contains the pinned source,
ARM64 sysroot extracted read-only from the admitted base image, cross toolchain
file, build script, logs and screenshots. Clang/LLD run natively on the Linux
build machine; qemu-aarch64 runs only the ARM64 protocol generator and unit test.
`build_graphics_package.sh` packages the staged library and headers as Aquamarine
0.14.0-3. The package retains the source license and a build receipt. This package
and the new kernel package must both be included in `j713-boot-inputs.json` before
image construction. See `graphics/README.md` for the build and validation recipe.
