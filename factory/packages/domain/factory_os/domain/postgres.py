from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Iterator
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg.types.json import Json

from factory_os.domain.models import (
    AccountingPeriod,
    CashAttachment,
    CashMovement,
    CashSaleTicket,
    CashSession,
    ChartAccount,
    Conversation,
    Customer,
    CustomerNote,
    HumanAuditEvent,
    InvoiceDocument,
    JournalEntry,
    JournalLine,
    LedgerEntry,
    ConversationMedia,
    EntityMedia,
    MediaAsset,
    PanelUser,
    ProductMedia,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    Reminder,
    ReportDownload,
    Delivery,
    Order,
    OrderItem,
    Payment,
    PaymentStatus,
    Supplier,
    WorkingState,
)
from factory_os.domain.embeddings import (
    embed_blob,
    embed_dims,
    embed_documents,
    parse_vector,
    reindex_requested,
    vector_literal,
)
from factory_os.domain.seed import catalog_search_blob, tokenize
from factory_os.domain.store import VariantRecord

MIGRATION_FILES = (
    "001_commerce.sql",
    "002_rls.sql",
    "003_working_state.sql",
    "004_cash.sql",
    "005_agent_trace.sql",
    "006_catalog_pgvector.sql",
    "007_catalog_cohere_embeddings.sql",
    "008_shop_knowledge.sql",
    "009_conversation_playbook.sql",
    "010_conversation_memory.sql",
    "011_payment_webhooks.sql",
    "012_whatsapp_inbound.sql",
    "013_learning_and_order_tracking.sql",
    "014_order_created_at.sql",
    "015_payment_before_order.sql",
    "016_order_discount.sql",
    "017_agent_catalog_view_security_invoker.sql",
    "018_customer_notes.sql",
    "019_reminders.sql",
    "020_panel_users.sql",
    "021_ledger_invoices.sql",
    "022_cash_sessions.sql",
    "023_cash_movement_meta.sql",
    "024_cash_sale_tickets.sql",
    "025_panel_supervisor_pin.sql",
    "026_cash_sale_qr.sql",
    "027_cash_attachments.sql",
    "028_ledger_entry_status.sql",
    "029_journal_double_entry.sql",
    "030_accounting_periods.sql",
    "031_journal_fase3.sql",
    "032_suppliers_directory.sql",
    "033_purchase_receipt_supplier.sql",
    "034_purchase_orders.sql",
    "035_purchase_order_receive.sql",
    "036_analytics_thresholds.sql",
    "037_analytics_owner_digest.sql",
    "038_report_download_log.sql",
    "039_counter_orders.sql",
    "040_catalog_category_sort.sql",
    "041_future_orders.sql",
    "042_catalog_modifiers.sql",
    "043_cash_ticket_discount.sql",
    "044_media_assets.sql",
    "045_conversation_media.sql",
    "046_entity_media.sql",
    "047_conversation_media_enrichment.sql",
    "048_whatsapp_inbound_tenant.sql",
    "049_tenant_industry_modules.sql",
    "050_catalog_rules.sql",
    "051_catalog_rule_versions.sql",
    "052_business_whatsapp.sql",
    "053_business_owners.sql",
    "054_business_reserved_replies.sql",
    "055_signup_invites.sql",
    "056_signup_rate_hits.sql",
    "057_owner_sessions.sql",
    "058_model_usage.sql",
    "059_tenant_autonomy.sql",
    "060_published_flow_maps.sql",
    "061_panel_admin_and_job.sql",
    "062_panel_admin_role.sql",
    "063_tenant_employees.sql",
)


def migrations_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "db" / "migrations"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("db/migrations")


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url, row_factory=dict_row)


def assert_rls_runtime_role(url: str) -> None:
    """Reject database roles that can bypass tenant row-level security."""
    conn = connect(url)
    try:
        row = conn.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
    finally:
        conn.close()
    if row is None or row["rolsuper"] or row["rolbypassrls"]:
        raise RuntimeError("database_runtime_role_must_not_bypass_rls")


def ensure_local_rls_runtime_role(admin_url: str, runtime_url: str) -> None:
    """Provision least-privilege local runtime access using credentials from its URL."""
    runtime_info = conninfo_to_dict(runtime_url)
    role_name = str(runtime_info.get("user") or "").strip()
    # Supabase pooler logins are `<role>.<project-ref>`; the role is `<role>`.
    if "pooler.supabase.com" in str(runtime_info.get("host") or ""):
        role_name = role_name.split(".", 1)[0]
    password = str(runtime_info.get("password") or "")
    database_name = str(runtime_info.get("dbname") or "").strip()
    if not role_name or not password or not database_name:
        raise RuntimeError("local_runtime_url_requires_user_password_and_database")

    conn = connect(admin_url)
    try:
        role = conn.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s",
            (role_name,),
        ).fetchone()
        if role is None:
            conn.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS").format(
                    sql.Identifier(role_name), sql.Literal(password)
                )
            )
        elif role["rolsuper"] or role["rolbypassrls"]:
            raise RuntimeError("database_runtime_role_must_not_bypass_rls")
        else:
            # Keep an existing local runtime role aligned with the credentials
            # supplied in DATABASE_RUNTIME_URL (Compose may use a separate host URL).
            # Naming NOSUPERUSER/NOBYPASSRLS here needs superuser on Postgres 16+
            # (managed hosts like Supabase); the check above already enforces both.
            conn.execute(
                sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                    sql.Identifier(role_name), sql.Literal(password)
                )
            )

        admin_role = conn.execute("SELECT current_user AS role_name").fetchone()["role_name"]
        conn.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database_name), sql.Identifier(role_name)
            )
        )
        conn.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role_name))
        )
        conn.execute(
            sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(
                sql.Identifier(role_name)
            )
        )
        conn.execute(
            sql.SQL("GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {}").format(
                sql.Identifier(role_name)
            )
        )
        conn.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
            ).format(sql.Identifier(admin_role), sql.Identifier(role_name))
        )
        conn.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                "GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {}"
            ).format(sql.Identifier(admin_role), sql.Identifier(role_name))
        )
        conn.commit()
    finally:
        conn.close()


def split_sql(sql: str) -> list[str]:
    """Split migration SQL on `;`, ignoring those inside `--` line comments or `$$` bodies."""
    parts: list[str] = []
    buf: list[str] = []
    dollar = False
    line_comment = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if line_comment:
            buf.append(ch)
            if ch == "\n":
                line_comment = False
            i += 1
            continue
        if sql.startswith("$$", i):
            dollar = not dollar
            buf.append("$$")
            i += 2
            continue
        if not dollar and sql.startswith("--", i):
            line_comment = True
            buf.append("--")
            i += 2
            continue
        if not dollar and ch == ";":
            stmt = "".join(buf).strip()
            if stmt and not all(
                line.strip().startswith("--") or not line.strip() for line in stmt.splitlines()
            ):
                parts.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail and not all(line.strip().startswith("--") or not line.strip() for line in tail.splitlines()):
        parts.append(tail)
    return parts


def local_database_host_allowed(url: str) -> bool:
    """A local process may use loopback or a single-label Compose host such as ``db``.

    A dotted host is a remote database. Production startup does not use this check.
    """
    try:
        host = (conninfo_to_dict(url).get("host") or "").strip().lower()
    except psycopg.Error:
        return False
    if host in {"", "localhost", "127.0.0.1", "::1"}:
        return True
    return "." not in host


def apply_migrations(url: str) -> None:
    with connect(url) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (id text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        applied = {row["id"] for row in conn.execute("SELECT id FROM schema_migrations")}
        v2_ready = conn.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'categories'
            """
        ).fetchone()
        if v2_ready and "001_commerce.sql" not in applied:
            conn.execute("INSERT INTO schema_migrations (id) VALUES ('001_commerce.sql')")
            if "002_rls.sql" not in applied:
                conn.execute("INSERT INTO schema_migrations (id) VALUES ('002_rls.sql')")
            applied = {row["id"] for row in conn.execute("SELECT id FROM schema_migrations")}
        for name in MIGRATION_FILES:
            if name in applied:
                continue
            sql = (migrations_dir() / name).read_text(encoding="utf-8")
            for stmt in split_sql(sql):
                conn.execute(stmt)
            conn.execute("INSERT INTO schema_migrations (id) VALUES (%s)", (name,))
        conn.commit()


def _catalog_tenant_name(payload: dict[str, Any]) -> str:
    """Display name from catalog payload shop or branch. Closet seeds omit both."""
    for key in ("shop", "branch"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            name = str(value.get("name") or "").strip()
            if name:
                return name
    return "Tienda piloto"


def seed_catalog(url: str, tenant_id: UUID, path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    seed_tenant = UUID(payload["tenant_id"])
    if seed_tenant != tenant_id:
        raise PermissionError("seed tenant does not match store tenant")
    with tenant_connection(url, tenant_id) as conn:
        conn.execute(
            """
            INSERT INTO tenants (id, name) VALUES (%s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (str(tenant_id), _catalog_tenant_name(payload)),
        )
        pending: list[tuple[Any, str]] = []
        for row in payload["products"]:
            attrs = dict(row.get("attributes") or {})
            category = str(attrs.get("category") or "general")
            cat = conn.execute(
                """
                INSERT INTO categories (tenant_id, name) VALUES (%s, %s)
                ON CONFLICT (tenant_id, name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                (str(tenant_id), category),
            ).fetchone()
            product = conn.execute(
                """
                INSERT INTO products (tenant_id, sku, name, description, category_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, sku) DO UPDATE
                  SET name = EXCLUDED.name, description = EXCLUDED.description, category_id = EXCLUDED.category_id
                RETURNING id
                """,
                (str(tenant_id), row["sku"], row["name"], row.get("description") or "", cat["id"]),
            ).fetchone()
            variant = conn.execute(
                """
                INSERT INTO product_variants (tenant_id, product_id, sku, attributes)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, sku) DO UPDATE
                  SET attributes = product_variants.attributes || EXCLUDED.attributes
                RETURNING id
                """,
                (str(tenant_id), product["id"], row["variant_sku"], Json(attrs)),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO prices (tenant_id, variant_id, amount, currency)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, variant_id) DO UPDATE
                  SET amount = EXCLUDED.amount, currency = EXCLUDED.currency
                """,
                (str(tenant_id), variant["id"], row["amount"], row.get("currency") or "BOB"),
            )
            # Quantity is live inventory. Seed only fills the first insert; a later
            # API restart must not reset sold units back to the JSON defaults.
            conn.execute(
                """
                INSERT INTO inventory (tenant_id, variant_id, quantity, low_stock_threshold)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, variant_id) DO UPDATE
                  SET low_stock_threshold = EXCLUDED.low_stock_threshold
                """,
                (
                    str(tenant_id),
                    variant["id"],
                    int(row.get("available_quantity") or 0),
                    int(row.get("low_stock_threshold") or 1),
                ),
            )
            pending.append((variant["id"], catalog_search_blob(row, attrs)))
        _write_embeddings(conn, tenant_id, pending)
        conn.commit()


def seed_shop_knowledge(url: str, tenant_id: UUID) -> None:
    from factory_os.domain.knowledge import load_shop_pack, shop_pack_for

    if shop_pack_for(tenant_id) is None:
        return
    pack = load_shop_pack()
    profile = pack.get("profile") if isinstance(pack.get("profile"), dict) else {}
    tenant_name = str(profile.get("name") or "").strip() or "Tienda piloto"
    with tenant_connection(url, tenant_id) as conn:
        conn.execute(
            """
            INSERT INTO tenants (id, name) VALUES (%s, %s)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
            """,
            (str(tenant_id), tenant_name),
        )
        conn.execute(
            """
            INSERT INTO shop_knowledge (tenant_id, payload, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (tenant_id) DO UPDATE
              SET payload = EXCLUDED.payload, updated_at = now()
            """,
            (str(tenant_id), Json(pack)),
        )


def seed_conversation_playbook(url: str, tenant_id: UUID) -> int:
    """Index curated playbook patterns into pgvector (behavior only; not catalog facts)."""
    from factory_os.domain.playbook import embed_playbook_documents, playbook_rows_for_seed

    rows = playbook_rows_for_seed()
    if not rows:
        return 0
    force = reindex_requested()
    dims = embed_dims()
    with tenant_connection(url, tenant_id) as conn:
        conn.execute(
            "INSERT INTO tenants (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
            (str(tenant_id), "Tienda piloto"),
        )
        existing = {
            row["pattern_id"]: row
            for row in conn.execute(
                """
                SELECT pattern_id, content_sha,
                       CASE WHEN embedding IS NULL THEN 0 ELSE vector_dims(embedding) END AS d
                FROM conversation_playbook
                """
            ).fetchall()
        }
        pending: list[dict[str, Any]] = []
        for row in rows:
            prev = existing.get(row["pattern_id"])
            if (
                not force
                and prev is not None
                and prev["content_sha"] == row["content_sha"]
                and int(prev["d"] or 0) == dims
            ):
                continue
            pending.append(row)
        if pending:
            vectors = embed_playbook_documents([item["embed_text"] for item in pending])
            for item, vec in zip(pending, vectors, strict=True):
                conn.execute(
                    """
                    INSERT INTO conversation_playbook (
                        tenant_id, pattern_id, intent, situation, next_action, skill,
                        capability, payload, embed_text, embedding, content_sha, updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s, now()
                    )
                    ON CONFLICT (tenant_id, pattern_id) DO UPDATE SET
                        intent = EXCLUDED.intent,
                        situation = EXCLUDED.situation,
                        next_action = EXCLUDED.next_action,
                        skill = EXCLUDED.skill,
                        capability = EXCLUDED.capability,
                        payload = EXCLUDED.payload,
                        embed_text = EXCLUDED.embed_text,
                        embedding = EXCLUDED.embedding,
                        content_sha = EXCLUDED.content_sha,
                        updated_at = now()
                    """,
                    (
                        str(tenant_id),
                        item["pattern_id"],
                        item["intent"],
                        item["situation"],
                        item["next_action"],
                        item["skill"],
                        item["capability"],
                        Json(item["payload"]),
                        item["embed_text"],
                        vector_literal(vec),
                        item["content_sha"],
                    ),
                )
        # Drop patterns removed from the curated file.
        keep = {row["pattern_id"] for row in rows}
        for pattern_id in existing:
            if pattern_id not in keep:
                conn.execute(
                    "DELETE FROM conversation_playbook WHERE pattern_id = %s",
                    (pattern_id,),
                )
    return len(rows)


def _embedding_dim(conn: psycopg.Connection, variant_id) -> int:
    row = conn.execute(
        """
        SELECT CASE WHEN embedding IS NULL THEN 0 ELSE vector_dims(embedding) END AS d
        FROM product_embeddings
        WHERE variant_id = %s
        """,
        (variant_id,),
    ).fetchone()
    if row is None:
        return 0
    return int(row["d"] or 0)


def _insert_embedding(
    conn: psycopg.Connection, tenant_id: UUID, variant_id, values: list[float]
) -> None:
    conn.execute(
        """
        INSERT INTO product_embeddings (variant_id, tenant_id, embedding)
        VALUES (%s, %s, %s::vector)
        ON CONFLICT (variant_id) DO UPDATE
          SET tenant_id = EXCLUDED.tenant_id, embedding = EXCLUDED.embedding
        """,
        (variant_id, str(tenant_id), vector_literal(values)),
    )


def _write_embeddings(
    conn: psycopg.Connection, tenant_id: UUID, pending: list[tuple[Any, str]]
) -> None:
    if not pending:
        return
    dims = embed_dims()
    force = reindex_requested()
    to_embed: list[tuple[Any, str]] = []
    for variant_id, text in pending:
        if force or _embedding_dim(conn, variant_id) != dims:
            to_embed.append((variant_id, text or " "))
    if not to_embed:
        return
    vectors = embed_documents([text for _, text in to_embed])
    for (variant_id, _), vec in zip(to_embed, vectors, strict=True):
        _insert_embedding(conn, tenant_id, variant_id, vec)


def _write_embedding(conn: psycopg.Connection, tenant_id: UUID, variant_id, text: str) -> None:
    _write_embeddings(conn, tenant_id, [(variant_id, text)])


@contextmanager
def tenant_connection(url: str, tenant_id: UUID) -> Iterator[psycopg.Connection]:
    conn = connect(url)
    try:
        conn.execute("SELECT set_config('app.tenant_id', %s, false)", (str(tenant_id),))
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _row_payment(row: dict[str, Any]) -> Payment:
    order_raw = row.get("order_id")
    customer_raw = row.get("customer_id")
    return Payment(
        id=row["id"],
        tenant_id=row["tenant_id"],
        order_id=order_raw,
        provider=row["provider"],
        provider_ref=row["provider_ref"],
        amount=Decimal(str(row["amount"])),
        currency=row["currency"],
        status=PaymentStatus(row["status"]),
        qr_payload=row["qr_payload"],
        variant_sku=str(row.get("variant_sku") or ""),
        customer_id=customer_raw,
        created_at=row.get("created_at"),
    )


