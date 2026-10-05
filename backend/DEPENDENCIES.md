# Python dependency locks

`requirements.in` is the reviewed production input. `requirements.txt` is its
generated, version-pinned, SHA-256-checked resolution. It contains conditional
pins where Python 3.11 and 3.12 need different versions (notably NumPy/SciPy).
The production image and both CI Python versions install this same lock.

Install from the repository root:

```sh
python -m pip install pip==26.1.2
python -m pip install --require-hashes --only-binary=:all: -r backend/requirements.txt
# Test environments only:
python -m pip install --require-hashes --only-binary=:all: -r backend/requirements-test.txt
python -m pip check
```

The Linux build requires wheels, so it never resolves unpinned source-build
dependencies. Some packages no longer publish macOS Intel wheels; development
on that platform can require a local compiler, or use the Linux container. An
sdist hash verifies the source archive, not the separately resolved build tools.

Regenerate with **uv 0.9.5**, from the repository root:

```sh
uv pip compile backend/requirements.in --universal --python-version 3.11 --generate-hashes --output-file backend/requirements.txt
uv pip compile backend/requirements-test.in --universal --python-version 3.11 --generate-hashes --output-file backend/requirements-test.txt
```

uv keeps existing output pins unless an upgrade is requested. For an intentional
upgrade, add `--upgrade-package PACKAGE` to the production command, inspect the
transitive diff, regenerate the test lock, and run fresh installs, `pip check`,
the offline backend suite, and a dependency audit on Python 3.11 and 3.12.
The test input constrains shared dependencies to the production lock; pytest is
not shipped in the production image.

Do not regenerate from `pip freeze` of a developer environment. Keep Stagehand
4.1.0 and langchain-anthropic 1.4.6 pinned until their browser/model transport
contracts have separate compatibility coverage. Legacy browser-use and offline
optimization remain in their own optional requirements files and environments.

This locks Python package versions and accepted artifact hashes. It does not pin
Debian packages, the Docker base-image digest, or browser binary downloads.

Sources: [uv compile and synchronization](https://docs.astral.sh/uv/pip/compile/),
[universal resolution](https://docs.astral.sh/uv/pip/compile/#universal-resolution),
[pip secure installations](https://pip.pypa.io/en/stable/topics/secure-installs/).
