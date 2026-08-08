← [Back to README](../README.md)

# Software Delivery & Repository Governance

This document outlines the operational policies governing source control, quality assurance, release management, and security across Linear Analytics Group repositories.

## 1. Branching & Deployment Strategy
* **Trunk-Based Development:** The `trunk` (or `main`) branch represents release-ready software at all times.
* **Short-Lived Feature Branches:** All active work takes place on isolated feature branches formatted as `<type>/<short-description>` (e.g., `feat/chunked-reader`, `fix/token-lock`).
* **Pull Request Enforcement:** Direct pushes to `trunk` are prohibited by policy, enforced via GitHub branch protection rules configured on this repository (outside this repository's own tracked files). Merges require passing status checks (CI) and code review approval.

## 2. Commit & History Standards
* **Conventional Commits:** All commit messages must follow the standard specification:
  ```text
  <type>(<scope>): <short summary in present tense>
  ```
  *Allowed types:* `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `ci`, `build`, `chore`.
* **Imperative Mood:** Summaries must begin with a present-tense action verb (e.g., `add retry backoff`, not `added retry backoff`).
* **Linear History:** Repositories enforce squashed or rebased merges to preserve clean, bisectable history trails without unnecessary merge commits.

## 3. Quality Assurance & Static Analysis
* **Strict Type Safety:** Python modules must pass `mypy --strict` with zero type warnings or un-typed function definitions.
* **Documentation Compliance:** Codebase docstrings follow `pydocstyle` (NumPy convention) to guarantee clear interface descriptions.
* **Centralized Testing:** Changes must include unit or integration tests mirroring the architectural layer under modification (`shared/lag-data-utils`, `shared/lag-service-kit`, or `services/*`).

## 4. Dependency & Package Governance
* **Library vs. Application Decoupling:** Shared libraries maintain loose lower bounds (`>=`) to avoid resolver conflicts, while services utilize hash-pinned lockfiles (`requirements.txt`) generated via `pip-compile`.
* **Monorepo Package Boundaries:** Internal packages (`lag-data-utils`, `lag-service-kit`) maintain strict dependency layering and ship `py.typed` markers (PEP 561).

## 5. Security & Vulnerability Reporting
If you discover a potential security issue, credentials exposure, or dependency vulnerability, please report it directly to `contact@linearanalyticsgroup.com` rather than opening a public GitHub issue.

---

← [Back to README](../README.md)