def _row_reminder(row: dict[str, Any]) -> Reminder:
    return Reminder(
        id=row["id"],
        tenant_id=row["tenant_id"],
        customer_id=row["customer_id"],
        kind=row["kind"],
        body=row["body"],
        created_at=row.get("created_at"),
        sent_at=row.get("sent_at"),
    )


def _row_report_download(row: dict[str, Any]) -> ReportDownload:
    actor_id = row.get("actor_user_id")
    return ReportDownload(
        id=row["id"],
        tenant_id=row["tenant_id"],
        report_id=row["report_id"],
        period_id=row["period_id"] or "",
        date_from=row.get("date_from"),
        date_to=row.get("date_to"),
        format=row["format"],
        actor_name=row["actor_name"],
        actor_user_id=actor_id if actor_id is None else UUID(str(actor_id)),
        created_at=row.get("created_at"),
    )


def _row_panel_user(row: dict[str, Any]) -> PanelUser:
    return PanelUser(
        id=row["id"],
        tenant_id=row["tenant_id"],
        name=row["name"],
        email=row["email"],
        role=row["role"],
        secret_salt=row["secret_salt"],
        secret_hash=row["secret_hash"],
        active=bool(row["active"]),
        created_at=row.get("created_at"),
        pin_salt=row.get("pin_salt"),
        pin_hash=row.get("pin_hash"),
        job_title=str(row.get("job_title") or ""),
    )


def _row_ledger(row: dict[str, Any]) -> LedgerEntry:
    return LedgerEntry(
        id=row["id"],
        tenant_id=row["tenant_id"],
        source=row["source"],
        source_id=row["source_id"],
        direction=row["direction"],
        amount=Decimal(str(row["amount"])),
        currency=row["currency"],
        created_at=row.get("created_at"),
        status=row.get("status") or "recorded",
    )


def _row_chart_account(row: dict[str, Any]) -> ChartAccount:
    return ChartAccount(
        id=row["id"],
        tenant_id=row["tenant_id"],
        code=row["code"],
        name=row["name"],
        account_type=row["account_type"],
        is_system=bool(row.get("is_system", True)),
        active=bool(row.get("active", True)),
        created_at=row.get("created_at"),
    )


def _row_journal_line(row: dict[str, Any]) -> JournalLine:
    return JournalLine(
        id=row["id"],
        tenant_id=row["tenant_id"],
        entry_id=row["entry_id"],
        account_id=row["account_id"],
        direction=row["direction"],
        amount=Decimal(str(row["amount"])),
        currency=row["currency"],
        account_code=row.get("account_code"),
    )


def _row_journal_entry(row: dict[str, Any], lines: list[JournalLine] | None = None) -> JournalEntry:
    return JournalEntry(
        id=row["id"],
        tenant_id=row["tenant_id"],
        entry_at=row["entry_at"],
        origin_source=row["origin_source"],
        origin_id=row["origin_id"],
        kind=row["kind"],
        memo=row.get("memo") or "",
        reverses_entry_id=row.get("reverses_entry_id"),
        lines=list(lines or []),
        created_at=row.get("created_at"),
    )


def _row_accounting_period(row: dict[str, Any]) -> AccountingPeriod:
    return AccountingPeriod(
        id=row["id"],
        tenant_id=row["tenant_id"],
        date_from=row["date_from"],
        date_to=row["date_to"],
        status=row["status"],
        closed_at=row.get("closed_at"),
        closed_by_name=row.get("closed_by_name"),
    )


def _row_purchase(row: dict[str, Any]) -> PurchaseReceipt:
    return PurchaseReceipt(
        id=row["id"],
        tenant_id=row["tenant_id"],
        variant_sku=row["variant_sku"],
        quantity=int(row["quantity"]),
        unit_cost=Decimal(str(row["unit_cost"])),
        currency=row["currency"],
        created_at=row.get("created_at"),
        payment_method=(str(row.get("payment_method") or "cash").strip().lower() or "cash"),
        supplier_id=row.get("supplier_id"),
        received_at=row.get("received_at") or row.get("created_at"),
        purchase_order_id=row.get("purchase_order_id"),
    )


def _row_invoice(row: dict[str, Any]) -> InvoiceDocument:
    return InvoiceDocument(
        id=row["id"],
        tenant_id=row["tenant_id"],
        order_id=row.get("order_id"),
        status=row["status"],
        amount=Decimal(str(row["amount"])),
        currency=row["currency"],
        external_ref=row.get("external_ref") or "",
        created_at=row.get("created_at"),
    )


def _row_human_audit(row: dict[str, Any]) -> HumanAuditEvent:
    return HumanAuditEvent(
        id=row["id"],
        tenant_id=row["tenant_id"],
        actor_id=row.get("actor_id"),
        actor_name=row["actor_name"],
        actor_role=row["actor_role"],
        method=row["method"],
        path=row["path"],
        created_at=row.get("created_at"),
    )


