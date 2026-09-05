# J713 software-rendered desktop

The private kernel already has simpledrm, GEM shared-memory buffers, sync files,
and the Apple input drivers. Mesa 26.2.1's llvmpipe supplies CPU OpenGL 4.6 and
OpenGL ES 3.2. No additional GPU kernel driver is needed for this path.

Aquamarine v0.14.0's display renderer initially requires an EGLDevice matching a
DRM node. Mesa can instead expose a working GBM software display. The included
patch retries Aquamarine's existing GBM renderer with the existing allocator
when matching an EGLDevice fails. It covers format discovery and renderer
initialization, retains allocator lifetime, and contains no machine identifiers.

## Build

Prepare a workspace with `aquamarine/` at revision
`a79fb21b2e2a82dd061a6d071802bcf38bd5c383` and apply
`aquamarine-software-egl.patch`. Extract `sysroot/usr/` read-only from the admitted
ARM64 base root image, preserving its headers and matching libraries. Include
`lib -> usr/lib` and `lib64 -> usr/lib` in the sysroot. Record the base image's
digest; never substitute the host's x86 libraries or a moving package snapshot.

```sh
./builder/cleanroom/graphics/build.sh /path/to/graphics-workspace
DESTDIR=/path/to/new-stage cmake --install /path/to/graphics-workspace/build-native
```

The build checks the source revision, exact source patch and native Clang
22.1.8. Its cross toolchain uses the base's GCC 16.1.1 C++ headers and libraries.
The host needs Clang/LLD, CMake, Ninja, pkg-config and qemu-aarch64. QEMU runs the
ARM64 protocol generator, not the C++ compiler. Two workers are used by default
to allow concurrent kernel compilation; `OMARCHY_BUILD_JOBS` overrides this.

Stage the source LICENSE at `usr/share/licenses/aquamarine/LICENSE` and a receipt
at `usr/share/omarchy/graphics/build-receipt.json` with the source revision,
patch/compiler/base identities and library digest. Package in the pinned
disposable native builder with `build_graphics_package.sh STAGE NEW_OUTPUT`.
Pass the real artifact owner's `HOST_UID` and `HOST_GID`. The staged shared
library must retain executable mode for makepkg's versioned SONAME dependency
discovery. Verify package metadata and its library hash against the tested build.

## Validation evidence

The local build's `attachments` test passed under qemu-aarch64. The exact library
bytes in the accepted 0.14.0-3 package were loaded on J713 through a temporary
library search path. A minimal Hyprland session displayed a terminal, followed
by the normal Omarchy uwsm session with its background, bar and notifications.
A full-screen capture was inspected, and the owner confirmed the display and
touchpad work. No touchpad configuration change was needed.

This validates software graphics on the previously installed kernel. It does
not constitute a boot test of the newly built kernel, a rebuilt installer
payload, or the graphical first-boot/SDDM transition. Future images install this
package, select graphical.target, and set LIBGL_ALWAYS_SOFTWARE=1 for SDDM and
the systemd user environment. The installed Omarchy session file already lives
under `/usr/local/share/wayland-sessions/`; do not create a duplicate session.
