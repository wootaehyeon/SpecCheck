"""별도 SQLite 저장소. 공개 동의 내역만 구매자별 익명으로 조회한다."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import sqlite3
from uuid import uuid4

from app.core.config import get_settings
from app.schemas.purchase_history import PurchaseRecord


@contextmanager
def database():
    directory = get_settings().data_dir
    directory.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(directory / "purchase-history.db", timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("""CREATE TABLE IF NOT EXISTS purchase_history (
            id TEXT PRIMARY KEY, owner_hash TEXT NOT NULL, buyer_label TEXT NOT NULL,
            request_id TEXT NOT NULL, product_name TEXT NOT NULL, category TEXT NOT NULL,
            unit_price INTEGER NOT NULL, quantity INTEGER NOT NULL, purchased_on TEXT NOT NULL,
            merchant TEXT NOT NULL, shared INTEGER NOT NULL, created_at TEXT NOT NULL,
            UNIQUE(owner_hash, request_id))""")
        connection.execute("CREATE INDEX IF NOT EXISTS ix_purchase_public ON purchase_history(shared, purchased_on DESC, created_at DESC)")
        connection.execute("CREATE INDEX IF NOT EXISTS ix_purchase_owner ON purchase_history(owner_hash, purchased_on DESC)")
        with connection:
            yield connection
    finally:
        connection.close()


def owner_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def serialize(row) -> dict:
    data = dict(row)
    data.pop("owner_hash")
    data.pop("request_id")
    data["shared"] = bool(data["shared"])
    data["total_price"] = data["unit_price"] * data["quantity"]
    data["currency"] = "KRW"
    data["source"] = "self_reported"
    return data


def save(token: str, record: PurchaseRecord) -> dict:
    owner = owner_hash(token)
    values = record.model_dump(mode="json")
    with database() as conn:
        previous = conn.execute("SELECT * FROM purchase_history WHERE owner_hash=? AND request_id=?",
                                (owner, values["request_id"])).fetchone()
        if previous:
            # 동일 요청 재전송은 중복 기록하지 않는다. 변경된 요청은 새 ID가 필요하다.
            if any(previous[key] != value for key, value in values.items()):
                raise ValueError("이미 저장된 요청입니다. 입력을 변경한 뒤 다시 저장하세요.")
            return serialize(previous)
        values.update(id=str(uuid4()), owner_hash=owner,
                      buyer_label="구매자 " + hashlib.sha256(("public:" + token).encode()).hexdigest()[:12],
                      created_at=datetime.now(timezone.utc).isoformat())
        columns = ",".join(values)
        conn.execute(f"INSERT INTO purchase_history ({columns}) VALUES ({','.join('?' for _ in values)}) ON CONFLICT(owner_hash, request_id) DO NOTHING", tuple(values.values()))
        row = conn.execute("SELECT * FROM purchase_history WHERE owner_hash=? AND request_id=?", (owner, values["request_id"])).fetchone()
        if any(row[key] != value for key, value in record.model_dump(mode="json").items()):
            raise ValueError("이미 저장된 요청입니다. 입력을 변경한 뒤 다시 저장하세요.")
        return serialize(row)


def listing(*, token=None, query="", category=None, buyer=None, page=1, page_size=20) -> dict:
    conditions, params = [], []
    if token:
        conditions.append("owner_hash=?")
        params.append(owner_hash(token))
    else:
        conditions.append("shared=1")
    if query:
        conditions.append("instr(lower(product_name), lower(?)) > 0")
        params.append(query)
    if category:
        conditions.append("category=?")
        params.append(category)
    if buyer:
        conditions.append("buyer_label=?")
        params.append(buyer)
    where = " AND ".join(conditions)
    with database() as conn:
        summary = dict(conn.execute(f"""SELECT COUNT(*) AS records, COUNT(DISTINCT buyer_label) AS buyers,
            COALESCE(SUM(unit_price * quantity), 0) AS total_spent,
            MIN(unit_price) AS min_unit_price, MAX(unit_price) AS max_unit_price
            FROM purchase_history WHERE {where}""", params).fetchone())
        rows = conn.execute(f"SELECT * FROM purchase_history WHERE {where} ORDER BY purchased_on DESC, created_at DESC, id DESC LIMIT ? OFFSET ?",
                            [*params, page_size, (page - 1) * page_size]).fetchall()
    return {"items": [serialize(row) for row in rows], "summary": summary,
            "page": page, "page_size": page_size, "currency": "KRW"}


def set_visibility(token: str, record_id: str, shared: bool) -> dict | None:
    with database() as conn:
        changed = conn.execute("UPDATE purchase_history SET shared=? WHERE id=? AND owner_hash=?",
                               (shared, record_id, owner_hash(token))).rowcount
        return serialize(conn.execute("SELECT * FROM purchase_history WHERE id=?", (record_id,)).fetchone()) if changed else None


def remove(token: str, record_id: str) -> bool:
    with database() as conn:
        return bool(conn.execute("DELETE FROM purchase_history WHERE id=? AND owner_hash=?",
                                 (record_id, owner_hash(token))).rowcount)