def _row_supplier(row: dict[str, Any]) -> Supplier:
    return Supplier(
        id=row["id"],
        tenant_id=row["tenant_id"],
        name=row["name"],
        contact_name=row.get("contact_name") or "",
        phone=row.get("phone") or "",
        whatsapp=row.get("whatsapp") or "",
        email=row.get("email") or "",
        notes=row.get("notes") or "",
        payment_terms=row.get("payment_terms") or "cash",
        lead_time_days=int(row.get("lead_time_days") or 0),
        active=bool(row.get("active", True)),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _row_purchase_order_line(row: dict[str, Any]) -> PurchaseOrderLine:
    unit_cost = row.get("unit_cost")
    return PurchaseOrderLine(
        id=row["id"],
        tenant_id=row["tenant_id"],
        purchase_order_id=row["purchase_order_id"],
        variant_sku=row["variant_sku"],
        quantity_ordered=int(row["quantity_ordered"]),
        quantity_received=int(row.get("quantity_received") or 0),
        unit_cost=None if unit_cost is None else Decimal(str(unit_cost)),
        currency=row.get("currency") or "BOB",
    )


def _row_purchase_order(
    row: dict[str, Any], lines: list[PurchaseOrderLine] | None = None
) -> PurchaseOrder:
    return PurchaseOrder(
        id=row["id"],
        tenant_id=row["tenant_id"],
        supplier_id=row["supplier_id"],
        status=row.get("status") or "draft",
        notes=row.get("notes") or "",
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
        lines=list(lines or []),
        payment_status=str(row.get("payment_status") or "unpaid"),
        amount_paid=Decimal(str(row.get("amount_paid") or "0")),
    )


def _row_cash_movement(row: dict[str, Any]) -> CashMovement:
    return CashMovement(
        id=row["id"],
        tenant_id=row["tenant_id"],
        direction=row["direction"],
        amount=Decimal(str(row["amount"])),
        currency=row["currency"],
        reason=row["reason"],
        session_id=row.get("session_id"),
        created_at=row.get("created_at"),
        category=row.get("category") or "",
        method=row.get("method") or "cash",
        status=row.get("status") or "recorded",
        recorded_by_name=row.get("recorded_by_name") or "sistema",
        recorded_by_id=row.get("recorded_by_id"),
        void_reason=row.get("void_reason"),
        voided_by_name=row.get("voided_by_name"),
        voided_by_id=row.get("voided_by_id"),
        voided_at=row.get("voided_at"),
        ticket_id=row.get("ticket_id"),
    )


def _row_cash_attachment(row: dict[str, Any]) -> CashAttachment:
    return CashAttachment(
        id=row["id"],
        tenant_id=row["tenant_id"],
        movement_id=row["movement_id"],
        filename=row["filename"],
        content_type=row.get("content_type") or "application/octet-stream",
        size_bytes=int(row["size_bytes"]),
        storage_key=row["storage_key"],
        uploaded_by_name=row.get("uploaded_by_name") or "sistema",
        created_at=row.get("created_at"),
    )


def _row_media_asset(row: dict[str, Any]) -> MediaAsset:
    return MediaAsset(
        id=row["id"],
        tenant_id=row["tenant_id"],
        kind=row.get("kind") or "image",
        mime=row["mime"],
        size_bytes=int(row["size_bytes"]),
        storage_key=row["storage_key"],
        origin=row["origin"],
        thumb_key=row.get("thumb_key"),
        medium_key=row.get("medium_key"),
        uploaded_by=row.get("uploaded_by"),
        provider_ref=row.get("provider_ref"),
        created_at=row.get("created_at"),
    )


def _row_product_media(row: dict[str, Any]) -> ProductMedia:
    return ProductMedia(
        id=row["id"],
        tenant_id=row["tenant_id"],
        product_sku=row["product_sku"],
        asset_id=row["asset_id"],
        is_primary=bool(row.get("is_primary")),
        sort_order=int(row.get("sort_order") or 0),
        created_at=row.get("created_at"),
    )


def _row_conversation_media(row: dict[str, Any]) -> ConversationMedia:
    return ConversationMedia(
        id=row["id"],
        tenant_id=row["tenant_id"],
        conversation_id=row["conversation_id"],
        asset_id=row.get("asset_id"),
        provider_ref=row.get("provider_ref"),
        message_index=row.get("message_index"),
        direction=row["direction"],
        status=row.get("status") or "ready",
        kind=row["kind"],
        mime=row.get("mime"),
        filename=row.get("filename"),
        size_bytes=int(row["size_bytes"]) if row.get("size_bytes") is not None else None,
        error=row.get("error"),
        uploaded_by=row.get("uploaded_by"),
        created_at=row.get("created_at"),
        transcript_text=row.get("transcript_text"),
        summary_text=row.get("summary_text"),
        enrichment_status=row.get("enrichment_status") or "none",
        enrichment_error=row.get("enrichment_error"),
    )


def _row_entity_media(row: dict[str, Any]) -> EntityMedia:
    return EntityMedia(
        id=row["id"],
        tenant_id=row["tenant_id"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        asset_id=row["asset_id"],
        filename=row["filename"],
        kind=row["kind"],
        mime=row["mime"],
        size_bytes=int(row["size_bytes"]),
        note=row.get("note"),
        uploaded_by=row.get("uploaded_by"),
        created_at=row.get("created_at"),
    )


def _row_cash_sale_ticket(row: dict[str, Any]) -> CashSaleTicket:
    from factory_os.domain.cash_sales import lines_from_json

    return CashSaleTicket(
        id=row["id"],
        tenant_id=row["tenant_id"],
        number=row["number"],
        status=row.get("status") or "recorded",
        method=row.get("method") or "cash",
        total=Decimal(str(row["total"])),
        currency=row.get("currency") or "BOB",
        lines=lines_from_json(row.get("lines")),
        session_id=row.get("session_id"),
        movement_id=row.get("movement_id"),
        payment_id=row.get("payment_id"),
        provider_ref=row.get("provider_ref"),
        recorded_by_name=row.get("recorded_by_name") or "sistema",
        recorded_by_id=row.get("recorded_by_id"),
        created_at=row.get("created_at"),
        order_id=row.get("order_id"),
        discount_amount=Decimal(str(row.get("discount_amount") or "0")),
    )


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _row_cash_session(row: dict[str, Any]) -> CashSession:
    return CashSession(
        id=row["id"],
        tenant_id=row["tenant_id"],
        status=row["status"],
        opening_float=Decimal(str(row["opening_float"])),
        currency=row["currency"],
        opened_by_name=row["opened_by_name"],
        opened_by_id=row.get("opened_by_id"),
        opened_at=row.get("opened_at"),
        closed_at=row.get("closed_at"),
        closed_by_name=row.get("closed_by_name"),
        closed_by_id=row.get("closed_by_id"),
        counted_cash=_decimal_or_none(row.get("counted_cash")),
        expected_cash=_decimal_or_none(row.get("expected_cash")),
        difference=_decimal_or_none(row.get("difference")),
        close_note=row.get("close_note"),
    )


def _modifier_from_row(row: dict[str, Any]):
    from factory_os.domain.modifiers import CatalogModifier

    modifier_id = row["id"]
    tenant = row["tenant_id"]
    return CatalogModifier(
        id=modifier_id if isinstance(modifier_id, UUID) else UUID(str(modifier_id)),
        tenant_id=tenant if isinstance(tenant, UUID) else UUID(str(tenant)),
        name=str(row.get("name") or ""),
        price_delta=Decimal(str(row.get("price_delta") or "0")),
        currency=str(row.get("currency") or "BOB"),
    )


def _stored_options(item: Any) -> list[dict[str, Any]]:
    raw = getattr(item, "options", None) or []
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def _loaded_options(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


class PostgresCommerceStore:
    def __init__(self, url: str, tenant_id: UUID) -> None:
        self.url = url
        self.tenant_id = tenant_id

    def require_tenant(self, tenant_id: UUID) -> None:
        if tenant_id != self.tenant_id:
            raise PermissionError("cross-tenant access denied")

    def iter_variants(self) -> Iterable[VariantRecord]:
        with tenant_connection(self.url, self.tenant_id) as conn:
            # Filter by tenant even if the DB role bypasses RLS (admin/test URLs).
            rows = conn.execute(
                "SELECT * FROM agent_catalog_read WHERE tenant_id = %s",
                (str(self.tenant_id),),
            ).fetchall()
        records = []
        for row in rows:
            attrs = row["attributes"] or {}
            if isinstance(attrs, str):
                attrs = json.loads(attrs)
            blob = catalog_search_blob(
                {
                    "name": row["name"] or "",
                    "description": row["description"] or "",
                    "category": row["category"] or "",
                    "product_sku": row["product_sku"],
                    "variant_sku": row["variant_sku"],
                },
                {**attrs, "codigo": attrs.get("codigo") or row.get("codigo") or ""},
            )
            supplier_raw = row.get("supplier_id")
            supplier_id = UUID(str(supplier_raw)) if supplier_raw else None
            records.append(
                VariantRecord(
                    product_sku=row["product_sku"],
                    variant_sku=row["variant_sku"],
                    name=row["name"],
                    description=row["description"] or "",
                    category=row["category"] or "",
                    attributes=dict(attrs),
                    price=Decimal(str(row["price"])),
                    currency=row["currency"],
                    stock=int(row["stock"] or 0),
                    tokens=tokenize(blob),
                    supplier_id=supplier_id,
                    reorder_threshold=int(row.get("reorder_threshold") or 1),
                )
            )
        return records

    def list_embeddings(self) -> dict[str, list[float]]:
        with tenant_connection(self.url, self.tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT v.sku AS variant_sku, e.embedding::text AS embedding
                FROM product_embeddings e
                JOIN product_variants v ON v.id = e.variant_id AND v.tenant_id = e.tenant_id
                """
            ).fetchall()
        return {row["variant_sku"]: parse_vector(row["embedding"]) for row in rows}

    def similar_variants(self, query_vec: list[float], limit: int = 40) -> dict[str, float]:
        lit = vector_literal(query_vec)
        with tenant_connection(self.url, self.tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT v.sku AS variant_sku,
                       (1 - (e.embedding <=> %s::vector))::float AS sim
                FROM product_embeddings e
                JOIN product_variants v ON v.id = e.variant_id AND v.tenant_id = e.tenant_id
                ORDER BY e.embedding <=> %s::vector
                LIMIT %s
                """,
                (lit, lit, limit),
            ).fetchall()
        return {row["variant_sku"]: float(row["sim"] or 0.0) for row in rows}

    def search_playbook(self, query: str, limit: int = 2) -> list[dict[str, Any]]:
        """kNN over conversation_playbook, re-ranked with content tokens (hybrid)."""
        from factory_os.domain.embeddings import embed_query
        from factory_os.domain.playbook import (
            PLAYBOOK_MAX_HITS,
            PLAYBOOK_VECTOR_MIN,
            _content_tokens,
            _query_tokens,
        )

        self.require_tenant(self.tenant_id)
        q = (query or "").strip()
        if not q:
            return []
        cap = max(1, min(int(limit), PLAYBOOK_MAX_HITS))
        lit = vector_literal(embed_query(q))
        q_tokens = _query_tokens(q)
        with tenant_connection(self.url, self.tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT pattern_id, intent, situation, next_action, skill, capability,
                       payload,
                       (1 - (embedding <=> %s::vector))::float AS sim
                FROM conversation_playbook
                ORDER BY embedding <=> %s::vector
                LIMIT 24
                """,
                (lit, lit),
            ).fetchall()
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            payload = row.get("payload") or {}
            if not isinstance(payload, dict):
                payload = {}
            pattern = {
                "intent": row.get("intent") or "",
                "situation": row.get("situation") or "",
                "goal": payload.get("goal") or "",
                "signals": payload.get("signals") or [],
            }
            sim = float(row.get("sim") or 0.0)
            lexical = float(len(q_tokens & _content_tokens(pattern)))
            if sim < PLAYBOOK_VECTOR_MIN and lexical < 1:
                continue
            score = sim + 0.45 * lexical
            item = dict(row)
            item["sim"] = score
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:cap]]

    def put_embedding(self, variant_sku: str, embedding: list[float]) -> None:
        with tenant_connection(self.url, self.tenant_id) as conn:
            row = conn.execute(
                "SELECT id FROM product_variants WHERE sku = %s",
                (variant_sku,),
            ).fetchone()
            if row is None:
                return
            conn.execute(
                """
                INSERT INTO product_embeddings (variant_id, tenant_id, embedding)
                VALUES (%s, %s, %s::vector)
                ON CONFLICT (variant_id) DO UPDATE
                  SET tenant_id = EXCLUDED.tenant_id, embedding = EXCLUDED.embedding
                """,
                (row["id"], str(self.tenant_id), vector_literal(embedding)),
            )

    def get_variant(self, tenant_id: UUID, variant_sku: str) -> VariantRecord | None:
        self.require_tenant(tenant_id)
        for record in self.iter_variants():
            if record.variant_sku == variant_sku:
                return record
        return None

    def get_or_create_customer(self, tenant_id: UUID, wa_number: str) -> Customer:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                "SELECT * FROM customers WHERE wa_number = %s", (wa_number,)
            ).fetchone()
            if row is None:
                row = conn.execute(
                    """
                    INSERT INTO customers (tenant_id, wa_number) VALUES (%s, %s)
                    RETURNING *
                    """,
                    (str(tenant_id), wa_number),
                ).fetchone()
        return Customer(
            id=row["id"],
            tenant_id=row["tenant_id"],
            wa_number=row["wa_number"],
            name=row["name"],
            address=row["address"],
        )

    def get_or_create_conversation(self, tenant_id: UUID, customer: Customer) -> Conversation:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE customer_id = %s", (str(customer.id),)
            ).fetchone()
            if row is None:
                row = conn.execute(
                    """
                    INSERT INTO conversations (tenant_id, customer_id, working_state)
                    VALUES (%s, %s, '{}'::jsonb)
                    RETURNING *
                    """,
                    (str(tenant_id), str(customer.id)),
                ).fetchone()
            messages = conn.execute(
                """
                SELECT role, body, created_at FROM conversation_messages
                WHERE conversation_id = %s ORDER BY created_at
                """,
                (str(row["id"]),),
            ).fetchall()
        state_payload = row["working_state"] or {}
        if isinstance(state_payload, str):
            state_payload = json.loads(state_payload)
        last_at = messages[-1]["created_at"] if messages else None
        return Conversation(
            id=row["id"],
            tenant_id=row["tenant_id"],
            customer_id=row["customer_id"],
            messages=[(m["role"], m["body"]) for m in messages],
            state=WorkingState.from_json(state_payload),
            summary_text=row.get("summary_text"),
            summary_msg_count=int(row.get("summary_msg_count") or 0),
            outcome=row.get("outcome"),
            outcome_reason=row.get("outcome_reason"),
            source_kind=row.get("source_kind"),
            live_code=row.get("live_code"),
            closed_at=row.get("closed_at"),
            last_message_at=last_at,
        )

    def get_customer(self, tenant_id: UUID, customer_id: UUID) -> Customer | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute("SELECT * FROM customers WHERE id = %s", (str(customer_id),)).fetchone()
        if row is None:
            return None
        return Customer(
            id=row["id"],
            tenant_id=row["tenant_id"],
            wa_number=row["wa_number"],
            name=row["name"],
            address=row["address"],
        )

    def list_customers(self, tenant_id: UUID) -> list[Customer]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute("SELECT * FROM customers ORDER BY wa_number").fetchall()
        return [
            Customer(
                id=row["id"],
                tenant_id=row["tenant_id"],
                wa_number=row["wa_number"],
                name=row["name"],
                address=row["address"],
            )
            for row in rows
        ]

    def add_customer_note(self, tenant_id: UUID, customer_id: UUID, body: str) -> CustomerNote:
        self.require_tenant(tenant_id)
        text = body.strip()
        if not text:
            raise ValueError("empty_note")
        if self.get_customer(tenant_id, customer_id) is None:
            raise KeyError(customer_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO customer_notes (tenant_id, customer_id, body)
                VALUES (%s, %s, %s)
                RETURNING id, tenant_id, customer_id, body, created_at
                """,
                (str(tenant_id), str(customer_id), text),
            ).fetchone()
        return CustomerNote(
            id=row["id"],
            tenant_id=row["tenant_id"],
            customer_id=row["customer_id"],
            body=row["body"],
            created_at=row["created_at"],
        )

    def list_customer_notes(self, tenant_id: UUID, customer_id: UUID) -> list[CustomerNote]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT id, tenant_id, customer_id, body, created_at
                FROM customer_notes
                WHERE customer_id = %s
                ORDER BY created_at
                """,
                (str(customer_id),),
            ).fetchall()
        return [
            CustomerNote(
                id=row["id"],
                tenant_id=row["tenant_id"],
                customer_id=row["customer_id"],
                body=row["body"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_reminders(self, tenant_id: UUID) -> list[Reminder]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT id, tenant_id, customer_id, kind, body, created_at, sent_at
                FROM reminders
                ORDER BY created_at
                """
            ).fetchall()
        return [_row_reminder(row) for row in rows]

    def add_reminder(self, tenant_id: UUID, customer_id: UUID, kind: str, body: str) -> Reminder:
        self.require_tenant(tenant_id)
        if kind not in {"follow_up", "repurchase", "collections"}:
            raise ValueError("bad_reminder_kind")
        text = body.strip()
        if not text:
            raise ValueError("empty_reminder")
        if self.get_customer(tenant_id, customer_id) is None:
            raise KeyError(customer_id)
        for current in self.list_reminders(tenant_id):
            if current.customer_id == customer_id and current.kind == kind and current.sent_at is None:
                return current
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO reminders (tenant_id, customer_id, kind, body)
                VALUES (%s, %s, %s, %s)
                RETURNING id, tenant_id, customer_id, kind, body, created_at, sent_at
                """,
                (str(tenant_id), str(customer_id), kind, text),
            ).fetchone()
        return _row_reminder(row)

    def mark_reminder_sent(self, tenant_id: UUID, reminder_id: UUID) -> Reminder:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE reminders
                SET sent_at = now()
                WHERE id = %s
                RETURNING id, tenant_id, customer_id, kind, body, created_at, sent_at
                """,
                (str(reminder_id),),
            ).fetchone()
        if row is None:
            raise KeyError(reminder_id)
        return _row_reminder(row)

    def record_report_download(
        self,
        tenant_id: UUID,
        *,
        report_id: str,
        period_id: str,
        date_from: datetime | None,
        date_to: datetime | None,
        format: str,
        actor_name: str,
        actor_user_id: UUID | None,
    ) -> ReportDownload:
        self.require_tenant(tenant_id)
        report = report_id.strip()
        fmt = format.strip().lower()
        name = actor_name.strip()
        if not report or not fmt or not name:
            raise ValueError("bad_download")
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO report_download_log (
                    tenant_id, report_id, period_id, date_from, date_to,
                    format, actor_name, actor_user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, tenant_id, report_id, period_id, date_from, date_to,
                          format, actor_name, actor_user_id, created_at
                """,
                (
                    str(tenant_id),
                    report,
                    (period_id or "").strip(),
                    date_from,
                    date_to,
                    fmt,
                    name,
                    str(actor_user_id) if actor_user_id else None,
                ),
            ).fetchone()
        return _row_report_download(row)

    def list_report_downloads(self, tenant_id: UUID, limit: int = 50) -> list[ReportDownload]:
        self.require_tenant(tenant_id)
        size = 50 if limit < 1 else min(int(limit), 200)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT id, tenant_id, report_id, period_id, date_from, date_to,
                       format, actor_name, actor_user_id, created_at
                FROM report_download_log
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (size,),
            ).fetchall()
        return [_row_report_download(row) for row in rows]

    def add_panel_user(
        self,
        tenant_id: UUID,
        name: str,
        email: str,
        role: str,
        secret_salt: str,
        secret_hash: str,
        *,
        pin_salt: str | None = None,
        pin_hash: str | None = None,
        job_title: str = "",
    ) -> PanelUser:
        from factory_os.domain.panel_access import STORED_PANEL_ROLES

        self.require_tenant(tenant_id)
        cleaned_name = name.strip()
        cleaned_email = email.strip().lower()
        if not cleaned_name:
            raise ValueError("empty_name")
        if "@" not in cleaned_email or cleaned_email.startswith("@") or " " in cleaned_email:
            raise ValueError("bad_email")
        if role not in STORED_PANEL_ROLES:
            raise ValueError("bad_role")
        if any(user.email == cleaned_email for user in self.list_panel_users(tenant_id)):
            raise ValueError("duplicate_email")
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO panel_users (
                    tenant_id, name, email, role, secret_salt, secret_hash, pin_salt, pin_hash,
                    job_title
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, tenant_id, name, email, role, secret_salt, secret_hash,
                          active, created_at, pin_salt, pin_hash, job_title
                """,
                (
                    str(tenant_id),
                    cleaned_name,
                    cleaned_email,
                    role,
                    secret_salt,
                    secret_hash,
                    pin_salt,
                    pin_hash,
                    (job_title or "").strip(),
                ),
            ).fetchone()
        return _row_panel_user(row)

    def list_panel_users(self, tenant_id: UUID) -> list[PanelUser]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT id, tenant_id, name, email, role, secret_salt, secret_hash,
                       active, created_at, pin_salt, pin_hash, job_title
                FROM panel_users
                ORDER BY created_at
                """
            ).fetchall()
        return [_row_panel_user(row) for row in rows]

    def get_panel_user(self, tenant_id: UUID, user_id: UUID) -> PanelUser | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                SELECT id, tenant_id, name, email, role, secret_salt, secret_hash,
                       active, created_at, pin_salt, pin_hash, job_title
                FROM panel_users
                WHERE id = %s
                """,
                (str(user_id),),
            ).fetchone()
        return _row_panel_user(row) if row else None

    def set_panel_user_secret(
        self,
        tenant_id: UUID,
        user_id: UUID,
        secret_salt: str,
        secret_hash: str,
    ) -> PanelUser:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE panel_users
                SET secret_salt = %s, secret_hash = %s
                WHERE id = %s AND active
                RETURNING id, tenant_id, name, email, role, secret_salt, secret_hash,
                          active, created_at, pin_salt, pin_hash, job_title
                """,
                (secret_salt, secret_hash, str(user_id)),
            ).fetchone()
        if row is None:
            raise KeyError(user_id)
        return _row_panel_user(row)

    def add_human_audit(
        self,
        tenant_id: UUID,
        actor_id: UUID | None,
        actor_name: str,
        actor_role: str,
        method: str,
        path: str,
    ) -> HumanAuditEvent:
        from factory_os.domain.panel_access import AUDIT_ROLES

        self.require_tenant(tenant_id)
        if actor_role not in AUDIT_ROLES:
            raise ValueError("bad_role")
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO human_audit_events
                    (tenant_id, actor_id, actor_name, actor_role, method, path)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, tenant_id, actor_id, actor_name, actor_role, method, path, created_at
                """,
                (
                    str(tenant_id),
                    str(actor_id) if actor_id else None,
                    actor_name.strip(),
                    actor_role,
                    method,
                    path,
                ),
            ).fetchone()
        return _row_human_audit(row)

    def list_human_audit(self, tenant_id: UUID) -> list[HumanAuditEvent]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT id, tenant_id, actor_id, actor_name, actor_role, method, path, created_at
                FROM human_audit_events
                ORDER BY created_at
                """
            ).fetchall()
        return [_row_human_audit(row) for row in rows]

    def list_suppliers(self, tenant_id: UUID, *, active_only: bool = True) -> list[Supplier]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            if active_only:
                rows = conn.execute(
                    """
                    SELECT * FROM suppliers
                    WHERE active = true
                    ORDER BY name, created_at
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM suppliers
                    ORDER BY active DESC, name, created_at
                    """
                ).fetchall()
        return [_row_supplier(row) for row in rows]

    def get_supplier(self, tenant_id: UUID, supplier_id: UUID) -> Supplier | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                "SELECT * FROM suppliers WHERE id = %s",
                (str(supplier_id),),
            ).fetchone()
        return _row_supplier(row) if row else None

    def create_supplier(
        self,
        tenant_id: UUID,
        name: str,
        *,
        contact_name: str = "",
        phone: str = "",
        whatsapp: str = "",
        email: str = "",
        notes: str = "",
        payment_terms: str = "cash",
        lead_time_days: int = 0,
    ) -> Supplier:
        self.require_tenant(tenant_id)
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("bad_name")
        if lead_time_days < 0:
            raise ValueError("bad_lead_time")
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO suppliers (
                    tenant_id, name, contact_name, phone, whatsapp, email, notes,
                    payment_terms, lead_time_days
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    str(tenant_id),
                    cleaned,
                    contact_name.strip(),
                    phone.strip(),
                    whatsapp.strip(),
                    email.strip(),
                    notes.strip(),
                    (payment_terms or "cash").strip() or "cash",
                    int(lead_time_days),
                ),
            ).fetchone()
        return _row_supplier(row)

    def update_supplier(
        self,
        tenant_id: UUID,
        supplier_id: UUID,
        *,
        name: str | None = None,
        contact_name: str | None = None,
        phone: str | None = None,
        whatsapp: str | None = None,
        email: str | None = None,
        notes: str | None = None,
        payment_terms: str | None = None,
        lead_time_days: int | None = None,
        active: bool | None = None,
    ) -> Supplier:
        self.require_tenant(tenant_id)
        current = self.get_supplier(tenant_id, supplier_id)
        if current is None:
            raise KeyError(supplier_id)
        next_name = current.name if name is None else name.strip()
        if not next_name:
            raise ValueError("bad_name")
        next_lead = current.lead_time_days if lead_time_days is None else int(lead_time_days)
        if next_lead < 0:
            raise ValueError("bad_lead_time")
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE suppliers SET
                    name = %s,
                    contact_name = %s,
                    phone = %s,
                    whatsapp = %s,
                    email = %s,
                    notes = %s,
                    payment_terms = %s,
                    lead_time_days = %s,
                    active = %s,
                    updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (
                    next_name,
                    current.contact_name if contact_name is None else contact_name.strip(),
                    current.phone if phone is None else phone.strip(),
                    current.whatsapp if whatsapp is None else whatsapp.strip(),
                    current.email if email is None else email.strip(),
                    current.notes if notes is None else notes.strip(),
                    (
                        current.payment_terms
                        if payment_terms is None
                        else (payment_terms.strip() or "cash")
                    ),
                    next_lead,
                    current.active if active is None else bool(active),
                    str(supplier_id),
                ),
            ).fetchone()
        if row is None:
            raise KeyError(supplier_id)
        return _row_supplier(row)

    def deactivate_supplier(self, tenant_id: UUID, supplier_id: UUID) -> Supplier:
        return self.update_supplier(tenant_id, supplier_id, active=False)

    def set_variant_supplier(
        self, tenant_id: UUID, variant_sku: str, supplier_id: UUID | None
    ) -> VariantRecord:
        self.require_tenant(tenant_id)
        if supplier_id is not None and self.get_supplier(tenant_id, supplier_id) is None:
            raise KeyError(supplier_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE product_variants
                SET supplier_id = %s
                WHERE tenant_id = %s AND sku = %s
                RETURNING sku
                """,
                (
                    str(supplier_id) if supplier_id is not None else None,
                    str(tenant_id),
                    variant_sku,
                ),
            ).fetchone()
        if row is None:
            raise KeyError(variant_sku)
        record = self.get_variant(tenant_id, variant_sku)
        if record is None:
            raise KeyError(variant_sku)
        return record

    def set_reorder_threshold(
        self, tenant_id: UUID, variant_sku: str, threshold: int
    ) -> VariantRecord:
        self.require_tenant(tenant_id)
        if threshold < 0:
            raise ValueError("bad_threshold")
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE inventory AS i
                SET low_stock_threshold = %s
                FROM product_variants AS v
                WHERE i.variant_id = v.id
                  AND i.tenant_id = v.tenant_id
                  AND v.tenant_id = %s
                  AND v.sku = %s
                RETURNING v.sku
                """,
                (int(threshold), str(tenant_id), variant_sku),
            ).fetchone()
        if row is None:
            raise KeyError(variant_sku)
        record = self.get_variant(tenant_id, variant_sku)
        if record is None:
            raise KeyError(variant_sku)
        return record

    def create_purchase_order(
        self,
        tenant_id: UUID,
        supplier_id: UUID,
        lines: list[dict[str, Any]],
        *,
        status: str = "draft",
        notes: str = "",
    ) -> PurchaseOrder:
        self.require_tenant(tenant_id)
        if status not in {"draft", "sent", "partially_received", "received", "cancelled"}:
            raise ValueError("bad_status")
        if not lines:
            raise ValueError("empty_lines")
        if self.get_supplier(tenant_id, supplier_id) is None:
            raise KeyError(supplier_id)
        with tenant_connection(self.url, tenant_id) as conn:
            header = conn.execute(
                """
                INSERT INTO purchase_orders (tenant_id, supplier_id, status, notes)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (str(tenant_id), str(supplier_id), status, (notes or "").strip()),
            ).fetchone()
            order_id = header["id"]
            po_lines: list[PurchaseOrderLine] = []
            for raw in lines:
                sku = str(raw.get("variant_sku") or "").strip()
                qty = int(raw.get("quantity") or raw.get("quantity_ordered") or 0)
                if not sku or qty < 1:
                    raise ValueError("bad_line")
                variant = conn.execute(
                    "SELECT sku FROM product_variants WHERE tenant_id = %s AND sku = %s",
                    (str(tenant_id), sku),
                ).fetchone()
                if variant is None:
                    raise KeyError(sku)
                unit_cost = raw.get("unit_cost")
                currency = str(raw.get("currency") or "BOB") or "BOB"
                line_row = conn.execute(
                    """
                    INSERT INTO purchase_order_lines (
                        tenant_id, purchase_order_id, variant_sku,
                        quantity_ordered, unit_cost, currency
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        str(tenant_id),
                        str(order_id),
                        sku,
                        qty,
                        None if unit_cost is None else str(unit_cost),
                        currency,
                    ),
                ).fetchone()
                po_lines.append(_row_purchase_order_line(line_row))
        return _row_purchase_order(header, po_lines)

    def list_purchase_orders(
        self, tenant_id: UUID, *, status: str | None = None
    ) -> list[PurchaseOrder]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            if status is None:
                headers = conn.execute(
                    """
                    SELECT * FROM purchase_orders
                    ORDER BY created_at DESC
                    """
                ).fetchall()
            else:
                headers = conn.execute(
                    """
                    SELECT * FROM purchase_orders
                    WHERE status = %s
                    ORDER BY created_at DESC
                    """,
                    (status,),
                ).fetchall()
            out: list[PurchaseOrder] = []
            for header in headers:
                line_rows = conn.execute(
                    """
                    SELECT * FROM purchase_order_lines
                    WHERE purchase_order_id = %s
                    ORDER BY variant_sku
                    """,
                    (str(header["id"]),),
                ).fetchall()
                out.append(
                    _row_purchase_order(
                        header, [_row_purchase_order_line(row) for row in line_rows]
                    )
                )
        return out

    def get_purchase_order(
        self, tenant_id: UUID, order_id: UUID
    ) -> PurchaseOrder | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            header = conn.execute(
                "SELECT * FROM purchase_orders WHERE id = %s",
                (str(order_id),),
            ).fetchone()
            if header is None:
                return None
            line_rows = conn.execute(
                """
                SELECT * FROM purchase_order_lines
                WHERE purchase_order_id = %s
                ORDER BY variant_sku
                """,
                (str(order_id),),
            ).fetchall()
        return _row_purchase_order(
            header, [_row_purchase_order_line(row) for row in line_rows]
        )

    def set_purchase_order_status(
        self, tenant_id: UUID, order_id: UUID, status: str
    ) -> PurchaseOrder:
        self.require_tenant(tenant_id)
        if status not in {"draft", "sent", "partially_received", "received", "cancelled"}:
            raise ValueError("bad_status")
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE purchase_orders
                SET status = %s, updated_at = now()
                WHERE id = %s
                RETURNING id
                """,
                (status, str(order_id)),
            ).fetchone()
        if row is None:
            raise KeyError(order_id)
        order = self.get_purchase_order(tenant_id, order_id)
        if order is None:
            raise KeyError(order_id)
        return order

    def set_purchase_order_line_received(
        self,
        tenant_id: UUID,
        order_id: UUID,
        line_id: UUID,
        quantity_received: int,
        unit_cost: Decimal | None = None,
    ) -> PurchaseOrderLine:
        self.require_tenant(tenant_id)
        if quantity_received < 0:
            raise ValueError("bad_quantity")
        with tenant_connection(self.url, tenant_id) as conn:
            current = conn.execute(
                """
                SELECT quantity_ordered FROM purchase_order_lines
                WHERE id = %s AND purchase_order_id = %s
                """,
                (str(line_id), str(order_id)),
            ).fetchone()
            if current is None:
                raise KeyError(line_id)
            if quantity_received > int(current["quantity_ordered"]):
                raise ValueError("over_receive")
            row = conn.execute(
                """
                UPDATE purchase_order_lines
                SET quantity_received = %s,
                    unit_cost = COALESCE(%s, unit_cost)
                WHERE id = %s AND purchase_order_id = %s
                RETURNING *
                """,
                (
                    int(quantity_received),
                    None if unit_cost is None else str(unit_cost),
                    str(line_id),
                    str(order_id),
                ),
            ).fetchone()
            conn.execute(
                "UPDATE purchase_orders SET updated_at = now() WHERE id = %s",
                (str(order_id),),
            )
        if row is None:
            raise KeyError(line_id)
        return _row_purchase_order_line(row)

    def set_purchase_order_payment(
        self,
        tenant_id: UUID,
        order_id: UUID,
        *,
        payment_status: str,
        amount_paid: Decimal,
    ) -> PurchaseOrder:
        self.require_tenant(tenant_id)
        status = (payment_status or "").strip().lower()
        if status not in {"unpaid", "partial", "paid"}:
            raise ValueError("bad_payment_status")
        paid = Decimal(str(amount_paid))
        if paid < 0:
            raise ValueError("bad_amount")
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE purchase_orders
                SET payment_status = %s, amount_paid = %s, updated_at = now()
                WHERE id = %s
                RETURNING id
                """,
                (status, str(paid), str(order_id)),
            ).fetchone()
        if row is None:
            raise KeyError(order_id)
        order = self.get_purchase_order(tenant_id, order_id)
        if order is None:
            raise KeyError(order_id)
        return order

    def get_conversation(self, tenant_id: UUID, conversation_id: UUID) -> Conversation | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = %s", (str(conversation_id),)
            ).fetchone()
            if row is None:
                return None
            messages = conn.execute(
                """
                SELECT role, body, created_at FROM conversation_messages
                WHERE conversation_id = %s ORDER BY created_at
                """,
                (str(row["id"]),),
            ).fetchall()
        state_payload = row["working_state"] or {}
        if isinstance(state_payload, str):
            state_payload = json.loads(state_payload)
        last_at = messages[-1]["created_at"] if messages else None
        return Conversation(
            id=row["id"],
            tenant_id=row["tenant_id"],
            customer_id=row["customer_id"],
            messages=[(m["role"], m["body"]) for m in messages],
            state=WorkingState.from_json(state_payload),
            summary_text=row.get("summary_text"),
            summary_msg_count=int(row.get("summary_msg_count") or 0),
            outcome=row.get("outcome"),
            outcome_reason=row.get("outcome_reason"),
            source_kind=row.get("source_kind"),
            live_code=row.get("live_code"),
            closed_at=row.get("closed_at"),
            last_message_at=last_at,
        )

    def list_conversations(self, tenant_id: UUID) -> list[Conversation]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT c.id
                FROM conversations c
                LEFT JOIN LATERAL (
                    SELECT created_at
                    FROM conversation_messages
                    WHERE conversation_id = c.id
                    ORDER BY created_at DESC
                    LIMIT 1
                ) last ON true
                ORDER BY last.created_at DESC NULLS LAST
                """
            ).fetchall()
        conversations: list[Conversation] = []
        for row in rows:
            conv = self.get_conversation(tenant_id, row["id"])
            if conv is not None:
                conversations.append(conv)
        return conversations

    def append_message(self, conv: Conversation, role: str, text: str) -> None:
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        conv.messages.append((role, text))
        conv.last_message_at = now
        with tenant_connection(self.url, conv.tenant_id) as conn:
            conn.execute(
                """
                INSERT INTO conversation_messages (tenant_id, conversation_id, role, body)
                VALUES (%s, %s, %s, %s)
                """,
                (str(conv.tenant_id), str(conv.id), role, text),
            )

    def save_conversation_state(self, conv: Conversation) -> None:
        from factory_os.domain.memory import maybe_refresh_summary, prefs_from_working_state

        maybe_refresh_summary(conv)
        prefs = prefs_from_working_state(conv.state)
        with tenant_connection(self.url, conv.tenant_id) as conn:
            conn.execute(
                """
                UPDATE conversations
                SET working_state = %s,
                    summary_text = %s,
                    summary_msg_count = %s,
                    outcome = %s,
                    outcome_reason = %s,
                    source_kind = %s,
                    live_code = %s,
                    closed_at = %s
                WHERE id = %s
                """,
                (
                    Json(conv.state.to_json()),
                    conv.summary_text,
                    int(conv.summary_msg_count or 0),
                    conv.outcome,
                    conv.outcome_reason,
                    conv.source_kind,
                    conv.live_code,
                    conv.closed_at,
                    str(conv.id),
                ),
            )
            for key, value in prefs.items():
                conn.execute(
                    """
                    INSERT INTO customer_preferences (tenant_id, customer_id, key, value)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (tenant_id, customer_id, key) DO UPDATE
                      SET value = EXCLUDED.value
                    """,
                    (str(conv.tenant_id), str(conv.customer_id), key, value),
                )

    def get_customer_preferences(self, tenant_id: UUID, customer_id: UUID) -> dict[str, str]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT key, value FROM customer_preferences
                WHERE customer_id = %s
                """,
                (str(customer_id),),
            ).fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}

    def put_customer_preferences(
        self, tenant_id: UUID, customer_id: UUID, prefs: dict[str, str]
    ) -> None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            for key, value in prefs.items():
                if not value:
                    continue
                conn.execute(
                    """
                    INSERT INTO customer_preferences (tenant_id, customer_id, key, value)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (tenant_id, customer_id, key) DO UPDATE
                      SET value = EXCLUDED.value
                    """,
                    (str(tenant_id), str(customer_id), str(key), str(value)),
                )

    def _variant_id(self, conn: psycopg.Connection, variant_sku: str) -> UUID:
        row = conn.execute(
            "SELECT id FROM product_variants WHERE sku = %s", (variant_sku,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown variant {variant_sku}")
        return row["id"]

    def create_order(
        self,
        tenant_id: UUID,
        customer_id: UUID,
        item: OrderItem | None = None,
        *,
        status: str = "open",
        items: list[OrderItem] | None = None,
        discount_amount: Decimal = Decimal("0"),
        hold_minutes: int = 15,
        origin: str = "agent",
        table_label: str = "",
        fulfill_on: date | None = None,
    ) -> Order:
        self.require_tenant(tenant_id)
        from factory_os.domain.learning import new_public_order_number
        from factory_os.domain.models import ORDER_STATUSES

        lines = list(items) if items else ([item] if item is not None else [])
        if not lines:
            raise ValueError("empty_order")
        if status not in ORDER_STATUSES:
            raise ValueError("bad_status")
        origin_clean = (origin or "agent").strip() or "agent"
        if origin_clean not in {"agent", "counter"}:
            raise ValueError("bad_origin")
        label = (table_label or "").strip()
        public_number = new_public_order_number()
        with tenant_connection(self.url, tenant_id) as conn:
            order_row = conn.execute(
                """
                INSERT INTO orders (
                    tenant_id, customer_id, status, public_number, discount_amount,
                    hold_minutes, origin, table_label, fulfill_on
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *
                """,
                (
                    str(tenant_id),
                    str(customer_id),
                    status,
                    public_number,
                    str(discount_amount),
                    int(hold_minutes),
                    origin_clean,
                    label,
                    fulfill_on,
                ),
            ).fetchone()
            for line in lines:
                variant_id = self._variant_id(conn, line.variant_sku)
                conn.execute(
                    """
                    INSERT INTO order_items (
                        tenant_id, order_id, variant_id, name, quantity, unit_price, currency, options
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(tenant_id),
                        str(order_row["id"]),
                        str(variant_id),
                        line.name,
                        line.quantity,
                        str(line.unit_price),
                        line.currency,
                        Json(_stored_options(line)),
                    ),
                )
        return Order(
            id=order_row["id"],
            tenant_id=tenant_id,
            customer_id=customer_id,
            items=lines,
            status=str(order_row.get("status") or "open"),
            public_number=str(order_row.get("public_number") or public_number),
            created_at=order_row.get("created_at"),
            discount_amount=Decimal(str(order_row.get("discount_amount") or discount_amount)),
            hold_minutes=int(order_row.get("hold_minutes") or hold_minutes),
            origin=str(order_row.get("origin") or origin_clean),
            table_label=str(order_row.get("table_label") or label),
            fulfill_on=order_row.get("fulfill_on"),
            stock_applied=bool(order_row.get("stock_applied")),
        )

    def replace_order_items(
        self,
        tenant_id: UUID,
        order_id: UUID,
        items: list[OrderItem],
        *,
        discount_amount: Decimal | None = None,
    ) -> Order:
        self.require_tenant(tenant_id)
        if not items:
            raise ValueError("empty_order")
        with tenant_connection(self.url, tenant_id) as conn:
            exists = conn.execute(
                "SELECT id FROM orders WHERE id = %s", (str(order_id),)
            ).fetchone()
            if exists is None:
                raise KeyError("order")
            conn.execute("DELETE FROM order_items WHERE order_id = %s", (str(order_id),))
            for line in items:
                variant_id = self._variant_id(conn, line.variant_sku)
                conn.execute(
                    """
                    INSERT INTO order_items (
                        tenant_id, order_id, variant_id, name, quantity, unit_price, currency, options
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(tenant_id),
                        str(order_id),
                        str(variant_id),
                        line.name,
                        line.quantity,
                        str(line.unit_price),
                        line.currency,
                        Json(_stored_options(line)),
                    ),
                )
            if discount_amount is not None:
                conn.execute(
                    "UPDATE orders SET discount_amount = %s WHERE id = %s",
                    (str(discount_amount), str(order_id)),
                )
        order = self.get_order(tenant_id, order_id)
        if order is None:
            raise KeyError("order")
        return order

    def delete_order(self, tenant_id: UUID, order_id: UUID) -> None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            conn.execute("DELETE FROM deliveries WHERE order_id = %s", (str(order_id),))
            conn.execute("DELETE FROM payments WHERE order_id = %s", (str(order_id),))
            conn.execute("DELETE FROM order_items WHERE order_id = %s", (str(order_id),))
            conn.execute("DELETE FROM orders WHERE id = %s", (str(order_id),))

    def held_variant_skus(self, tenant_id: UUID) -> set[str]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT sku FROM (
                    SELECT v.sku AS sku
                    FROM orders o
                    JOIN order_items oi ON oi.order_id = o.id
                    JOIN product_variants v ON v.id = oi.variant_id
                    WHERE (
                            o.status = 'reserved'
                            OR (
                                o.status = 'open'
                                AND NOT EXISTS (
                                    SELECT 1 FROM payments p
                                    WHERE p.order_id = o.id AND p.status = 'confirmed'
                                )
                            )
                          )
                      AND COALESCE(o.origin, 'agent') <> 'counter'
                      AND o.fulfill_on IS NULL
                    UNION
                    SELECT variant_sku AS sku
                    FROM payments
                    WHERE order_id IS NULL
                      AND status = 'pending'
                      AND variant_sku IS NOT NULL
                      AND variant_sku <> ''
                    UNION
                    SELECT line->>'variant_sku' AS sku
                    FROM cash_sale_tickets t
                    CROSS JOIN LATERAL jsonb_array_elements(t.lines) AS line
                    WHERE t.status = 'pending_qr'
                      AND COALESCE(line->>'variant_sku', '') <> ''
                ) held
                """
            ).fetchall()
        return {str(row["sku"]) for row in rows}

    def get_order(self, tenant_id: UUID, order_id: UUID) -> Order | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute("SELECT * FROM orders WHERE id = %s", (str(order_id),)).fetchone()
            if row is None:
                return None
            items = conn.execute(
                "SELECT * FROM order_items WHERE order_id = %s", (str(order_id),)
            ).fetchall()
            variant_rows = {
                r["id"]: r["sku"]
                for r in conn.execute("SELECT id, sku FROM product_variants").fetchall()
            }
        return Order(
            id=row["id"],
            tenant_id=row["tenant_id"],
            customer_id=row["customer_id"],
            status=row["status"],
            public_number=row.get("public_number"),
            delivered_at=row.get("delivered_at"),
            delivered_by=row.get("delivered_by"),
            created_at=row.get("created_at"),
            discount_amount=Decimal(str(row.get("discount_amount") or "0")),
            hold_minutes=int(row.get("hold_minutes") or 15),
            origin=str(row.get("origin") or "agent"),
            table_label=str(row.get("table_label") or ""),
            fulfill_on=row.get("fulfill_on"),
            stock_applied=bool(row.get("stock_applied")),
            items=[
                OrderItem(
                    variant_sku=variant_rows.get(item["variant_id"], ""),
                    name=item["name"],
                    quantity=item["quantity"],
                    unit_price=Decimal(str(item["unit_price"])),
                    currency=item["currency"],
                    options=_loaded_options(item.get("options")),
                )
                for item in items
            ],
        )

    def get_order_by_public_number(self, tenant_id: UUID, public_number: str) -> Order | None:
        self.require_tenant(tenant_id)
        needle = (public_number or "").strip().upper()
        if not needle:
            return None
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                "SELECT id FROM orders WHERE upper(public_number) = %s",
                (needle,),
            ).fetchone()
        if row is None:
            return None
        return self.get_order(tenant_id, row["id"])

    def mark_order_delivered(
        self, tenant_id: UUID, order_id: UUID, *, delivered_by: str = "owner"
    ) -> Order:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE orders
                SET delivered_at = now(),
                    delivered_by = %s,
                    status = 'delivered'
                WHERE id = %s
                RETURNING id
                """,
                (delivered_by, str(order_id)),
            ).fetchone()
        if row is None:
            raise KeyError("order")
        order = self.get_order(tenant_id, order_id)
        if order is None:
            raise KeyError("order")
        return order

    def set_order_status(
        self, tenant_id: UUID, order_id: UUID, status: str, *, delivered_by: str = "owner"
    ) -> Order:
        self.require_tenant(tenant_id)
        if status not in {"reserved", "placed", "open", "cancelled", "delivered"}:
            raise ValueError("bad_status")
        with tenant_connection(self.url, tenant_id) as conn:
            if status == "delivered":
                row = conn.execute(
                    """
                    UPDATE orders
                    SET status = 'delivered',
                        delivered_at = COALESCE(delivered_at, now()),
                        delivered_by = COALESCE(delivered_by, %s)
                    WHERE id = %s
                    RETURNING id
                    """,
                    (delivered_by, str(order_id)),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    UPDATE orders
                    SET status = %s, delivered_at = NULL, delivered_by = NULL
                    WHERE id = %s
                    RETURNING id
                    """,
                    (status, str(order_id)),
                ).fetchone()
        if row is None:
            raise KeyError("order")
        order = self.get_order(tenant_id, order_id)
        if order is None:
            raise KeyError("order")
        return order

    def mark_order_stock_applied(self, tenant_id: UUID, order_id: UUID) -> None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE orders SET stock_applied = true
                WHERE id = %s AND tenant_id = %s
                RETURNING id
                """,
                (str(order_id), str(tenant_id)),
            ).fetchone()
        if row is None:
            raise KeyError("order")
        order = self.get_order(tenant_id, order_id)
        if order is not None:
            order.stock_applied = True

    def sold_units_by_sku(self, tenant_id: UUID) -> dict[str, int]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT v.sku AS sku, COALESCE(SUM(oi.quantity), 0) AS qty
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                JOIN payments p ON p.order_id = o.id
                JOIN product_variants v ON v.id = oi.variant_id
                WHERE o.status <> 'cancelled' AND p.status = 'confirmed'
                GROUP BY v.sku
                """
            ).fetchall()
        return {str(row["sku"]): int(row["qty"]) for row in rows}

    def create_payment(
        self,
        tenant_id: UUID,
        order_id: UUID | None,
        provider: str,
        provider_ref: str,
        amount: Decimal,
        currency: str,
        qr_payload: str,
        *,
        variant_sku: str = "",
        customer_id: UUID | None = None,
    ) -> Payment:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO payments (
                    tenant_id, order_id, provider, provider_ref, amount, currency, status, qr_payload,
                    variant_sku, customer_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    str(tenant_id),
                    str(order_id) if order_id else None,
                    provider,
                    provider_ref,
                    str(amount),
                    currency,
                    PaymentStatus.PENDING.value,
                    qr_payload,
                    variant_sku or None,
                    str(customer_id) if customer_id else None,
                ),
            ).fetchone()
        return _row_payment(row)

    def delete_payment(self, tenant_id: UUID, payment_id: UUID) -> None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            conn.execute("DELETE FROM payments WHERE id = %s", (str(payment_id),))

    def payment_status(self, tenant_id: UUID, provider_ref: str) -> Payment | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                "SELECT * FROM payments WHERE provider_ref = %s", (provider_ref,)
            ).fetchone()
        return _row_payment(row) if row else None

    def get_payment(self, tenant_id: UUID, payment_id: UUID) -> Payment | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute("SELECT * FROM payments WHERE id = %s", (str(payment_id),)).fetchone()
        return _row_payment(row) if row else None

    def set_payment_status(
        self,
        tenant_id: UUID,
        payment_id_or_ref: UUID | str,
        status: str,
    ) -> Payment:
        self.require_tenant(tenant_id)
        next_status = PaymentStatus(str(status).strip().lower())
        with tenant_connection(self.url, tenant_id) as conn:
            if isinstance(payment_id_or_ref, UUID):
                row = conn.execute(
                    """
                    UPDATE payments SET status = %s WHERE id = %s
                    RETURNING *
                    """,
                    (next_status.value, str(payment_id_or_ref)),
                ).fetchone()
            else:
                raw = str(payment_id_or_ref).strip()
                row = None
                try:
                    as_id = UUID(raw)
                except ValueError:
                    as_id = None
                if as_id is not None:
                    row = conn.execute(
                        """
                        UPDATE payments SET status = %s WHERE id = %s
                        RETURNING *
                        """,
                        (next_status.value, str(as_id)),
                    ).fetchone()
                if row is None:
                    row = conn.execute(
                        """
                        UPDATE payments SET status = %s WHERE provider_ref = %s
                        RETURNING *
                        """,
                        (next_status.value, raw),
                    ).fetchone()
        if row is None:
            raise ValueError("payment_not_found")
        return _row_payment(row)

    def payment_for_order(self, tenant_id: UUID, order_id: UUID) -> Payment | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                "SELECT * FROM payments WHERE order_id = %s ORDER BY id DESC LIMIT 1",
                (str(order_id),),
            ).fetchone()
        return _row_payment(row) if row else None

    def confirm_from_adapter(self, provider_ref: str) -> None:
        """Confirm one provider reference. Customer text never reaches this.

        Baneco confirms its own ref. Owner cash confirms a payment just created
        with provider ``cash``. Walk-in QR tickets complete without an Order or
        drawer movement; chat payments place the order and mark it sold.
        """
        from factory_os.domain.cash_sales import complete_walkin_qr_if_pending
        from factory_os.domain.ledger import remember_payment

        pending: dict[str, Any] | None = None
        with tenant_connection(self.url, self.tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE payments SET status = %s WHERE provider_ref = %s
                RETURNING id, order_id, variant_sku, customer_id
                """,
                (PaymentStatus.CONFIRMED.value, provider_ref),
            ).fetchone()
            if row is not None:
                pending = dict(row)
        if pending is None:
            return
        confirmed = self.payment_status(self.tenant_id, provider_ref)
        if confirmed is not None and complete_walkin_qr_if_pending(self, confirmed):
            remember_payment(self, confirmed)
            return
        order_id = pending.get("order_id")
        variant_sku = str(pending.get("variant_sku") or "")
        customer_raw = pending.get("customer_id")
        sell_now = False
        if order_id is None and variant_sku and customer_raw:
            record = self.get_variant(self.tenant_id, variant_sku)
            if record is not None:
                order = self.create_order(
                    self.tenant_id,
                    customer_raw if isinstance(customer_raw, UUID) else UUID(str(customer_raw)),
                    OrderItem(
                        variant_sku=record.variant_sku,
                        name=record.name,
                        quantity=1,
                        unit_price=record.price,
                        currency=record.currency,
                    ),
                    status="placed",
                )
                order_id = order.id
                sell_now = True
                with tenant_connection(self.url, self.tenant_id) as conn:
                    conn.execute(
                        "UPDATE payments SET order_id = %s WHERE provider_ref = %s",
                        (str(order_id), provider_ref),
                    )
        if order_id is None:
            if confirmed is not None:
                remember_payment(self, confirmed)
            return
        existing = self.get_order(self.tenant_id, order_id if isinstance(order_id, UUID) else UUID(str(order_id)))
        if existing is not None and existing.status in {"reserved", "open"}:
            self.set_order_status(self.tenant_id, existing.id, "placed")
            sell_now = True
        if sell_now:
            due = existing is not None and getattr(existing, "fulfill_on", None) is not None
            if due:
                from factory_os.domain.future_orders import apply_due_future_orders

                apply_due_future_orders(self, self.tenant_id)
            else:
                with tenant_connection(self.url, self.tenant_id) as conn:
                    items = conn.execute(
                        """
                        SELECT v.sku AS sku, oi.quantity AS quantity
                        FROM order_items oi
                        JOIN product_variants v ON v.id = oi.variant_id
                        WHERE oi.order_id = %s
                        """,
                        (str(order_id),),
                    ).fetchall()
                from factory_os.domain.stock import consume_stock

                for item in items:
                    consume_stock(self, self.tenant_id, str(item["sku"]), int(item["quantity"]))
        confirmed = self.payment_status(self.tenant_id, provider_ref)
        if confirmed is not None:
            remember_payment(self, confirmed)

    def mark_sold_for_confirmed_payments(self) -> None:
        """Re-apply sold after catalog seed. Seed upsert restores JSON stock and drops disabled."""
        with tenant_connection(self.url, self.tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT v.sku AS sku, COALESCE(SUM(oi.quantity), 0) AS sold
                FROM payments p
                JOIN orders o ON o.id = p.order_id
                JOIN order_items oi ON oi.order_id = o.id
                JOIN product_variants v ON v.id = oi.variant_id
                WHERE p.status = 'confirmed' AND o.status <> 'cancelled'
                  AND (o.fulfill_on IS NULL OR o.stock_applied)
                GROUP BY v.sku
                """
            ).fetchall()
        for row in rows:
            record = self.get_variant(self.tenant_id, str(row["sku"]))
            if record is None:
                continue
            remaining = record.stock - int(row["sold"])
            if remaining <= 0:
                self.set_variant_availability(self.tenant_id, record.variant_sku, available=False)
            else:
                self.set_variant_availability(
                    self.tenant_id, record.variant_sku, available=True, stock=remaining
                )

    def record_webhook_event(
        self,
        tenant_id: UUID,
        *,
        event_id: str,
        provider: str,
        provider_ref: str,
        state: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO payment_webhook_events (
                    event_id, tenant_id, provider, provider_ref, state, payload
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
                RETURNING event_id
                """,
                (
                    event_id,
                    str(tenant_id),
                    provider,
                    provider_ref,
                    state,
                    Json(payload or {}),
                ),
            ).fetchone()
        return row is not None

    def update_customer(self, tenant_id: UUID, wa_number: str, name: str | None, address: str | None) -> Customer:
        customer = self.get_or_create_customer(tenant_id, wa_number)
        with tenant_connection(self.url, tenant_id) as conn:
            conn.execute(
                """
                UPDATE customers SET
                    name = COALESCE(%s, name),
                    address = COALESCE(%s, address)
                WHERE id = %s
                RETURNING *
                """,
                (name, address, str(customer.id)),
            )
            row = conn.execute("SELECT * FROM customers WHERE id = %s", (str(customer.id),)).fetchone()
        return Customer(
            id=row["id"],
            tenant_id=row["tenant_id"],
            wa_number=row["wa_number"],
            name=row["name"],
            address=row["address"],
        )

    def create_delivery(self, tenant_id: UUID, order_id: UUID, address: str, recipient_name: str) -> Delivery:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO deliveries (tenant_id, order_id, address, recipient_name)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (str(tenant_id), str(order_id), address, recipient_name),
            ).fetchone()
        return Delivery(
            id=row["id"],
            tenant_id=row["tenant_id"],
            order_id=row["order_id"],
            address=row["address"],
            recipient_name=row["recipient_name"],
        )

    def update_delivery(
        self, tenant_id: UUID, order_id: UUID, address: str, recipient_name: str
    ) -> Delivery:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE deliveries
                SET address = %s, recipient_name = %s
                WHERE id = (
                    SELECT id FROM deliveries
                    WHERE order_id = %s
                    ORDER BY id DESC
                    LIMIT 1
                )
                RETURNING *
                """,
                (address, recipient_name, str(order_id)),
            ).fetchone()
        if row is None:
            raise KeyError("delivery")
        return Delivery(
            id=row["id"],
            tenant_id=row["tenant_id"],
            order_id=row["order_id"],
            address=row["address"],
            recipient_name=row["recipient_name"],
        )

    def delivery_for_order(self, tenant_id: UUID, order_id: UUID) -> Delivery | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                SELECT * FROM deliveries
                WHERE order_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (str(order_id),),
            ).fetchone()
        if row is None:
            return None
        return Delivery(
            id=row["id"],
            tenant_id=row["tenant_id"],
            order_id=row["order_id"],
            address=row["address"],
            recipient_name=row["recipient_name"],
        )

    def adjust_stock(self, tenant_id: UUID, variant_sku: str, delta: int) -> VariantRecord:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            variant_id = self._variant_id(conn, variant_sku)
            row = conn.execute(
                """
                UPDATE inventory SET quantity = quantity + %s
                WHERE variant_id = %s AND tenant_id = %s
                RETURNING quantity
                """,
                (delta, str(variant_id), str(tenant_id)),
            ).fetchone()
            if row is None:
                raise KeyError(variant_sku)
            if int(row["quantity"]) < 0:
                conn.rollback()
                raise ValueError("negative_stock")
        record = self.get_variant(tenant_id, variant_sku)
        if record is None:
            raise KeyError(variant_sku)
        return record

    def put_variant(self, tenant_id: UUID, record: VariantRecord) -> VariantRecord:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            cat = conn.execute(
                """
                INSERT INTO categories (tenant_id, name) VALUES (%s, %s)
                ON CONFLICT (tenant_id, name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                (str(tenant_id), record.category or "general"),
            ).fetchone()
            product = conn.execute(
                """
                INSERT INTO products (tenant_id, sku, name, description, category_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, sku) DO UPDATE
                  SET name = EXCLUDED.name, description = EXCLUDED.description, category_id = EXCLUDED.category_id
                RETURNING id
                """,
                (str(tenant_id), record.product_sku, record.name, record.description, cat["id"]),
            ).fetchone()
            variant = conn.execute(
                """
                INSERT INTO product_variants (tenant_id, product_id, sku, attributes, supplier_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, sku) DO UPDATE
                  SET attributes = EXCLUDED.attributes,
                      supplier_id = COALESCE(EXCLUDED.supplier_id, product_variants.supplier_id)
                RETURNING id
                """,
                (
                    str(tenant_id),
                    product["id"],
                    record.variant_sku,
                    Json(record.attributes),
                    str(record.supplier_id) if record.supplier_id else None,
                ),
            ).fetchone()
            conn.execute(
                "DELETE FROM prices WHERE tenant_id = %s AND variant_id = %s",
                (str(tenant_id), variant["id"]),
            )
            conn.execute(
                """
                INSERT INTO prices (tenant_id, variant_id, amount, currency)
                VALUES (%s, %s, %s, %s)
                """,
                (str(tenant_id), variant["id"], str(record.price), record.currency),
            )
            threshold = max(0, int(getattr(record, "reorder_threshold", 1) or 1))
            exists = conn.execute(
                "SELECT id FROM inventory WHERE tenant_id = %s AND variant_id = %s",
                (str(tenant_id), variant["id"]),
            ).fetchone()
            if exists:
                conn.execute(
                    "UPDATE inventory SET quantity = %s WHERE id = %s",
                    (record.stock, exists["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO inventory (tenant_id, variant_id, quantity, low_stock_threshold)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (str(tenant_id), variant["id"], record.stock, threshold),
                )
            _write_embedding(conn, tenant_id, variant["id"], embed_blob(record))
        return record

    def set_product_image_paths(
        self, tenant_id: UUID, product_sku: str, image_path: str, thumb_path: str
    ) -> int:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE product_variants AS v
                SET attributes = v.attributes || %s::jsonb
                FROM products AS p
                WHERE v.product_id = p.id
                  AND p.sku = %s
                  AND v.tenant_id = %s
                """,
                (
                    Json({"image_path": image_path, "thumb_path": thumb_path}),
                    product_sku,
                    str(tenant_id),
                ),
            )
            count = row.rowcount if row is not None else 0
        if count == 0:
            raise ValueError("unknown_product")
        return int(count)

    def add_media_asset(self, tenant_id: UUID, asset: MediaAsset) -> MediaAsset:
        self.require_tenant(tenant_id)
        if asset.tenant_id != tenant_id:
            raise PermissionError("cross-tenant access denied")
        ref = (asset.provider_ref or "").strip()
        if ref:
            prior = self.get_media_asset_by_provider_ref(tenant_id, ref)
            if prior is not None:
                return prior
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO media_assets (
                    id, tenant_id, kind, mime, size_bytes, storage_key,
                    thumb_key, medium_key, origin, uploaded_by, provider_ref, created_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, now())
                )
                RETURNING *
                """,
                (
                    str(asset.id),
                    str(tenant_id),
                    asset.kind or "image",
                    asset.mime,
                    int(asset.size_bytes),
                    asset.storage_key,
                    asset.thumb_key,
                    asset.medium_key,
                    asset.origin,
                    asset.uploaded_by,
                    asset.provider_ref,
                    asset.created_at,
                ),
            ).fetchone()
        return _row_media_asset(row)

    def get_media_asset(self, tenant_id: UUID, asset_id: UUID) -> MediaAsset | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                SELECT * FROM media_assets
                WHERE id = %s AND tenant_id = %s
                """,
                (str(asset_id), str(tenant_id)),
            ).fetchone()
        return _row_media_asset(row) if row else None

    def get_media_asset_by_provider_ref(
        self, tenant_id: UUID, provider_ref: str
    ) -> MediaAsset | None:
        self.require_tenant(tenant_id)
        ref = (provider_ref or "").strip()
        if not ref:
            return None
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                SELECT * FROM media_assets
                WHERE tenant_id = %s AND provider_ref = %s
                LIMIT 1
                """,
                (str(tenant_id), ref),
            ).fetchone()
        return _row_media_asset(row) if row else None

    def add_conversation_media(
        self, tenant_id: UUID, link: ConversationMedia
    ) -> ConversationMedia:
        self.require_tenant(tenant_id)
        if link.tenant_id != tenant_id:
            raise PermissionError("cross-tenant access denied")
        ref = (link.provider_ref or "").strip()
        if ref:
            prior = self.get_conversation_media_by_provider_ref(tenant_id, ref)
            if prior is not None:
                return prior
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO conversation_media (
                    id, tenant_id, conversation_id, asset_id, provider_ref, message_index,
                    direction, status, kind, mime, filename, size_bytes, error,
                    uploaded_by, created_at, transcript_text, summary_text,
                    enrichment_status, enrichment_error
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, now()),
                    %s, %s, COALESCE(%s, 'none'), %s
                )
                RETURNING *
                """,
                (
                    str(link.id),
                    str(tenant_id),
                    str(link.conversation_id),
                    str(link.asset_id) if link.asset_id else None,
                    link.provider_ref,
                    link.message_index,
                    link.direction,
                    link.status,
                    link.kind,
                    link.mime,
                    link.filename,
                    link.size_bytes,
                    link.error,
                    link.uploaded_by,
                    link.created_at,
                    link.transcript_text,
                    link.summary_text,
                    link.enrichment_status or "none",
                    link.enrichment_error,
                ),
            ).fetchone()
        return _row_conversation_media(row)

    def list_conversation_media(
        self, tenant_id: UUID, conversation_id: UUID
    ) -> list[ConversationMedia]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT * FROM conversation_media
                WHERE conversation_id = %s
                ORDER BY created_at, id
                """,
                (str(conversation_id),),
            ).fetchall()
        return [_row_conversation_media(row) for row in rows]

    def get_conversation_media(
        self, tenant_id: UUID, link_id: UUID
    ) -> ConversationMedia | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                SELECT * FROM conversation_media
                WHERE id = %s
                LIMIT 1
                """,
                (str(link_id),),
            ).fetchone()
        return _row_conversation_media(row) if row else None

    def get_conversation_media_by_provider_ref(
        self, tenant_id: UUID, provider_ref: str
    ) -> ConversationMedia | None:
        self.require_tenant(tenant_id)
        ref = (provider_ref or "").strip()
        if not ref:
            return None
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                SELECT * FROM conversation_media
                WHERE tenant_id = %s AND provider_ref = %s
                LIMIT 1
                """,
                (str(tenant_id), ref),
            ).fetchone()
        return _row_conversation_media(row) if row else None

    def update_conversation_media_enrichment(
        self,
        tenant_id: UUID,
        link_id: UUID,
        *,
        transcript_text: str | None = None,
        summary_text: str | None = None,
        enrichment_status: str,
        enrichment_error: str | None = None,
    ) -> ConversationMedia:
        self.require_tenant(tenant_id)
        status = (enrichment_status or "none").strip().lower()
        if status not in {"none", "pending", "ready", "failed"}:
            raise ValueError("bad_enrichment_status")
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE conversation_media
                SET transcript_text = %s,
                    summary_text = %s,
                    enrichment_status = %s,
                    enrichment_error = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    transcript_text,
                    summary_text,
                    status,
                    enrichment_error,
                    str(link_id),
                ),
            ).fetchone()
        if row is None:
            raise KeyError("conversation_media")
        return _row_conversation_media(row)

    def add_entity_media(self, tenant_id: UUID, link: EntityMedia) -> EntityMedia:
        self.require_tenant(tenant_id)
        if link.tenant_id != tenant_id:
            raise PermissionError("cross-tenant access denied")
        with tenant_connection(self.url, tenant_id) as conn:
            asset = conn.execute(
                "SELECT id FROM media_assets WHERE id = %s",
                (str(link.asset_id),),
            ).fetchone()
            if asset is None:
                raise ValueError("unknown_media")
            row = conn.execute(
                """
                INSERT INTO entity_media (
                    id, tenant_id, entity_type, entity_id, asset_id,
                    filename, kind, mime, size_bytes, note, uploaded_by, created_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, now())
                )
                RETURNING *
                """,
                (
                    str(link.id),
                    str(tenant_id),
                    link.entity_type,
                    str(link.entity_id),
                    str(link.asset_id),
                    link.filename,
                    link.kind,
                    link.mime,
                    int(link.size_bytes),
                    link.note,
                    link.uploaded_by,
                    link.created_at,
                ),
            ).fetchone()
        return _row_entity_media(row)

    def list_entity_media(
        self, tenant_id: UUID, entity_type: str, entity_id: UUID
    ) -> list[EntityMedia]:
        self.require_tenant(tenant_id)
        etype = (entity_type or "").strip().lower()
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT * FROM entity_media
                WHERE tenant_id = %s AND entity_type = %s AND entity_id = %s
                ORDER BY created_at, id
                """,
                (str(tenant_id), etype, str(entity_id)),
            ).fetchall()
        return [_row_entity_media(row) for row in rows]

    def add_product_media(self, tenant_id: UUID, link: ProductMedia) -> ProductMedia:
        self.require_tenant(tenant_id)
        if link.tenant_id != tenant_id:
            raise PermissionError("cross-tenant access denied")
        with tenant_connection(self.url, tenant_id) as conn:
            asset = conn.execute(
                "SELECT id FROM media_assets WHERE id = %s",
                (str(link.asset_id),),
            ).fetchone()
            if asset is None:
                raise ValueError("unknown_media")
            product = conn.execute(
                "SELECT id FROM products WHERE sku = %s",
                (link.product_sku,),
            ).fetchone()
            if product is None:
                raise ValueError("unknown_product")
            existing = conn.execute(
                """
                SELECT COUNT(*) AS n FROM product_media
                WHERE product_sku = %s
                """,
                (link.product_sku,),
            ).fetchone()
            make_primary = bool(link.is_primary) or int(existing["n"] or 0) == 0
            if make_primary:
                conn.execute(
                    """
                    UPDATE product_media
                    SET is_primary = false
                    WHERE product_sku = %s AND is_primary
                    """,
                    (link.product_sku,),
                )
            row = conn.execute(
                """
                INSERT INTO product_media (
                    id, tenant_id, product_sku, asset_id, is_primary, sort_order, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, now()))
                RETURNING *
                """,
                (
                    str(link.id),
                    str(tenant_id),
                    link.product_sku,
                    str(link.asset_id),
                    make_primary,
                    int(link.sort_order),
                    link.created_at,
                ),
            ).fetchone()
        return _row_product_media(row)

    def list_product_media(
        self, tenant_id: UUID, product_sku: str
    ) -> list[ProductMedia]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT * FROM product_media
                WHERE product_sku = %s
                ORDER BY sort_order, created_at, id
                """,
                (product_sku,),
            ).fetchall()
        return [_row_product_media(row) for row in rows]

    def set_category_sort(self, tenant_id: UUID, name: str, sort_order: int) -> None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            conn.execute(
                """
                INSERT INTO categories (tenant_id, name, sort_order)
                VALUES (%s, %s, %s)
                ON CONFLICT (tenant_id, name) DO UPDATE
                  SET sort_order = EXCLUDED.sort_order
                """,
                (str(tenant_id), name, int(sort_order)),
            )

    def category_sort_map(self, tenant_id: UUID) -> dict[str, int]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute("SELECT name, sort_order FROM categories").fetchall()
        return {str(row["name"]): int(row["sort_order"] or 0) for row in rows}

    def create_modifier(
        self,
        tenant_id: UUID,
        *,
        name: str,
        price_delta: Decimal,
        currency: str = "BOB",
    ):
        from factory_os.domain.modifiers import CatalogModifier

        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO catalog_modifiers (tenant_id, name, price_delta, currency)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (str(tenant_id), name, str(price_delta), currency or "BOB"),
            ).fetchone()
        return _modifier_from_row(row)

    def list_modifiers(self, tenant_id: UUID) -> list:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                "SELECT * FROM catalog_modifiers ORDER BY lower(name), id"
            ).fetchall()
        return [_modifier_from_row(row) for row in rows]

    def get_modifier(self, tenant_id: UUID, modifier_id: UUID):
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                "SELECT * FROM catalog_modifiers WHERE id = %s",
                (str(modifier_id),),
            ).fetchone()
        if row is None:
            return None
        return _modifier_from_row(row)

    def disable_variant(self, tenant_id: UUID, variant_sku: str) -> VariantRecord:
        return self.set_variant_availability(tenant_id, variant_sku, available=False)

    def set_variant_availability(
        self,
        tenant_id: UUID,
        variant_sku: str,
        *,
        available: bool,
        stock: int | None = None,
    ) -> VariantRecord:
        self.require_tenant(tenant_id)
        record = self.get_variant(tenant_id, variant_sku)
        if record is None:
            raise KeyError(variant_sku)
        attrs = dict(record.attributes)
        if available:
            attrs.pop("disabled", None)
            if stock is not None:
                if stock < 0:
                    raise ValueError("bad_stock")
                new_stock = stock
            else:
                new_stock = record.stock if record.stock >= 1 else 1
        else:
            attrs["disabled"] = True
            new_stock = 0 if stock is None else max(0, stock)
        with tenant_connection(self.url, tenant_id) as conn:
            conn.execute(
                "UPDATE product_variants SET attributes = %s WHERE tenant_id = %s AND sku = %s",
                (Json(attrs), str(tenant_id), variant_sku),
            )
            variant = conn.execute(
                "SELECT id FROM product_variants WHERE tenant_id = %s AND sku = %s",
                (str(tenant_id), variant_sku),
            ).fetchone()
            if variant is None:
                raise KeyError(variant_sku)
            exists = conn.execute(
                "SELECT id FROM inventory WHERE tenant_id = %s AND variant_id = %s",
                (str(tenant_id), variant["id"]),
            ).fetchone()
            if exists:
                conn.execute(
                    "UPDATE inventory SET quantity = %s WHERE id = %s",
                    (new_stock, exists["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO inventory (tenant_id, variant_id, quantity, low_stock_threshold)
                    VALUES (%s, %s, %s, 1)
                    """,
                    (str(tenant_id), variant["id"], new_stock),
                )
        updated = self.get_variant(tenant_id, variant_sku)
        if updated is None:
            raise KeyError(variant_sku)
        return updated

    def list_orders(self, tenant_id: UUID) -> list[Order]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute("SELECT id FROM orders").fetchall()
        orders: list[Order] = []
        for row in rows:
            order = self.get_order(tenant_id, row["id"])
            if order is not None:
                orders.append(order)
        return orders

    def list_payments(self, tenant_id: UUID) -> list[Payment]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute("SELECT * FROM payments").fetchall()
        return [_row_payment(row) for row in rows]

    def get_open_cash_session(self, tenant_id: UUID) -> CashSession | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                "SELECT * FROM cash_sessions WHERE status = 'open' LIMIT 1"
            ).fetchone()
        return _row_cash_session(row) if row else None

    def list_cash_sessions(self, tenant_id: UUID, *, status: str | None = None) -> list[CashSession]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            if status is None:
                rows = conn.execute(
                    """
                    SELECT * FROM cash_sessions
                    ORDER BY COALESCE(closed_at, opened_at) DESC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM cash_sessions
                    WHERE status = %s
                    ORDER BY COALESCE(closed_at, opened_at) DESC
                    """,
                    (status,),
                ).fetchall()
        return [_row_cash_session(row) for row in rows]

    def open_cash_session(
        self,
        tenant_id: UUID,
        opening_float: Decimal,
        currency: str,
        opened_by_name: str,
        opened_by_id: UUID | None = None,
    ) -> CashSession:
        self.require_tenant(tenant_id)
        if opening_float < 0:
            raise ValueError("bad_amount")
        with tenant_connection(self.url, tenant_id) as conn:
            existing = conn.execute(
                "SELECT id FROM cash_sessions WHERE status = 'open' LIMIT 1"
            ).fetchone()
            if existing is not None:
                raise ValueError("session_open")
            row = conn.execute(
                """
                INSERT INTO cash_sessions (
                    tenant_id, status, opening_float, currency, opened_by_name, opened_by_id
                )
                VALUES (%s, 'open', %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    str(tenant_id),
                    str(opening_float),
                    currency or "BOB",
                    opened_by_name,
                    str(opened_by_id) if opened_by_id else None,
                ),
            ).fetchone()
        return _row_cash_session(row)

    def close_cash_session(
        self,
        tenant_id: UUID,
        *,
        counted_cash: Decimal,
        expected_cash: Decimal,
        difference: Decimal,
        note: str,
        closed_by_name: str,
        closed_by_id: UUID | None = None,
    ) -> CashSession:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE cash_sessions
                SET status = 'closed',
                    counted_cash = %s,
                    expected_cash = %s,
                    difference = %s,
                    close_note = %s,
                    closed_by_name = %s,
                    closed_by_id = %s,
                    closed_at = now()
                WHERE status = 'open'
                RETURNING *
                """,
                (
                    str(counted_cash),
                    str(expected_cash),
                    str(difference),
                    note,
                    closed_by_name,
                    str(closed_by_id) if closed_by_id else None,
                ),
            ).fetchone()
        if row is None:
            raise ValueError("session_required")
        return _row_cash_session(row)

    def reopen_cash_session(
        self,
        tenant_id: UUID,
        *,
        reopened_by_name: str,
        reopened_by_id: UUID | None = None,
    ) -> CashSession:
        self.require_tenant(tenant_id)
        _ = reopened_by_name, reopened_by_id
        with tenant_connection(self.url, tenant_id) as conn:
            open_row = conn.execute(
                "SELECT id FROM cash_sessions WHERE status = 'open' LIMIT 1"
            ).fetchone()
            if open_row is not None:
                raise ValueError("session_open")
            row = conn.execute(
                """
                UPDATE cash_sessions
                SET status = 'open',
                    closed_at = NULL,
                    closed_by_name = NULL,
                    closed_by_id = NULL,
                    counted_cash = NULL,
                    expected_cash = NULL,
                    difference = NULL,
                    close_note = NULL
                WHERE id = (
                    SELECT id FROM cash_sessions
                    WHERE status = 'closed'
                    ORDER BY COALESCE(closed_at, opened_at) DESC
                    LIMIT 1
                )
                RETURNING *
                """
            ).fetchone()
        if row is None:
            raise ValueError("session_required")
        return _row_cash_session(row)

    def record_cash(
        self,
        tenant_id: UUID,
        direction: str,
        amount: Decimal,
        currency: str,
        reason: str,
        *,
        category: str = "",
        method: str = "cash",
        recorded_by_name: str = "sistema",
        recorded_by_id: UUID | None = None,
        ticket_id: UUID | None = None,
    ) -> CashMovement:
        self.require_tenant(tenant_id)
        if direction not in {"in", "out"}:
            raise ValueError("bad_direction")
        if amount <= 0:
            raise ValueError("bad_amount")
        method_clean = (method or "cash").strip() or "cash"
        actor_name = (recorded_by_name or "sistema").strip() or "sistema"
        with tenant_connection(self.url, tenant_id) as conn:
            session = conn.execute(
                "SELECT id FROM cash_sessions WHERE status = 'open' LIMIT 1"
            ).fetchone()
            if session is None:
                raise ValueError("session_required")
            row = conn.execute(
                """
                INSERT INTO cash_movements (
                    tenant_id, direction, amount, currency, reason, session_id,
                    category, method, status, recorded_by_name, recorded_by_id, ticket_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'recorded', %s, %s, %s)
                RETURNING *
                """,
                (
                    str(tenant_id),
                    direction,
                    str(amount),
                    currency or "BOB",
                    reason,
                    str(session["id"]),
                    category or "",
                    method_clean,
                    actor_name,
                    str(recorded_by_id) if recorded_by_id else None,
                    str(ticket_id) if ticket_id else None,
                ),
            ).fetchone()
        movement = _row_cash_movement(row)
        from factory_os.domain.ledger import remember_cash

        remember_cash(self, movement)
        return movement

    def create_cash_sale_ticket(self, tenant_id: UUID, ticket: CashSaleTicket) -> CashSaleTicket:
        from factory_os.domain.cash_sales import lines_as_json

        self.require_tenant(tenant_id)
        if ticket.tenant_id != tenant_id:
            raise PermissionError("cross-tenant access denied")
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO cash_sale_tickets (
                    id, tenant_id, number, status, method, total, currency, lines,
                    session_id, movement_id, payment_id, provider_ref,
                    recorded_by_name, recorded_by_id, created_at, order_id, discount_amount
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, COALESCE(%s, now()), %s, %s
                )
                RETURNING *
                """,
                (
                    str(ticket.id),
                    str(tenant_id),
                    ticket.number,
                    ticket.status or "recorded",
                    ticket.method or "cash",
                    str(ticket.total),
                    ticket.currency or "BOB",
                    Json(lines_as_json(ticket.lines)),
                    str(ticket.session_id) if ticket.session_id else None,
                    str(ticket.movement_id) if ticket.movement_id else None,
                    str(ticket.payment_id) if ticket.payment_id else None,
                    ticket.provider_ref,
                    ticket.recorded_by_name or "sistema",
                    str(ticket.recorded_by_id) if ticket.recorded_by_id else None,
                    ticket.created_at,
                    str(ticket.order_id) if ticket.order_id else None,
                    str(ticket.discount_amount),
                ),
            ).fetchone()
        return _row_cash_sale_ticket(row)

    def set_cash_sale_movement(
        self, tenant_id: UUID, ticket_id: UUID, movement_id: UUID
    ) -> CashSaleTicket:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE cash_sale_tickets
                SET movement_id = %s
                WHERE id = %s
                RETURNING *
                """,
                (str(movement_id), str(ticket_id)),
            ).fetchone()
        if row is None:
            raise ValueError("ticket_not_found")
        return _row_cash_sale_ticket(row)

    def link_cash_sale_payment(
        self,
        tenant_id: UUID,
        ticket_id: UUID,
        payment_id: UUID,
        provider_ref: str,
    ) -> CashSaleTicket:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE cash_sale_tickets
                SET payment_id = %s, provider_ref = %s
                WHERE id = %s
                RETURNING *
                """,
                (str(payment_id), (provider_ref or "").strip() or None, str(ticket_id)),
            ).fetchone()
        if row is None:
            raise ValueError("ticket_not_found")
        return _row_cash_sale_ticket(row)

    def cash_sale_ticket_for_payment(
        self, tenant_id: UUID, payment_id: UUID
    ) -> CashSaleTicket | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                "SELECT * FROM cash_sale_tickets WHERE payment_id = %s",
                (str(payment_id),),
            ).fetchone()
        if row is None:
            return None
        return _row_cash_sale_ticket(row)

    def set_cash_sale_status(
        self, tenant_id: UUID, ticket_id: UUID, status: str
    ) -> CashSaleTicket:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE cash_sale_tickets
                SET status = %s
                WHERE id = %s
                RETURNING *
                """,
                (status, str(ticket_id)),
            ).fetchone()
        if row is None:
            raise ValueError("ticket_not_found")
        return _row_cash_sale_ticket(row)

    def get_cash_sale_ticket(self, tenant_id: UUID, ticket_id: UUID) -> CashSaleTicket | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                "SELECT * FROM cash_sale_tickets WHERE id = %s",
                (str(ticket_id),),
            ).fetchone()
        if row is None:
            return None
        return _row_cash_sale_ticket(row)

    def list_cash_sale_tickets(
        self, tenant_id: UUID, session_id: UUID | None = None
    ) -> list[CashSaleTicket]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            if session_id is None:
                rows = conn.execute(
                    """
                    SELECT * FROM cash_sale_tickets
                    ORDER BY created_at DESC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM cash_sale_tickets
                    WHERE session_id = %s
                    ORDER BY created_at DESC
                    """,
                    (str(session_id),),
                ).fetchall()
        return [_row_cash_sale_ticket(row) for row in rows]

    def void_cash(
        self,
        tenant_id: UUID,
        movement_id: UUID,
        reason: str,
        voided_by_name: str,
        voided_by_id: UUID | None = None,
    ) -> CashMovement:
        from factory_os.domain.ledger import void_cash_ledger

        self.require_tenant(tenant_id)
        reason_clean = (reason or "").strip()
        if not reason_clean:
            raise ValueError("void_reason_required")
        actor_name = (voided_by_name or "").strip() or "sistema"
        with tenant_connection(self.url, tenant_id) as conn:
            existing = conn.execute(
                "SELECT * FROM cash_movements WHERE id = %s",
                (str(movement_id),),
            ).fetchone()
            if existing is None:
                raise ValueError("movement_not_found")
            if (existing.get("status") or "recorded") == "voided":
                raise ValueError("already_voided")
            row = conn.execute(
                """
                UPDATE cash_movements
                SET status = 'voided',
                    void_reason = %s,
                    voided_by_name = %s,
                    voided_by_id = %s,
                    voided_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (
                    reason_clean,
                    actor_name,
                    str(voided_by_id) if voided_by_id else None,
                    str(movement_id),
                ),
            ).fetchone()
        movement = _row_cash_movement(row)
        void_cash_ledger(self, movement)
        return movement

    def list_cash(self, tenant_id: UUID, session_id: UUID | None = None) -> list[CashMovement]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            if session_id is None:
                rows = conn.execute(
                    "SELECT * FROM cash_movements ORDER BY created_at"
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM cash_movements
                    WHERE session_id = %s
                    ORDER BY created_at
                    """,
                    (str(session_id),),
                ).fetchall()
        return [_row_cash_movement(row) for row in rows]

    def get_cash_movement(self, tenant_id: UUID, movement_id: UUID) -> CashMovement | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                "SELECT * FROM cash_movements WHERE id = %s",
                (str(movement_id),),
            ).fetchone()
        return _row_cash_movement(row) if row else None

    def list_cash_attachments(
        self, tenant_id: UUID, movement_id: UUID
    ) -> list[CashAttachment]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT * FROM cash_attachments
                WHERE movement_id = %s
                ORDER BY created_at DESC
                """,
                (str(movement_id),),
            ).fetchall()
        return [_row_cash_attachment(row) for row in rows]

    def add_cash_attachment(
        self, tenant_id: UUID, attachment: CashAttachment
    ) -> CashAttachment:
        self.require_tenant(tenant_id)
        if attachment.tenant_id != tenant_id:
            raise PermissionError("cross-tenant access denied")
        with tenant_connection(self.url, tenant_id) as conn:
            existing = conn.execute(
                "SELECT id FROM cash_movements WHERE id = %s",
                (str(attachment.movement_id),),
            ).fetchone()
            if existing is None:
                raise ValueError("movement_not_found")
            row = conn.execute(
                """
                INSERT INTO cash_attachments (
                    id, tenant_id, movement_id, filename, content_type,
                    size_bytes, storage_key, uploaded_by_name, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, now()))
                RETURNING *
                """,
                (
                    str(attachment.id),
                    str(tenant_id),
                    str(attachment.movement_id),
                    attachment.filename,
                    attachment.content_type or "application/octet-stream",
                    int(attachment.size_bytes),
                    attachment.storage_key,
                    (attachment.uploaded_by_name or "sistema").strip() or "sistema",
                    attachment.created_at,
                ),
            ).fetchone()
        return _row_cash_attachment(row)

    def add_ledger_entry(
        self,
        tenant_id: UUID,
        source: str,
        source_id: UUID,
        direction: str,
        amount: Decimal,
        currency: str,
        *,
        status: str = "recorded",
    ) -> LedgerEntry:
        self.require_tenant(tenant_id)
        if source not in {"payment", "cash", "purchase"} or direction not in {"in", "out"}:
            raise ValueError("bad_ledger")
        if amount <= 0:
            raise ValueError("bad_amount")
        status_clean = (status or "recorded").strip() or "recorded"
        if status_clean not in {"recorded", "voided"}:
            raise ValueError("bad_ledger_status")
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO ledger_entries
                    (tenant_id, source, source_id, direction, amount, currency, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, source, source_id) DO NOTHING
                RETURNING id, tenant_id, source, source_id, direction, amount, currency, created_at, status
                """,
                (
                    str(tenant_id),
                    source,
                    str(source_id),
                    direction,
                    str(amount),
                    currency or "BOB",
                    status_clean,
                ),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    """
                    SELECT id, tenant_id, source, source_id, direction, amount, currency, created_at, status
                    FROM ledger_entries
                    WHERE source = %s AND source_id = %s
                    """,
                    (source, str(source_id)),
                ).fetchone()
        return _row_ledger(row)

    def set_ledger_entry_status(
        self, tenant_id: UUID, source: str, source_id: UUID, status: str
    ) -> LedgerEntry:
        self.require_tenant(tenant_id)
        status_clean = (status or "").strip()
        if status_clean not in {"recorded", "voided"}:
            raise ValueError("bad_ledger_status")
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE ledger_entries
                SET status = %s
                WHERE source = %s AND source_id = %s
                RETURNING id, tenant_id, source, source_id, direction, amount, currency, created_at, status
                """,
                (status_clean, source, str(source_id)),
            ).fetchone()
        if row is None:
            raise ValueError("ledger_entry_not_found")
        return _row_ledger(row)

    def list_ledger(self, tenant_id: UUID) -> list[LedgerEntry]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT id, tenant_id, source, source_id, direction, amount, currency, created_at, status
                FROM ledger_entries
                ORDER BY created_at
                """
            ).fetchall()
        return [_row_ledger(row) for row in rows]

    def list_chart_accounts(self, tenant_id: UUID) -> list[ChartAccount]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT id, tenant_id, code, name, account_type, is_system, active, created_at
                FROM chart_accounts
                ORDER BY code
                """
            ).fetchall()
        return [_row_chart_account(row) for row in rows]

    def upsert_chart_account(
        self,
        tenant_id: UUID,
        *,
        code: str,
        name: str,
        account_type: str,
        is_system: bool = True,
        active: bool = True,
        account_id: UUID | None = None,
    ) -> ChartAccount:
        from factory_os.domain.chart_accounts import ACCOUNT_TYPES

        self.require_tenant(tenant_id)
        code_clean = (code or "").strip()
        name_clean = (name or "").strip()
        type_clean = (account_type or "").strip()
        if not code_clean or not name_clean or type_clean not in ACCOUNT_TYPES:
            raise ValueError("bad_chart_account")
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO chart_accounts (
                    id, tenant_id, code, name, account_type, is_system, active
                )
                VALUES (COALESCE(%s, gen_random_uuid()), %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, code) DO UPDATE SET
                    name = EXCLUDED.name,
                    account_type = EXCLUDED.account_type,
                    is_system = EXCLUDED.is_system,
                    active = EXCLUDED.active
                RETURNING id, tenant_id, code, name, account_type, is_system, active, created_at
                """,
                (
                    str(account_id) if account_id else None,
                    str(tenant_id),
                    code_clean,
                    name_clean,
                    type_clean,
                    bool(is_system),
                    bool(active),
                ),
            ).fetchone()
        return _row_chart_account(row)

    def ensure_chart_accounts(self, tenant_id: UUID) -> list[ChartAccount]:
        from factory_os.domain.chart_accounts import SEED_ACCOUNTS

        self.require_tenant(tenant_id)
        for seed in SEED_ACCOUNTS:
            self.upsert_chart_account(
                tenant_id,
                code=seed["code"],
                name=seed["name"],
                account_type=seed["account_type"],
                is_system=True,
                active=True,
            )
        return self.list_chart_accounts(tenant_id)

    def list_journal_lines(self, tenant_id: UUID, entry_id: UUID) -> list[JournalLine]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT jl.id, jl.tenant_id, jl.entry_id, jl.account_id, jl.direction,
                       jl.amount, jl.currency, ca.code AS account_code
                FROM journal_lines jl
                JOIN chart_accounts ca ON ca.id = jl.account_id
                WHERE jl.entry_id = %s
                ORDER BY jl.direction, ca.code
                """,
                (str(entry_id),),
            ).fetchall()
        return [_row_journal_line(row) for row in rows]

    def get_journal_by_origin(
        self, tenant_id: UUID, origin_source: str, origin_id: UUID, kind: str
    ) -> JournalEntry | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                SELECT id, tenant_id, entry_at, origin_source, origin_id, kind,
                       memo, reverses_entry_id, created_at
                FROM journal_entries
                WHERE origin_source = %s AND origin_id = %s AND kind = %s
                """,
                (origin_source, str(origin_id), kind),
            ).fetchone()
        if row is None:
            return None
        return _row_journal_entry(row, self.list_journal_lines(tenant_id, row["id"]))

    def list_journal_entries(self, tenant_id: UUID) -> list[JournalEntry]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT id, tenant_id, entry_at, origin_source, origin_id, kind,
                       memo, reverses_entry_id, created_at
                FROM journal_entries
                ORDER BY entry_at, created_at
                """
            ).fetchall()
        return [
            _row_journal_entry(row, self.list_journal_lines(tenant_id, row["id"]))
            for row in rows
        ]

    def add_journal_entry(
        self,
        tenant_id: UUID,
        *,
        entry_at: Any,
        origin_source: str,
        origin_id: UUID,
        kind: str,
        memo: str,
        lines: list[dict[str, Any]],
        reverses_entry_id: UUID | None = None,
    ) -> JournalEntry:
        from datetime import UTC, datetime

        from factory_os.domain.accounting_periods import assert_period_open_for_entry
        from factory_os.domain.journal import (
            JOURNAL_KINDS,
            LINE_DIRECTIONS,
            ORIGIN_SOURCES,
            assert_journal_balanced,
        )

        self.require_tenant(tenant_id)
        source = (origin_source or "").strip()
        kind_clean = (kind or "").strip()
        if source not in ORIGIN_SOURCES or kind_clean not in JOURNAL_KINDS:
            raise ValueError("bad_journal")
        existing = self.get_journal_by_origin(tenant_id, source, origin_id, kind_clean)
        if existing is not None:
            return existing
        if not lines:
            raise ValueError("journal_needs_two_lines")
        for line in lines:
            direction = str(line.get("direction") or "").strip()
            amount = Decimal(str(line.get("amount")))
            if direction not in LINE_DIRECTIONS or amount <= 0:
                raise ValueError("bad_journal_line")
        assert_journal_balanced(lines)
        when = entry_at or datetime.now(UTC)
        assert_period_open_for_entry(self, tenant_id, when)
        entry_id = uuid4()
        with tenant_connection(self.url, tenant_id) as conn:
            accounts_by_code = {
                row["code"]: row["id"]
                for row in conn.execute(
                    "SELECT id, code FROM chart_accounts WHERE active = true"
                ).fetchall()
            }
            accounts_by_id = {
                row["id"]: row["code"]
                for row in conn.execute("SELECT id, code FROM chart_accounts").fetchall()
            }
            resolved: list[tuple[UUID, str, Decimal, str]] = []
            for line in lines:
                account_id = line.get("account_id")
                account_code = (line.get("account_code") or "").strip()
                if account_id is not None:
                    aid = account_id if isinstance(account_id, UUID) else UUID(str(account_id))
                    if aid not in accounts_by_id:
                        raise ValueError("account_not_found")
                elif account_code:
                    if account_code not in accounts_by_code:
                        raise ValueError("account_not_found")
                    aid = accounts_by_code[account_code]
                else:
                    raise ValueError("account_required")
                resolved.append(
                    (
                        aid,
                        str(line["direction"]).strip(),
                        Decimal(str(line["amount"])),
                        (str(line.get("currency") or "BOB").strip() or "BOB"),
                    )
                )
            row = conn.execute(
                """
                INSERT INTO journal_entries (
                    id, tenant_id, entry_at, origin_source, origin_id, kind, memo, reverses_entry_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, origin_source, origin_id, kind) DO NOTHING
                RETURNING id, tenant_id, entry_at, origin_source, origin_id, kind,
                          memo, reverses_entry_id, created_at
                """,
                (
                    str(entry_id),
                    str(tenant_id),
                    when,
                    source,
                    str(origin_id),
                    kind_clean,
                    (memo or "").strip(),
                    str(reverses_entry_id) if reverses_entry_id else None,
                ),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    """
                    SELECT id, tenant_id, entry_at, origin_source, origin_id, kind,
                           memo, reverses_entry_id, created_at
                    FROM journal_entries
                    WHERE origin_source = %s AND origin_id = %s AND kind = %s
                    """,
                    (source, str(origin_id), kind_clean),
                ).fetchone()
                return _row_journal_entry(
                    row, self.list_journal_lines(tenant_id, row["id"])
                )
            for account_id, direction, amount, currency in resolved:
                conn.execute(
                    """
                    INSERT INTO journal_lines (
                        tenant_id, entry_id, account_id, direction, amount, currency
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(tenant_id),
                        str(row["id"]),
                        str(account_id),
                        direction,
                        str(amount),
                        currency,
                    ),
                )
        return _row_journal_entry(row, self.list_journal_lines(tenant_id, row["id"]))

    def list_accounting_periods(self, tenant_id: UUID) -> list[AccountingPeriod]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT id, tenant_id, date_from, date_to, status, closed_at, closed_by_name
                FROM accounting_periods
                ORDER BY date_from, date_to
                """
            ).fetchall()
        return [_row_accounting_period(row) for row in rows]

    def get_accounting_period(
        self, tenant_id: UUID, *, date_from: Any, date_to: Any
    ) -> AccountingPeriod | None:
        from datetime import date as date_cls

        self.require_tenant(tenant_id)
        start = date_from if isinstance(date_from, date_cls) else date_cls.fromisoformat(str(date_from)[:10])
        end = date_to if isinstance(date_to, date_cls) else date_cls.fromisoformat(str(date_to)[:10])
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                SELECT id, tenant_id, date_from, date_to, status, closed_at, closed_by_name
                FROM accounting_periods
                WHERE date_from = %s AND date_to = %s
                """,
                (start, end),
            ).fetchone()
        return _row_accounting_period(row) if row else None

    def close_accounting_period(
        self,
        tenant_id: UUID,
        *,
        date_from: Any,
        date_to: Any,
        closed_by_name: str = "",
    ) -> AccountingPeriod:
        from datetime import UTC, date as date_cls, datetime

        self.require_tenant(tenant_id)
        start = date_from if isinstance(date_from, date_cls) else date_cls.fromisoformat(str(date_from)[:10])
        end = date_to if isinstance(date_to, date_cls) else date_cls.fromisoformat(str(date_to)[:10])
        if start > end:
            raise ValueError("bad_period_range")
        name = (closed_by_name or "").strip() or None
        now = datetime.now(UTC)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO accounting_periods (
                    tenant_id, date_from, date_to, status, closed_at, closed_by_name
                )
                VALUES (%s, %s, %s, 'closed', %s, %s)
                ON CONFLICT (tenant_id, date_from, date_to) DO UPDATE
                SET status = 'closed',
                    closed_at = EXCLUDED.closed_at,
                    closed_by_name = COALESCE(EXCLUDED.closed_by_name, accounting_periods.closed_by_name)
                RETURNING id, tenant_id, date_from, date_to, status, closed_at, closed_by_name
                """,
                (str(tenant_id), start, end, now, name),
            ).fetchone()
        return _row_accounting_period(row)

    def reopen_accounting_period(
        self, tenant_id: UUID, *, date_from: Any, date_to: Any
    ) -> AccountingPeriod:
        from datetime import date as date_cls

        self.require_tenant(tenant_id)
        start = date_from if isinstance(date_from, date_cls) else date_cls.fromisoformat(str(date_from)[:10])
        end = date_to if isinstance(date_to, date_cls) else date_cls.fromisoformat(str(date_to)[:10])
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE accounting_periods
                SET status = 'open', closed_at = NULL, closed_by_name = NULL
                WHERE date_from = %s AND date_to = %s
                RETURNING id, tenant_id, date_from, date_to, status, closed_at, closed_by_name
                """,
                (start, end),
            ).fetchone()
        if row is None:
            raise ValueError("period_not_found")
        return _row_accounting_period(row)

    def list_purchases(self, tenant_id: UUID) -> list[PurchaseReceipt]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT id, tenant_id, variant_sku, quantity, unit_cost, currency, created_at,
                       COALESCE(payment_method, 'cash') AS payment_method,
                       supplier_id,
                       COALESCE(received_at, created_at) AS received_at,
                       purchase_order_id
                FROM purchase_receipts
                ORDER BY created_at ASC
                """
            ).fetchall()
        return [_row_purchase(row) for row in rows]

    def receive_purchase(
        self,
        tenant_id: UUID,
        variant_sku: str,
        quantity: int,
        unit_cost: Decimal,
        currency: str = "BOB",
        payment_method: str = "cash",
        supplier_id: UUID | None = None,
        received_at: Any = None,
        purchase_order_id: UUID | None = None,
    ) -> PurchaseReceipt:
        from datetime import UTC, datetime

        from factory_os.domain.ledger import remember_purchase

        self.require_tenant(tenant_id)
        if quantity < 1 or unit_cost <= 0:
            raise ValueError("bad_purchase")
        method = (payment_method or "cash").strip().lower() or "cash"
        if method not in {"cash", "credit"}:
            raise ValueError("bad_payment_method")
        resolved_order: UUID | None = None
        if purchase_order_id is not None:
            linked = self.get_purchase_order(tenant_id, purchase_order_id)
            if linked is None:
                raise KeyError(purchase_order_id)
            resolved_order = linked.id
        resolved_supplier: UUID | None = None
        if supplier_id is not None:
            supplier = self.get_supplier(tenant_id, supplier_id)
            if supplier is None:
                raise KeyError(supplier_id)
            resolved_supplier = supplier.id
        when = received_at if isinstance(received_at, datetime) else datetime.now(UTC)
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        self.adjust_stock(tenant_id, variant_sku, quantity)
        if resolved_supplier is not None:
            record = self.get_variant(tenant_id, variant_sku)
            if record is not None and getattr(record, "supplier_id", None) is None:
                self.set_variant_supplier(tenant_id, variant_sku, resolved_supplier)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO purchase_receipts (
                    tenant_id, variant_sku, quantity, unit_cost, currency, payment_method,
                    supplier_id, received_at, purchase_order_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, tenant_id, variant_sku, quantity, unit_cost, currency, created_at,
                          payment_method, supplier_id, received_at, purchase_order_id
                """,
                (
                    str(tenant_id),
                    variant_sku,
                    quantity,
                    str(unit_cost),
                    currency or "BOB",
                    method,
                    str(resolved_supplier) if resolved_supplier is not None else None,
                    when,
                    str(resolved_order) if resolved_order is not None else None,
                ),
            ).fetchone()
        receipt = _row_purchase(row)
        remember_purchase(self, receipt)
        return receipt

    def add_invoice_document(
        self, tenant_id: UUID, order_id: UUID, amount: Decimal, currency: str
    ) -> InvoiceDocument:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                INSERT INTO invoice_documents (tenant_id, order_id, status, amount, currency)
                VALUES (%s, %s, 'draft', %s, %s)
                RETURNING id, tenant_id, order_id, status, amount, currency, external_ref, created_at
                """,
                (str(tenant_id), str(order_id), str(amount), currency or "BOB"),
            ).fetchone()
        return _row_invoice(row)

    def set_invoice_status(
        self, tenant_id: UUID, document_id: UUID, status: str, external_ref: str
    ) -> InvoiceDocument:
        self.require_tenant(tenant_id)
        if status not in {"draft", "exported", "issued", "failed"}:
            raise ValueError("bad_invoice_status")
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                UPDATE invoice_documents
                SET status = %s, external_ref = %s
                WHERE id = %s
                RETURNING id, tenant_id, order_id, status, amount, currency, external_ref, created_at
                """,
                (status, external_ref, str(document_id)),
            ).fetchone()
        if row is None:
            raise KeyError(document_id)
        return _row_invoice(row)

    def list_invoices(self, tenant_id: UUID) -> list[InvoiceDocument]:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            rows = conn.execute(
                """
                SELECT id, tenant_id, order_id, status, amount, currency, external_ref, created_at
                FROM invoice_documents
                ORDER BY created_at
                """
            ).fetchall()
        return [_row_invoice(row) for row in rows]

    def get_shop_knowledge(self, tenant_id: UUID) -> dict[str, Any] | None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute("SELECT payload FROM shop_knowledge").fetchone()
        if row is None:
            return None
        payload = row["payload"]
        return dict(payload) if isinstance(payload, dict) else None

    def put_shop_knowledge(self, tenant_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        from factory_os.domain.knowledge import merge_shop_pack, sanitize_shop_pack

        self.require_tenant(tenant_id)
        current = self.get_shop_knowledge(tenant_id)
        stored = merge_shop_pack(current, sanitize_shop_pack(payload))
        with tenant_connection(self.url, tenant_id) as conn:
            conn.execute(
                """
                INSERT INTO shop_knowledge (tenant_id, payload, updated_at)
                VALUES (%s, %s, now())
                ON CONFLICT (tenant_id) DO UPDATE
                  SET payload = EXCLUDED.payload, updated_at = now()
                """,
                (str(tenant_id), Json(stored)),
            )
        return stored

    def get_analytics_thresholds(self, tenant_id: UUID):
        from factory_os.domain.analytics_thresholds import AnalyticsThresholds

        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                """
                SELECT qr_pending_hours, inactive_days, digest_whatsapp_enabled
                FROM analytics_thresholds
                """
            ).fetchone()
        if row is None:
            return AnalyticsThresholds()
        return AnalyticsThresholds(
            qr_pending_hours=int(row["qr_pending_hours"]),
            inactive_days=int(row["inactive_days"]),
            digest_whatsapp_enabled=bool(row["digest_whatsapp_enabled"]),
        )

    def put_analytics_thresholds(self, tenant_id: UUID, thresholds):
        from factory_os.domain.analytics_thresholds import AnalyticsThresholds

        self.require_tenant(tenant_id)
        if not isinstance(thresholds, AnalyticsThresholds):
            raise ValueError("bad_thresholds")
        with tenant_connection(self.url, tenant_id) as conn:
            conn.execute(
                """
                INSERT INTO analytics_thresholds (
                    tenant_id, qr_pending_hours, inactive_days,
                    digest_whatsapp_enabled, updated_at
                )
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (tenant_id) DO UPDATE
                  SET qr_pending_hours = EXCLUDED.qr_pending_hours,
                      inactive_days = EXCLUDED.inactive_days,
                      digest_whatsapp_enabled = EXCLUDED.digest_whatsapp_enabled,
                      updated_at = now()
                """,
                (
                    str(tenant_id),
                    thresholds.qr_pending_hours,
                    thresholds.inactive_days,
                    thresholds.digest_whatsapp_enabled,
                ),
            )
        return thresholds

    def analytics_digest_sent(self, tenant_id: UUID, business_date: date) -> bool:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            row = conn.execute(
                "SELECT 1 FROM analytics_owner_digest_log WHERE business_date = %s",
                (business_date,),
            ).fetchone()
        return row is not None

    def record_analytics_digest(
        self,
        tenant_id: UUID,
        business_date: date,
        alert_type_count: int,
        sent_at: datetime,
    ) -> None:
        self.require_tenant(tenant_id)
        with tenant_connection(self.url, tenant_id) as conn:
            conn.execute(
                """
                INSERT INTO analytics_owner_digest_log (
                    tenant_id, business_date, sent_at, alert_type_count
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, business_date) DO UPDATE
                  SET sent_at = EXCLUDED.sent_at,
                      alert_type_count = EXCLUDED.alert_type_count
                """,
                (str(tenant_id), business_date, sent_at, int(alert_type_count)),
            )


