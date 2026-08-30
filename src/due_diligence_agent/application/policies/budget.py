from __future__ import annotations

from contextlib import closing
from decimal import Decimal
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from due_diligence_agent.ports.llm import LLMBudgetRequest, LLMUsage


class BudgetExceeded(RuntimeError):
    stable_error_code = "BUDGET_EXCEEDED"


class BudgetReservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    case_id: UUID
    attempt: str
    reserved_tokens: int
    reserved_usd_cost: Decimal


class BudgetUsageRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reservation_id: UUID
    case_id: UUID
    attempt: str
    tokens: int
    usd_cost: Decimal


class BudgetGuard:
    def __init__(
        self,
        *,
        default_token_limit: int,
        default_usd_limit: Decimal,
        persistence_path: Path | None = None,
    ) -> None:
        if default_token_limit < 0 or default_usd_limit < 0:
            raise ValueError("budget limits must be non-negative")
        self.default_token_limit = default_token_limit
        self.default_usd_limit = default_usd_limit
        self._persistence_path = persistence_path
        self._lock = RLock()
        self._active: dict[UUID, BudgetReservation] = {}
        self._usage: list[BudgetUsageRecord] = []
        if self._persistence_path is not None:
            self._init_store()

    @property
    def persistence_path(self) -> Path | None:
        return self._persistence_path

    def reserve(self, request: LLMBudgetRequest, *, attempt: str) -> BudgetReservation:
        if self._persistence_path is not None:
            return self._reserve_persistent(request, attempt=attempt)
        with self._lock:
            projected_tokens = (
                self._used_tokens(request.case_id)
                + self._reserved_tokens(request.case_id)
                + request.worst_case_tokens
            )
            projected_cost = (
                self._used_cost(request.case_id)
                + self._reserved_cost(request.case_id)
                + request.worst_case_usd_cost
            )
            if projected_tokens > self.default_token_limit or projected_cost > self.default_usd_limit:
                raise BudgetExceeded("BUDGET_EXCEEDED")
            reservation = BudgetReservation(
                id=uuid4(),
                case_id=request.case_id,
                attempt=attempt,
                reserved_tokens=request.worst_case_tokens,
                reserved_usd_cost=request.worst_case_usd_cost,
            )
            self._active[reservation.id] = reservation
            return reservation

    def reconcile(
        self,
        reservation: BudgetReservation,
        *,
        usage: LLMUsage | None,
        actual_usd_cost: Decimal | None = None,
    ) -> BudgetUsageRecord:
        if self._persistence_path is not None:
            return self._reconcile_persistent(
                reservation,
                usage=usage,
                actual_usd_cost=actual_usd_cost,
            )
        with self._lock:
            if reservation.id not in self._active:
                raise ValueError("BUDGET_RESERVATION_ALREADY_RECONCILED")
            tokens = usage.total_tokens if usage is not None else reservation.reserved_tokens
            cost = actual_usd_cost if actual_usd_cost is not None else reservation.reserved_usd_cost
            if tokens < 0 or cost < 0:
                raise ValueError("budget usage must be non-negative")
            self._active.pop(reservation.id)
            record = BudgetUsageRecord(
                reservation_id=reservation.id,
                case_id=reservation.case_id,
                attempt=reservation.attempt,
                tokens=tokens,
                usd_cost=cost,
            )
            self._usage.append(record)
            return record

    def release(self, reservation: BudgetReservation) -> None:
        if self._persistence_path is not None:
            self._release_persistent(reservation)
            return
        with self._lock:
            self._active.pop(reservation.id, None)

    def usage_for_case(self, case_id: UUID) -> tuple[BudgetUsageRecord, ...]:
        if self._persistence_path is not None:
            return self._usage_for_case_persistent(case_id)
        with self._lock:
            return tuple(record for record in self._usage if record.case_id == case_id)

    def reserved_tokens_for_case(self, case_id: UUID) -> int:
        if self._persistence_path is not None:
            return self._reserved_tokens_persistent(case_id)
        with self._lock:
            return self._reserved_tokens(case_id)

    def _used_tokens(self, case_id: UUID) -> int:
        return sum(record.tokens for record in self._usage if record.case_id == case_id)

    def _used_cost(self, case_id: UUID) -> Decimal:
        return sum((record.usd_cost for record in self._usage if record.case_id == case_id), Decimal("0"))

    def _reserved_tokens(self, case_id: UUID) -> int:
        return sum(
            reservation.reserved_tokens
            for reservation in self._active.values()
            if reservation.case_id == case_id
        )

    def _reserved_cost(self, case_id: UUID) -> Decimal:
        return sum(
            (
                reservation.reserved_usd_cost
                for reservation in self._active.values()
                if reservation.case_id == case_id
            ),
            Decimal("0"),
        )

    def _init_store(self) -> None:
        if self._persistence_path is None:
            return
        self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS budget_active_reservations (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    attempt TEXT NOT NULL,
                    reserved_tokens INTEGER NOT NULL,
                    reserved_usd_cost TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS budget_usage_records (
                    reservation_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    attempt TEXT NOT NULL,
                    tokens INTEGER NOT NULL,
                    usd_cost TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        if self._persistence_path is None:
            raise RuntimeError("budget persistence is not configured")
        conn = sqlite3.connect(self._persistence_path, timeout=30, isolation_level=None)
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _reserve_persistent(self, request: LLMBudgetRequest, *, attempt: str) -> BudgetReservation:
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    used_tokens, used_cost = self._persistent_used(conn, request.case_id)
                    reserved_tokens, reserved_cost = self._persistent_reserved(conn, request.case_id)
                    projected_tokens = used_tokens + reserved_tokens + request.worst_case_tokens
                    projected_cost = used_cost + reserved_cost + request.worst_case_usd_cost
                    if projected_tokens > self.default_token_limit or projected_cost > self.default_usd_limit:
                        raise BudgetExceeded("BUDGET_EXCEEDED")
                    reservation = BudgetReservation(
                        id=uuid4(),
                        case_id=request.case_id,
                        attempt=attempt,
                        reserved_tokens=request.worst_case_tokens,
                        reserved_usd_cost=request.worst_case_usd_cost,
                    )
                    conn.execute(
                        """
                        INSERT INTO budget_active_reservations
                            (id, case_id, attempt, reserved_tokens, reserved_usd_cost)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            str(reservation.id),
                            str(reservation.case_id),
                            reservation.attempt,
                            reservation.reserved_tokens,
                            str(reservation.reserved_usd_cost),
                        ),
                    )
                    conn.execute("COMMIT")
                    return reservation
                except Exception:
                    conn.execute("ROLLBACK")
                    raise

    def _reconcile_persistent(
        self,
        reservation: BudgetReservation,
        *,
        usage: LLMUsage | None,
        actual_usd_cost: Decimal | None,
    ) -> BudgetUsageRecord:
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    row = conn.execute(
                        """
                        SELECT case_id, attempt, reserved_tokens, reserved_usd_cost
                        FROM budget_active_reservations
                        WHERE id = ?
                        """,
                        (str(reservation.id),),
                    ).fetchone()
                    if row is None:
                        raise ValueError("BUDGET_RESERVATION_ALREADY_RECONCILED")
                    tokens = usage.total_tokens if usage is not None else int(row[2])
                    cost = actual_usd_cost if actual_usd_cost is not None else Decimal(str(row[3]))
                    if tokens < 0 or cost < 0:
                        raise ValueError("budget usage must be non-negative")
                    record = BudgetUsageRecord(
                        reservation_id=reservation.id,
                        case_id=UUID(str(row[0])),
                        attempt=str(row[1]),
                        tokens=tokens,
                        usd_cost=cost,
                    )
                    conn.execute(
                        "DELETE FROM budget_active_reservations WHERE id = ?",
                        (str(reservation.id),),
                    )
                    conn.execute(
                        """
                        INSERT INTO budget_usage_records
                            (reservation_id, case_id, attempt, tokens, usd_cost)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            str(record.reservation_id),
                            str(record.case_id),
                            record.attempt,
                            record.tokens,
                            str(record.usd_cost),
                        ),
                    )
                    conn.execute("COMMIT")
                    return record
                except Exception:
                    conn.execute("ROLLBACK")
                    raise

    def _release_persistent(self, reservation: BudgetReservation) -> None:
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute(
                        "DELETE FROM budget_active_reservations WHERE id = ?",
                        (str(reservation.id),),
                    )
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise

    def _usage_for_case_persistent(self, case_id: UUID) -> tuple[BudgetUsageRecord, ...]:
        with self._lock:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    """
                    SELECT reservation_id, case_id, attempt, tokens, usd_cost
                    FROM budget_usage_records
                    WHERE case_id = ?
                    ORDER BY rowid
                    """,
                    (str(case_id),),
                ).fetchall()
        return tuple(
            BudgetUsageRecord(
                reservation_id=UUID(str(row[0])),
                case_id=UUID(str(row[1])),
                attempt=str(row[2]),
                tokens=int(row[3]),
                usd_cost=Decimal(str(row[4])),
            )
            for row in rows
        )

    def _reserved_tokens_persistent(self, case_id: UUID) -> int:
        with self._lock:
            with closing(self._connect()) as conn:
                reserved_tokens, _reserved_cost = self._persistent_reserved(conn, case_id)
        return reserved_tokens

    def _persistent_used(self, conn: sqlite3.Connection, case_id: UUID) -> tuple[int, Decimal]:
        rows = conn.execute(
            """
            SELECT tokens, usd_cost
            FROM budget_usage_records
            WHERE case_id = ?
            """,
            (str(case_id),),
        ).fetchall()
        return (
            sum(int(row[0]) for row in rows),
            sum((Decimal(str(row[1])) for row in rows), Decimal("0")),
        )

    def _persistent_reserved(self, conn: sqlite3.Connection, case_id: UUID) -> tuple[int, Decimal]:
        rows = conn.execute(
            """
            SELECT reserved_tokens, reserved_usd_cost
            FROM budget_active_reservations
            WHERE case_id = ?
            """,
            (str(case_id),),
        ).fetchall()
        return (
            sum(int(row[0]) for row in rows),
            sum((Decimal(str(row[1])) for row in rows), Decimal("0")),
        )
