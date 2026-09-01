# Linux Compatibility Evidence Matrix

VoidSmith's Linux portable archive is built and smoke-tested natively in the
release workflow. A successful CI artifact is necessary evidence, but it is
not a claim that every Linux distribution, desktop session, graphics stack, or
Starsector installation has been qualified.

## Evidence record

Record results locally (outside the distributable repository when they name a
real installation, mod, or user). Do not add copied game/mod data, screenshots,
or entity lists here.

| Platform | Package version | Desktop / display | Result | Evidence required | Status |
| --- | --- | --- | --- | --- | --- |
| GitHub-hosted Ubuntu x64 | tag workflow version | offscreen smoke test | archive starts with `--smoke-test` | successful tag workflow and artifact verification | Verified — tag workflow succeeded (for example `v0.1.0RC3`) |
| Ubuntu LTS x64 | user-local | user-local | launch, scan, generate, export | local release-verifier output plus observed smoke result | Unverified |
| Linux Mint x64 | user-local | user-local | launch, scan, generate, export | local release-verifier output plus observed smoke result | Unverified |
| Fedora Workstation x64 | user-local | user-local | launch, scan, generate, export | local release-verifier output plus observed smoke result | Unverified |

## Local verification procedure

1. Verify the downloaded archive without extracting or running it:

   `python tools/verify_portable_release.py VoidSmith-<version>-linux-x64.tar.gz --checksum VoidSmith-<version>-linux-x64.tar.gz.sha256`

2. Extract it to a disposable user-owned directory and run `./VoidSmith
   --smoke-test` with the desktop environment's normal display variables.
3. In the GUI, select a locally installed Starsector directory, perform a
   read-only scan, and create one compatibility-mod export below a configured
   local output directory.
4. Record the archive hash, OS release, desktop/display details, outcome, and
   any error text in a user-local evidence file. Never copy installation or
   mod contents into a public report.

The matrix deliberately does not infer package-manager compatibility,
Wayland/X11 equivalence, GPU-driver behavior, or broad distro support from one
result. A failure is evidence for that stated environment, not a claim about
all Linux systems.
