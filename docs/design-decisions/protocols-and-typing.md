← [Back to README](../../README.md) · [All docs](../README.md)

# Design Decisions: Protocols & Structural Typing

Why this codebase consistently reaches for `typing.Protocol` instead of
inheritance — for transport clients, source composition, and even unit
test doubles — and how runtime-checkable protocols let a single class
detect an optional capability without violating Liskov Substitution.

## Table of Contents

- [`from_settings()` and Structural Typing](#from_settings-and-structural-typing)
- [Protocols Over Inheritance, Even for Test Doubles](#protocols-over-inheritance-even-for-test-doubles)
- [Runtime Checkable Protocols](#runtime-checkable-protocols)

## `from_settings()` and Structural Typing

`lag-data-utils` needs four string attributes to construct a
`DataverseClient`. Rather than importing a concrete settings class (which
would chain the transport layer to Pydantic) or duplicating a builder
function in every service, `DataverseClient` exposes:

```python
@classmethod
def from_settings(cls, settings: DataverseConnectionSettings) -> "DataverseClient":
    ...
```

where `DataverseConnectionSettings` is a `@runtime_checkable
typing.Protocol` — not a Pydantic base class. Any object with the right
shape satisfies it: a `lag_service_kit` settings instance passes
`isinstance(obj, Proto)` against the `lag_data_utils` protocol despite
the two packages never importing from each other.

## Protocols Over Inheritance, Even for Test Doubles

A recurring choice throughout this codebase, made explicit here rather
than left to be inferred file by file: whenever a piece of code needs
to accept "something that behaves like X," it is typed against a
`typing.Protocol` describing only the behavior actually used, never
against a concrete class — including when "something that behaves
like X" is a unit test's fake.

**Where this already applied before Key Vault existed:**
`DataverseClient.from_settings()` takes a `DataverseConnectionSettings`
Protocol, not a concrete Pydantic settings class (see above);
`lag_service_kit.sources.base.RecordSource`
and `ChunkedRecordSource` let any object with the right method(s) act
as a runner's source, with zero base class to inherit from (see
"Runtime Checkable Protocols" below).

**Where this showed up again, and why it's the SOLID-correct choice
even under pressure not to be:**
`lag_service_kit.azure_key_vault.AzureKeyVaultSettingsSource` needs a
Key Vault client to fetch secrets. The obvious signature types that
parameter as the real `azure.keyvault.secrets.SecretClient` — but a
unit test then has to pass in a fake, and mypy `--strict` correctly
rejects a fake that doesn't nominally inherit from `SecretClient` as
an incompatible argument type.

Two tempting fixes were rejected:

* **Subclassing the real `SecretClient`** to produce a compatible
  fake. `SecretClient` is a sealed, third-party Azure SDK class whose
  constructor performs real credential/transport setup — inheriting
  from it just to satisfy a type checker couples the test double to
  Azure SDK internals it has no business depending on, and violates
  the Liskov Substitution Principle in spirit even if mypy would
  technically allow it (a fake is not actually substitutable for
  everything a real `SecretClient` does).
* **`# type: ignore[arg-type]` at every call site.** This suppresses
  the specific error mypy raised without addressing why it was raised
  — the parameter's declared type still says "must be this concrete
  Azure class," which remains true (and wrong) everywhere else that
  type gets read or reasoned about, not just at the suppressed lines.

**The fix:** two minimal `typing.Protocol` definitions, local to
`azure_key_vault.py` —

```python
class _SecretValue(Protocol):
    @property
    def value(self) -> Optional[str]: ...

class _SecretClientLike(Protocol):
    def get_secret(self, name: str) -> _SecretValue: ...
```

— and `AzureKeyVaultSettingsSource.__init__`'s `secret_client`
parameter is typed against `_SecretClientLike`, not `SecretClient`.
The real `SecretClient` satisfies this automatically (it has a
matching `get_secret()`); a test's fake satisfies it too, with no
inheritance relationship between the two at all. Neither class knows
the Protocol exists.

Two structural-typing pitfalls apply to any Protocol modeled on a
real third-party type, worth stating explicitly:

* **A Protocol member's type must match the real type's optionality
  exactly.** `_SecretValue.value` is typed `Optional[str]`, matching
  the real `KeyVaultSecret.value` exactly (a secret version can exist
  without a value — e.g. disabled or soft-deleted). A Protocol
  narrower than the real type it's supposed to describe always
  rejects the real type as a structural mismatch; the Protocol must
  describe the type honestly, not the type this code happens to
  expect on the happy path.
* **A read-only property on the real type needs a read-only property
  on the Protocol, not a plain attribute.** `_SecretValue.value` is
  declared as a read-only `@property` because the real
  `KeyVaultSecret.value` is one too; a Protocol plain attribute means
  "gettable and settable," so it would reject the real read-only
  property as a mismatch even with the type itself correct. A settable
  fake attribute still satisfies a read-only Protocol requirement
  (read-write is a superset of read-only), so this constraint only
  binds in one direction.

**Why this is the durable pattern, not a one-off:** structural typing
here is a direct expression of the Dependency Inversion Principle —
this code depends on an abstraction it owns (`_SecretClientLike`), not
on a concrete detail owned by a third party (`SecretClient`) — and of
the Interface Segregation Principle, since the Protocol exposes
exactly the one method actually called, nothing a full `SecretClient`
also happens to expose. The same reasoning applies to any future
constructor parameter accepting a third-party or sealed class: define
the narrow shape actually used, type against that, and let both the
real class and any test double satisfy it independently.

## Runtime Checkable Protocols

We use a `@runtime_checkable` Protocol (`ChunkedRecordSource`, in
`lag_service_kit.sources.base`) to dynamically detect whether an
incoming record source supports chunked streaming.

* **Interface Segregation & LSP:** Not all source formats can genuinely stream. 
Forcing a dummy streaming method onto every reader violates the Liskov 
Substitution Principle and the Interface Segregation Principle. A separate 
Protocol segregates this optional capability cleanly- abstaining from forcing
clients into implementing methods they cannot support.
* **Type-Safe Narrowing:** It allows Mypy to narrow types inside conditional 
blocks. This eliminates the need for unsafe `ignore` workarounds that may hide
true defects.
* **CPU vs. I/O Bottlenecks:** While structural `isinstance` checks carry a 
minor runtime CPU overhead, this check occurs exactly once at the start of the 
sync run—not inside the inner loop processing thousands of records. In a 
network-heavy, I/O-bound pipeline, a microsecond-level CPU check is 
mathematically irrelevant compared to milliseconds of network latency, adding
little-to-no cost to implementing this clean and predictable design.

---

← [Back to README](../../README.md) · [All docs](../README.md)
