"""OS keyring access for the live-translation API key."""

from __future__ import annotations

from typing import Protocol

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

KEYRING_SERVICE = "Parallel Book Viewer"
KEYRING_ACCOUNT = "translation-api-key"


class CredentialStoreError(Exception):
    """Safe wrapper around an unavailable or failing credential backend."""


class CredentialStore(Protocol):
    def read_api_key(self) -> str | None: ...

    def write_api_key(self, value: str) -> None: ...

    def delete_api_key(self) -> None: ...


class KeyringCredentialStore:
    """Store the single translation credential in the operating-system keyring."""

    def read_api_key(self) -> str | None:
        try:
            return keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
        except KeyringError as error:
            raise CredentialStoreError(
                "The operating-system credential store is unavailable."
            ) from error

    def write_api_key(self, value: str) -> None:
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, value)
        except KeyringError as error:
            raise CredentialStoreError(
                "The API key could not be saved in the operating-system credential store."
            ) from error

    def delete_api_key(self) -> None:
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
        except PasswordDeleteError:
            return
        except KeyringError as error:
            raise CredentialStoreError(
                "The API key could not be removed from the operating-system credential store."
            ) from error
