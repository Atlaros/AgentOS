from __future__ import annotations

import asyncio
from decimal import ROUND_DOWN, Decimal

from stellar_sdk import Asset, Keypair, Network, Server, TransactionBuilder
from stellar_sdk.exceptions import NotFoundError, SdkError
from stellar_sdk.strkey import StrKey

from agentos.domain.ports import Balance, SubmitResult
from agentos.settings import Settings


def is_stellar_address(value: str) -> bool:
    return StrKey.is_valid_ed25519_public_key(value)


class StellarTestnetAdapter:
    """Stellar Testnet adapter. Lab signer secret comes from env only — never DB."""

    provider = "stellar"
    network = "testnet"

    def __init__(
        self,
        *,
        horizon_url: str,
        network_passphrase: str,
        secret_key: str | None,
    ) -> None:
        if "public" in network_passphrase.lower() and "test" not in network_passphrase.lower():
            raise ValueError("mainnet passphrase denied in MVP")
        self._horizon_url = horizon_url
        self._network_passphrase = network_passphrase
        self._secret_key = secret_key
        self._submitted: dict[str, SubmitResult] = {}

    @classmethod
    def from_settings(cls, settings: Settings) -> StellarTestnetAdapter:
        return cls(
            horizon_url=settings.stellar_horizon_url,
            network_passphrase=settings.stellar_network_passphrase,
            secret_key=settings.stellar_secret_key or None,
        )

    def signer_public_key(self) -> str | None:
        if not self._secret_key:
            return None
        return Keypair.from_secret(self._secret_key).public_key

    async def get_balances(self, public_address: str) -> list[Balance]:
        if not StrKey.is_valid_ed25519_public_key(public_address):
            raise ValueError("invalid_stellar_address")
        return await asyncio.to_thread(self._get_balances_sync, public_address)

    def _get_balances_sync(self, public_address: str) -> list[Balance]:
        server = Server(horizon_url=self._horizon_url)
        try:
            try:
                account = server.accounts().account_id(public_address).call()
            except NotFoundError:
                return [Balance(asset_code="XLM", amount=Decimal(0), issuer=None)]

            out: list[Balance] = []
            for bal in account.get("balances", []):
                asset_type = bal.get("asset_type")
                amount = Decimal(str(bal.get("balance", "0")))
                if asset_type == "native":
                    out.append(Balance(asset_code="XLM", amount=amount, issuer=None))
                else:
                    out.append(
                        Balance(
                            asset_code=str(bal.get("asset_code")),
                            amount=amount,
                            issuer=str(bal.get("asset_issuer")),
                        )
                    )
            return out
        finally:
            server.close()

    async def submit_payment(
        self,
        *,
        from_address: str,
        to_address: str,
        asset_code: str,
        amount: Decimal,
        memo: str | None,
        idempotency_key: str,
    ) -> SubmitResult:
        if idempotency_key in self._submitted:
            return self._submitted[idempotency_key]

        if asset_code != "XLM":
            result = SubmitResult(network_tx_id="", status="failed")
            self._submitted[idempotency_key] = result
            return result

        if not self._secret_key:
            result = SubmitResult(network_tx_id="", status="failed")
            self._submitted[idempotency_key] = result
            return result

        if not StrKey.is_valid_ed25519_public_key(from_address):
            result = SubmitResult(network_tx_id="", status="failed")
            self._submitted[idempotency_key] = result
            return result
        if not StrKey.is_valid_ed25519_public_key(to_address):
            result = SubmitResult(network_tx_id="", status="failed")
            self._submitted[idempotency_key] = result
            return result

        signer = Keypair.from_secret(self._secret_key)
        if signer.public_key != from_address:
            # Lab signer can only move funds from its own public address.
            result = SubmitResult(network_tx_id="", status="failed")
            self._submitted[idempotency_key] = result
            return result

        try:
            result = await asyncio.to_thread(
                self._submit_sync,
                signer,
                to_address,
                amount,
                memo,
            )
        except (SdkError, ValueError, RuntimeError):
            result = SubmitResult(network_tx_id="", status="failed")

        self._submitted[idempotency_key] = result
        return result

    @staticmethod
    def _format_amount(amount: Decimal) -> str:
        # Horizon rejects excess scale from Numeric(36,18) values like 1.000000000000000000
        quantized = amount.quantize(Decimal("0.0000001"), rounding=ROUND_DOWN)
        return format(quantized.normalize(), "f")

    def _submit_sync(
        self,
        signer: Keypair,
        to_address: str,
        amount: Decimal,
        memo: str | None,
    ) -> SubmitResult:
        server = Server(horizon_url=self._horizon_url)
        try:
            source_account = server.load_account(signer.public_key)
            base_fee = server.fetch_base_fee()
            builder = (
                TransactionBuilder(
                    source_account=source_account,
                    network_passphrase=self._network_passphrase,
                    base_fee=base_fee,
                )
                .append_payment_op(
                    destination=to_address,
                    asset=Asset.native(),
                    amount=self._format_amount(amount),
                )
                .set_timeout(60)
            )
            if memo:
                builder.add_text_memo(memo[:28])
            tx = builder.build()
            tx.sign(signer)
            response = server.submit_transaction(tx)
            tx_hash = str(response.get("hash") or "")
            successful = bool(response.get("successful", False))
            status = "confirmed" if successful else "submitted"
            return SubmitResult(network_tx_id=tx_hash, status=status)
        finally:
            server.close()


# Re-export Network constant for settings default alignment
TESTNET_PASSPHRASE = Network.TESTNET_NETWORK_PASSPHRASE
