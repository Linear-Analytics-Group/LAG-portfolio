# Engineering Standards & Collaboration

Linear Analytics Group (LAG) maintains strict, production-grade engineering standards across all integration services, shared libraries, and open-source repositories.

### Core Delivery Standards
* **Conventional Commits & Semantic Versioning:** Commits follow structured syntactic scoping (`feat`, `fix`, `refactor`, `docs`) to guarantee clear Git history, automated changelogs, and full auditability.
* **Automated Quality Gates:** All pull requests must pass strict static type checking (`mypy --strict`), docstyle compliance (`pydocstyle`), and full test coverage before merging into trunk.
* **Branch Protection & Review:** Direct pushes to production branches are disabled. Code changes require formal peer review and passing CI workflows.

---
*For detailed repository management, branching policies, and quality assurance workflows, see [docs/GOVERNANCE.md](docs/GOVERNANCE.md).*
