"""
CulpemCorpus — local archive integration (YeneConservatio).

Looks for YeneConservatio DBs at ../YeneConservatio/data/yene_{source}.db
relative to this file. If the sibling repo isn't present, every function
degrades gracefully (returns None / empty).
"""
import os
import sqlite3
import logging

logger = logging.getLogger(__name__)

_THIS_DIR  = os.path.dirname(os.path.abspath(__file__))
_YENE_DATA = os.path.join(_THIS_DIR, "..", "YeneConservatio", "data")


def _db_path(source_id):
    return os.path.normpath(os.path.join(_YENE_DATA, f"yene_{source_id}.db"))


def _connect(source_id):
    path = _db_path(source_id)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    return con


def coverage(source_id):
    """
    Return (min_date, max_date, article_count) if a local DB exists with data,
    else None.
    """
    path = _db_path(source_id)
    if not os.path.exists(path):
        return None
    try:
        con = _connect(source_id)
        row = con.execute(
            "SELECT MIN(date) mn, MAX(date) mx, COUNT(*) n FROM articles"
        ).fetchone()
        con.close()
        if not row["mn"]:
            return None
        return row["mn"], row["mx"], row["n"]
    except Exception as e:
        logger.warning("local_db coverage error (%s): %s", source_id, e)
        return None


def has_fts(source_id):
    """Check whether the FTS5 virtual table exists in this DB."""
    try:
        con = _connect(source_id)
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='articles_fts'"
        ).fetchone()
        con.close()
        return row is not None
    except Exception:
        return False


def query(source_id, query_str, date_from, date_to):
    """
    Yield article dicts from the local DB.

    Uses FTS5 if available (better quality than substring match).
    Falls back to LIKE search if FTS table is missing.
    date_from / date_to are YYYY-MM-DD strings (empty string = no bound).
    """
    path = _db_path(source_id)
    if not os.path.exists(path):
        return

    d_from = date_from or "0000-01-01"
    d_to   = date_to   or "9999-12-31"

    try:
        con  = _connect(source_id)
        use_fts = query_str and has_fts(source_id)

        if use_fts:
            rows = con.execute(
                "SELECT a.source, a.date, a.title, a.url, a.body_text, a.section "
                "FROM articles a "
                "JOIN articles_fts f ON a.id = f.rowid "
                "WHERE articles_fts MATCH ? "
                "AND a.date BETWEEN ? AND ? "
                "ORDER BY a.date DESC",
                (query_str, d_from, d_to),
            ).fetchall()
        elif query_str:
            pattern = f"%{query_str}%"
            rows = con.execute(
                "SELECT source, date, title, url, body_text, section FROM articles "
                "WHERE (title LIKE ? OR body_text LIKE ?) "
                "AND date BETWEEN ? AND ? "
                "ORDER BY date DESC",
                (pattern, pattern, d_from, d_to),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT source, date, title, url, body_text, section FROM articles "
                "WHERE date BETWEEN ? AND ? "
                "ORDER BY date DESC",
                (d_from, d_to),
            ).fetchall()

        con.close()
        for row in rows:
            yield dict(row)

    except Exception as e:
        logger.warning("local_db query error (%s): %s", source_id, e)