def retain_catalog_skus(
    url: str,
    tenant_id: UUID,
    keep_skus: set[str],
    keep_variant_skus: set[str] | None = None,
) -> None:
    """Drop products whose sku is not in the loaded seed.

    When ``keep_variant_skus`` is provided and non-empty, also drop variants
    whose sku is outside that set even if the parent product sku is kept.
    Orders for those rows go with them.
    """
    if not keep_skus:
        return
    tid = str(tenant_id)
    with tenant_connection(url, tenant_id) as conn:
        # Always filter by tenant_id: test URLs often use a superuser that bypasses RLS.
        rows = conn.execute(
            "SELECT id, sku FROM products WHERE tenant_id = %s",
            (tid,),
        ).fetchall()
        drop_products = [row["id"] for row in rows if row["sku"] not in keep_skus]
        variant_ids: list[Any] = []
        if drop_products:
            variants = conn.execute(
                """
                SELECT id FROM product_variants
                WHERE tenant_id = %s AND product_id = ANY(%s)
                """,
                (tid, drop_products),
            ).fetchall()
            variant_ids.extend(row["id"] for row in variants)
        if keep_variant_skus:
            kept_product_ids = [row["id"] for row in rows if row["sku"] in keep_skus]
            if kept_product_ids:
                orphans = conn.execute(
                    """
                    SELECT id FROM product_variants
                    WHERE tenant_id = %s
                      AND product_id = ANY(%s)
                      AND NOT (sku = ANY(%s))
                    """,
                    (tid, kept_product_ids, list(keep_variant_skus)),
                ).fetchall()
                variant_ids.extend(row["id"] for row in orphans)
        if not variant_ids and not drop_products:
            return
        if variant_ids:
            conn.execute(
                "DELETE FROM cart_items WHERE tenant_id = %s AND variant_id = ANY(%s)",
                (tid, variant_ids),
            )
            conn.execute(
                "DELETE FROM product_embeddings WHERE tenant_id = %s AND variant_id = ANY(%s)",
                (tid, variant_ids),
            )
            order_rows = conn.execute(
                """
                SELECT DISTINCT order_id FROM order_items
                WHERE tenant_id = %s AND variant_id = ANY(%s)
                """,
                (tid, variant_ids),
            ).fetchall()
            order_ids = [row["order_id"] for row in order_rows]
            conn.execute(
                "DELETE FROM order_items WHERE tenant_id = %s AND variant_id = ANY(%s)",
                (tid, variant_ids),
            )
            if order_ids:
                conn.execute(
                    """
                    DELETE FROM deliveries
                    WHERE tenant_id = %s
                      AND order_id = ANY(%s)
                      AND order_id NOT IN (
                          SELECT order_id FROM order_items WHERE tenant_id = %s
                      )
                    """,
                    (tid, order_ids, tid),
                )
                conn.execute(
                    """
                    DELETE FROM payments
                    WHERE tenant_id = %s
                      AND order_id = ANY(%s)
                      AND order_id NOT IN (
                          SELECT order_id FROM order_items WHERE tenant_id = %s
                      )
                    """,
                    (tid, order_ids, tid),
                )
                conn.execute(
                    """
                    DELETE FROM orders
                    WHERE tenant_id = %s
                      AND id = ANY(%s)
                      AND id NOT IN (
                          SELECT order_id FROM order_items WHERE tenant_id = %s
                      )
                    """,
                    (tid, order_ids, tid),
                )
            conn.execute(
                "DELETE FROM prices WHERE tenant_id = %s AND variant_id = ANY(%s)",
                (tid, variant_ids),
            )
            conn.execute(
                "DELETE FROM inventory WHERE tenant_id = %s AND variant_id = ANY(%s)",
                (tid, variant_ids),
            )
            conn.execute(
                "DELETE FROM product_variants WHERE tenant_id = %s AND id = ANY(%s)",
                (tid, variant_ids),
            )
        if drop_products:
            conn.execute(
                "DELETE FROM products WHERE tenant_id = %s AND id = ANY(%s)",
                (tid, drop_products),
            )


def open_postgres_shop(
    url: str,
    tenant_id: UUID,
    path: Path | None = None,
    extra_paths: list[Path] | None = None,
    *,
    runtime_url: str | None = None,
    sync_seed: bool = True,
) -> PostgresCommerceStore:
    apply_migrations(url)
    # Hosted startup migrates only. Seeding rewrites catalog, shop knowledge,
    # and the playbook; that stays on the local pilot.
    if sync_seed and path is not None:
        seed_catalog(url, tenant_id, path)
    if sync_seed:
        for extra in extra_paths or []:
            seed_catalog(url, tenant_id, extra)
        seed_shop_knowledge(url, tenant_id)
        seed_conversation_playbook(url, tenant_id)
    store = PostgresCommerceStore(runtime_url or url, tenant_id)
    # Seed writes the JSON stock back; a confirmed QR must stay vendido across restarts.
    # Without a seed, stock is already the live value. Subtracting again would
    # drain it on every production boot.
    if sync_seed:
        store.mark_sold_for_confirmed_payments()
    return store
