"""SQLite database for game history and statistics."""
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pathlib import Path

from backend.config import DATABASE_PATH


def get_connection():
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_number INTEGER NOT NULL,
                player_move TEXT NOT NULL,
                player_confidence REAL,
                computer_move TEXT NOT NULL,
                predicted_player_move TEXT,
                result TEXT NOT NULL,
                strategy_used TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rounds_result ON rounds(result)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rounds_timestamp ON rounds(timestamp)")


def insert_round(
    round_number: int,
    player_move: str,
    player_confidence: Optional[float],
    computer_move: str,
    predicted_player_move: Optional[str],
    result: str,
    strategy_used: Optional[str],
):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO rounds
               (round_number, player_move, player_confidence, computer_move,
                predicted_player_move, result, strategy_used)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (round_number, player_move, player_confidence, computer_move,
             predicted_player_move, result, strategy_used),
        )


def get_recent_rounds(limit: int = 20) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM rounds ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def get_stats() -> Dict[str, Any]:
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM rounds").fetchone()[0]
        if total == 0:
            return {"total_games": 0, "wins": 0, "losses": 0, "draws": 0, "win_rate": 0.0}

        wins = conn.execute(
            "SELECT COUNT(*) FROM rounds WHERE result = 'win'"
        ).fetchone()[0]
        losses = conn.execute(
            "SELECT COUNT(*) FROM rounds WHERE result = 'lose'"
        ).fetchone()[0]
        draws = conn.execute(
            "SELECT COUNT(*) FROM rounds WHERE result = 'draw'"
        ).fetchone()[0]

        decisive = wins + losses
        return {
            "total_games": total,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "win_rate": round(wins / decisive, 4) if decisive > 0 else 0.0,
        }


def get_class_stats() -> Dict[str, int]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT player_move, COUNT(*) as cnt FROM rounds GROUP BY player_move"
        ).fetchall()
        return {r["player_move"]: r["cnt"] for r in rows}


def get_strategy_stats() -> Dict[str, Any]:
    """Per-strategy accuracy: how often the predicted player move matched the actual move."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT strategy_used,
                      COUNT(*) as total,
                      SUM(CASE WHEN predicted_player_move = player_move THEN 1 ELSE 0 END) as correct
               FROM rounds WHERE strategy_used IS NOT NULL
               GROUP BY strategy_used"""
        ).fetchall()
        return {
            r["strategy_used"]: {
                "total": r["total"],
                "accuracy": round(r["correct"] / r["total"], 4) if r["total"] > 0 else 0.0,
            }
            for r in rows
        }


def reset_history():
    with get_connection() as conn:
        conn.execute("DELETE FROM rounds")


# Initialize DB on import
init_db()
