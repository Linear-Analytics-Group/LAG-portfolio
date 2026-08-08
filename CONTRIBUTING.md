# Engineering Standards & Collaboration

Linear Analytics Group (LAG) maintains strict, production-grade engineering standards across all integration services, shared libraries, and open-source repositories.

### Core Delivery Standards
* **Conventional Commits & Semantic Versioning:** Commits follow `<type>(<scope>): <summary>` (`feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `ci`, `build`, `chore`) to guarantee clear Git history, automated changelogs, and full auditability.
* **Automated Quality Gates:** All pull requests must pass strict static type checking (`mypy --strict`), docstyle compliance (`pydocstyle`), and 100% test coverage — enforced in CI via `--cov-fail-under=100`, not merely reported — before merging into trunk.
* **Branch Protection & Review:** Direct pushes to production branches are disabled. Code changes require formal peer review and passing CI workflows.

---
*For detailed repository management, branching policies, and quality assurance workflows, see [docs/GOVERNANCE.md](docs/GOVERNANCE.md).*
