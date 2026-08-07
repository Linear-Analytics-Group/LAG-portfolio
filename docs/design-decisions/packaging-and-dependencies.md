← [Back to README](../../README.md) · [All docs](../README.md)

# Design Decisions: Packaging & Dependencies

How the two shared packages resolve against each other inside a
monorepo with no private package index, why dependency pinning
differs between libraries and the application, and what real package
metadata this repo ships beyond a version number.

## Table of Contents

- [Monorepo Dependency Resolution: Install Order vs. a Private Feed](#monorepo-dependency-resolution-install-order-vs-a-private-feed)
- [Dependency Pinning: Loose for Libraries, Locked for the Application](#dependency-pinning-loose-for-libraries-locked-for-the-application)
- [Packaging Governance: Real Metadata, Not Just a Version Number](#packaging-governance-real-metadata-not-just-a-version-number)

## Monorepo Dependency Resolution: Install Order vs. a Private Feed

`lag-service-kit`'s `pyproject.toml` declares `lag-data-utils>=1.0.0`
in exactly the same form as any PyPI dependency (`pydantic>=2.7.0`,
`pandas>=2.2.0`). There is no `pyproject.toml` syntax that marks one
dependency as "resolve this from a local path" and another as
"resolve this from a package index" — pip has no such distinction
built in.

**How this actually resolves today:** purely by install order, not by
anything declared in the metadata. Every documented workflow in this
repo — the local setup steps (see [Setup](../setup.md)), and CI's
explicit `lag-data-utils` wheel build before `lag-service-kit`'s —
installs `lag-data-utils` first, so by the time pip is asked to
satisfy `lag-data-utils>=1.0.0`, it is already present in the
environment and pip never looks anywhere else for it. Reverse that
order, in an environment with no local `lag-data-utils` already
present, and this fails outright — `lag-data-utils` isn't actually
published anywhere pip reaches by default.

**The enterprise-grade fix, and why it's not here:** the robust answer
is a private package index — an internal Azure Artifacts feed, or a
self-hosted PyPI-compatible server — that actually publishes
`lag-data-utils`, so it resolves like any other dependency regardless
of install order. (A monorepo-aware tool with native workspace/path
dependencies, like `uv` or PDM, is the other real fix, at the cost of
a bigger toolchain change.) Standing up either is out of scope here:
one internal package, consumed by exactly one sibling package, in a
repo with two documented install paths — local dev and CI — that both
already get the order right. This note exists to make that a
documented, understood tradeoff rather than a silent gap — the
trigger to revisit it is a second internal consumer, a third install
path, or any of this actually being published externally.

## Dependency Pinning: Loose for Libraries, Locked for the Application

The Python Packaging Authority draws a hard line between *libraries*
and *applications*. `lag-data-utils` and `lag-service-kit` are
libraries — installed alongside whatever else shares that
environment. If they pinned tightly (e.g., `pandas==2.2.0`) and
something else in that environment needed `pandas==2.3.1`, pip's
resolver couldn't satisfy both. For packages, implementing lower
bounds only helps prevent dependency conflicts of this nature.
Conversely, applications (e.g., `services/inventory-sync-engine`)
share nothing in their environments, so there's no resolver-conflict
risk — what actually matters is reproducibility: the same versions
installed today, next month, and in CI. A loose lower bound-only
requirement doesn't provide that — a breaking release of any
dependency could land silently on the next `pip install`, in CI or a
real deployment, with zero code change and zero warning.

**The Solution:** `requirements.in` (loose bounds, human-edited) plus
a fully pinned, hash-verified `requirements.txt`, generated via
[pip-tools](https://github.com/jazzband/pip-tools)'s `pip-compile` —
additive on top of plain `pip`, not a replacement toolchain, matching
this repo's own "Monorepo Dependency Resolution" call above to stay
off `uv`/Poetry for now. Regenerate after changing `requirements.in`
or either shared package's own dependencies:

```bash
python -m build --wheel ../../shared/lag-data-utils --outdir /tmp/lag-wheels
python -m build --wheel ../../shared/lag-service-kit --outdir /tmp/lag-wheels
pip-compile --generate-hashes --no-emit-find-links --no-header \
  --find-links /tmp/lag-wheels \
  --unsafe-package lag-data-utils --unsafe-package lag-service-kit \
  --output-file=requirements.txt requirements.in
```

**Why `lag-data-utils`/`lag-service-kit` appear in `requirements.in`
but never in the generated `requirements.txt`:** the lock needs to
cover the *whole* deployed environment, not just the service's own
direct imports — `lag-service-kit` alone pulls in `pyarrow`,
`azure-identity`, and `azure-keyvault-secrets`, none of which the
service imports directly. Listing the two shared packages in
`requirements.in` (resolved via `--find-links` against freshly built
wheels, since neither is published to a real index) lets `pip-compile`
correctly compute *their* transitive dependencies too. Hash-pinning the
two local packages would be unreliable: CI rebuilds their wheels
fresh every run, and that build isn't guaranteed byte-for-byte
reproducible, so a hash computed today could mismatch a wheel built
tomorrow. `--unsafe-package` excludes them from the pinned output
while still using them as resolution input — and this is safe
specifically because CI's existing install order already installs
both wheels *before* `requirements.txt`, so by the time the lock file
is installed, pip finds them already present and never needs to
resolve or hash-check them itself.

## Packaging Governance: Real Metadata, Not Just a Version Number

**`Requires-Python`:** Without a `requires-python` constraint on the
package itself, `pip install`s into older interpreters would succeed
silently and fail later, deep inside the given module(s), with a
confusing `TypeError` instead of a clear version-mismatch error at
install time. Packages declare `requires-python`, `license`,
`authors`, `classifiers` (including `Typing :: Typed`, matching their
`py.typed` marker), and `[project.urls]` in their respective
`pyproject.toml` files.

**Package Version References:** Package versions are exposed via
`importlib.metadata.version` in each package's `__init__.py`, rather
than a hardcoded string literal — this reads the version pip already
recorded at install time from the same `pyproject.toml` field, so it
can never drift out of sync.

**Licensing:** this repository is proprietary, source-available for
evaluation only — see the root `LICENSE` file. Each packages'
`pyproject.toml` embed this license to support build requirements.

---

← [Back to README](../../README.md) · [All docs](../README.md)
