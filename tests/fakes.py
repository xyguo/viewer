"""Shared in-memory collaborators for tests."""

from __future__ import annotations

from dataclasses import dataclass

from book_viewer.credentials import CredentialStoreError


@dataclass(slots=True)
class MemoryCredentialStore:
    api_key: str | None = None
    unavailable: bool = False
    fail_writes: bool = False

    def read_api_key(self) -> str | None:
        if self.unavailable:
            raise CredentialStoreError("unavailable")
        return self.api_key

    def write_api_key(self, value: str) -> None:
        if self.fail_writes:
            raise CredentialStoreError("Keyring write failed.")
        self.api_key = value

    def delete_api_key(self) -> None:
        if self.fail_writes:
            raise CredentialStoreError("Keyring delete failed.")
        self.api_key = None
