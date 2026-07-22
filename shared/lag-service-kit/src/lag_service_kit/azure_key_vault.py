"""Azure Key Vault as a pydantic-settings source, for any LAG service."""

from typing import Any, Dict, Optional, Tuple, Type

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource


class AzureKeyVaultSettingsSource(PydanticBaseSettingsSource):
    """Resolves declared fields from Azure Key Vault, any other fields not at all.

    A ``pydantic_settings.PydanticBaseSettingsSource`` implementation —
    the same extension point ``BaseSettings`` already uses internally
    for environment variables and ``.env`` files — so a concrete
    settings class using this needs no code of its own beyond
    declaring which fields are vault-backed (see
    :attr:`~lag_service_kit.settings.BaseServiceSettings.vault_secret_fields`).
    Destination- and service-agnostic: this class has no knowledge of
    Dataverse, inventory, or any other domain concept, only of pydantic
    fields and Key Vault secrets.

    Notes
    -----
    Only fields named in the settings class's ``vault_secret_fields``
    are ever looked up — every other field returns immediately with no
    network call, so composing this source costs nothing for the
    (typical) case where only one or two fields are true secrets.
    Authenticates via ``azure.identity.DefaultAzureCredential``, which
    tries a chain of credential sources (environment variables, a
    Managed Identity, an ``az login`` session, and others) in order —
    the same code here works unchanged whether it runs on a developer's
    machine or inside Azure with a Managed Identity assigned.
    """

    def __init__(
        self,
        settings_cls: Type[BaseSettings],
        vault_url: str,
        secret_client: Optional[SecretClient] = None,
    ) -> None:
        """Bind this source to a Key Vault, or an injected fake for testing.

        Parameters
        ----------
        settings_cls : Type[BaseSettings]
            The settings class this source will be asked to resolve
            fields for.
        vault_url : str
            The target Key Vault's URL (e.g.,
            ``"https://my-vault.vault.azure.net/"``).
        secret_client : SecretClient, optional
            An existing client to use instead of constructing a real
            one — the seam a test replaces with a fake, so no test
            ever needs a real Azure credential or network call.
            Defaults to a real ``SecretClient`` authenticated via
            ``DefaultAzureCredential``.

        Returns
        -------
        None
        """
        super().__init__(settings_cls)
        self._client = secret_client or SecretClient(
            vault_url=vault_url, credential=DefaultAzureCredential()
        )

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> Tuple[Any, str, bool]:
        """Fetch one field's value from Key Vault, if it is vault-backed.

        Parameters
        ----------
        field : FieldInfo
            The pydantic field metadata for ``field_name``. Unused —
            present only to satisfy the base class's signature.
        field_name : str
            The settings class's attribute name (e.g.,
            ``"azure_client_secret"``).

        Returns
        -------
        Tuple[Any, str, bool]
            ``(value, field_name, False)``. ``value`` is ``None``
            immediately, with no Key Vault call at all, for any field
            not listed in the settings class's ``vault_secret_fields``.

        Raises
        ------
        azure.core.exceptions.ResourceNotFoundError
            If a *declared* vault-backed field has no matching secret
            in the vault — deliberately not caught here. A field the
            settings class explicitly says should come from Key Vault,
            but doesn't exist there, is a real setup mistake that
            should surface clearly, not fall through silently to a
            possibly-stale `.env` value.
        azure.core.exceptions.ClientAuthenticationError
            If ``DefaultAzureCredential`` cannot find any working
            credential in its chain. Also deliberately not caught.
        """
        vault_fields = getattr(self.settings_cls, "vault_secret_fields", ())
        if field_name not in vault_fields:
            return None, field_name, False

        secret_name = field_name.replace("_", "-")
        secret = self._client.get_secret(secret_name)
        return secret.value, field_name, False

    def prepare_field_value(
        self,
        field_name: str,
        field: FieldInfo,
        value: Any,
        value_is_complex: bool,
    ) -> Any:
        """Pass a fetched secret value through unchanged.

        Parameters
        ----------
        field_name : str
            The settings class's attribute name.
        field : FieldInfo
            The pydantic field metadata for ``field_name``. Unused.
        value : Any
            The raw value :meth:`get_field_value` returned.
        value_is_complex : bool
            Unused — every value this source produces is a plain
            string, never a value requiring JSON parsing.

        Returns
        -------
        Any
            ``value``, unchanged.
        """
        return value

    def __call__(self) -> Dict[str, Any]:
        """Resolve every vault-backed field for this settings class.

        Returns
        -------
        Dict[str, Any]
            One entry per field actually found in Key Vault. A field
            not listed in ``vault_secret_fields`` is simply absent from
            the result, letting the next source in the chain (e.g.
            ``.env``) supply it instead.
        """
        resolved: Dict[str, Any] = {}
        for field_name, field in self.settings_cls.model_fields.items():
            field_value, field_key, value_is_complex = self.get_field_value(
                field, field_name
            )
            if field_value is not None:
                resolved[field_key] = self.prepare_field_value(
                    field_name, field, field_value, value_is_complex
                )
        return resolved
