from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from .models import JobOptions, MediaItem, Profile


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, destination: str | Path):
        self.root = Path(destination).resolve()
        self.state = self.root / ".mira"
        self.state.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.state / "history.sqlite3", timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, profile_url TEXT NOT NULL, platform TEXT NOT NULL,
          username TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          date_from TEXT NOT NULL, date_to TEXT NOT NULL, only_new INTEGER NOT NULL,
          found INTEGER NOT NULL DEFAULT 0, downloaded INTEGER NOT NULL DEFAULT 0,
          skipped INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0,
          bytes INTEGER NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS media (
          id TEXT PRIMARY KEY, platform TEXT NOT NULL, username TEXT NOT NULL,
          profile_url TEXT NOT NULL, author_id TEXT NOT NULL, media_key TEXT NOT NULL,
          post_id TEXT NOT NULL, idx INTEGER NOT NULL, url TEXT NOT NULL,
          extension TEXT NOT NULL, posted TEXT NOT NULL, status TEXT NOT NULL,
          path TEXT NOT NULL DEFAULT '', sha256 TEXT NOT NULL DEFAULT '',
          size INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '',
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS media_profile ON media(profile_url, status);
        CREATE INDEX IF NOT EXISTS media_hash ON media(platform, author_id, sha256);
        CREATE TABLE IF NOT EXISTS job_items (
          job_id TEXT NOT NULL REFERENCES jobs(id), media_id TEXT NOT NULL REFERENCES media(id),
          outcome TEXT NOT NULL DEFAULT 'found', PRIMARY KEY(job_id,media_id)
        );
        PRAGMA user_version=1;
        """)
        self.db.commit()

    def close(self):
        self.db.close()

    def start_job(self, profile: Profile, options: JobOptions) -> str:
        existing = self.db.execute("SELECT * FROM jobs WHERE id=?", (options.job_id,)).fetchone()
        if existing and (existing["profile_url"], existing["mode"], existing["date_from"], existing["date_to"], bool(existing["only_new"])) == (
            profile.url, options.mode, options.date_from, options.date_to, options.only_new
        ):
            job_id = existing["id"]
            self.db.execute("UPDATE job_items SET outcome='found' WHERE job_id=? AND outcome='failed'", (job_id,))
            self.db.execute("UPDATE jobs SET status='scanning',updated_at=? WHERE id=?", (now(),job_id))
        else:
            job_id = uuid.uuid4().hex
            self.db.execute("""INSERT INTO jobs(id,profile_url,platform,username,mode,status,created_at,updated_at,date_from,date_to,only_new)
                              VALUES(?,?,?,?,?,'scanning',?,?,?,?,?)""",
                            (job_id,profile.url,profile.platform,profile.username,options.mode,now(),now(),options.date_from,options.date_to,int(options.only_new)))
        self.db.commit()
        return job_id

    def register(self, profile: Profile, item: MediaItem, job_id: str) -> dict:
        identity = f"{profile.platform}:{item.author_id}:{item.key}"
        self.db.execute("""INSERT INTO media(id,platform,username,profile_url,author_id,media_key,post_id,idx,url,extension,posted,status,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,'pending',?)
            ON CONFLICT(id) DO UPDATE SET url=excluded.url, username=excluded.username,
            profile_url=excluded.profile_url, posted=excluded.posted, updated_at=excluded.updated_at""",
            (identity,profile.platform,profile.username,profile.url,item.author_id,item.key,item.post_id,item.index,item.url,item.extension,item.posted,now()))
        self.db.execute("INSERT OR IGNORE INTO job_items(job_id,media_id) VALUES(?,?)", (job_id, identity))
        self.db.commit()
        return dict(self.db.execute("SELECT * FROM media WHERE id=?",(identity,)).fetchone())

    def queued(self, profile: Profile) -> list[MediaItem]:
        rows = self.db.execute("SELECT * FROM media WHERE profile_url=? AND status IN ('pending','failed') ORDER BY posted DESC,post_id,idx",(profile.url,)).fetchall()
        return [MediaItem(r['media_key'],r['post_id'],r['idx'],r['url'],r['extension'],r['posted'],r['author_id']) for r in rows]

    def result(self, job_id: str, media_id: str, outcome: str, *, path: str = "", sha256: str = "", size: int = 0, error: str = ""):
        if outcome in ("downloaded", "skipped") and path:
            self.db.execute("UPDATE media SET status='saved',path=?,sha256=?,size=?,error='',updated_at=? WHERE id=?",
                            (path,sha256,size,now(),media_id))
        elif outcome == "failed":
            self.db.execute("UPDATE media SET status='failed',error=?,updated_at=? WHERE id=?", (error,now(),media_id))
        self.db.execute("UPDATE job_items SET outcome=? WHERE job_id=? AND media_id=?", (outcome,job_id,media_id))
        self.db.commit()

    def duplicate(self, platform: str, author_id: str, digest: str, exclude_id: str) -> dict | None:
        from .downloads import file_hash
        for row in self.db.execute("SELECT * FROM media WHERE platform=? AND author_id=? AND sha256=? AND id<>? AND status='saved'",(platform,author_id,digest,exclude_id)):
            candidate = self.root / row["path"]
            try:
                if (candidate.resolve().is_relative_to(self.root) and candidate.is_file()
                        and candidate.stat().st_size == row["size"] and file_hash(candidate) == digest):
                    return dict(row)
            except OSError:
                pass
        return None

    def stats(self, job_id: str) -> dict:
        counts = {r["outcome"]: r["n"] for r in self.db.execute("SELECT outcome,COUNT(*) AS n FROM job_items WHERE job_id=? GROUP BY outcome", (job_id,))}
        total_bytes = self.db.execute("SELECT COALESCE(SUM(m.size),0) FROM job_items j JOIN media m ON m.id=j.media_id WHERE j.job_id=? AND j.outcome='downloaded'",(job_id,)).fetchone()[0]
        result = dict(found=sum(counts.values()),downloaded=counts.get('downloaded',0),skipped=counts.get('skipped',0),failed=counts.get('failed',0),bytes=total_bytes)
        self.db.execute("UPDATE jobs SET found=?,downloaded=?,skipped=?,failed=?,bytes=?,updated_at=? WHERE id=?",(*result.values(),now(),job_id))
        self.db.commit()
        return result

    def set_status(self, job_id: str, status: str, message: str = ""):
        self.db.execute("UPDATE jobs SET status=?,message=?,updated_at=? WHERE id=?",(status,message,now(),job_id))
        self.db.commit()

    def list_jobs(self, limit: int = 40) -> list[dict]:
        return [dict(row) for row in self.db.execute("SELECT * FROM jobs ORDER BY updated_at DESC LIMIT ?",(limit,))]

    def recent_files(self, profile_url: str = "", limit: int = 120) -> list[dict]:
        sql = "SELECT DISTINCT path,post_id,platform,username,author_id,updated_at FROM media WHERE status='saved' AND path<>''"
        args = []
        if profile_url:
            sql += " AND profile_url=?"
            args.append(profile_url)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        args.append(limit)
        result = []
        seen = set()
        for row in self.db.execute(sql,args):
            item = dict(row)
            item['path'] = str(self.root / item['path'])
            if item['path'] not in seen:
                result.append(item)
                seen.add(item['path'])
        return result

    def recover_interrupted(self):
        # Only recover after proving no other worker owns this destination.
        from .locking import DestinationLock, DestinationBusy
        try:
            with DestinationLock(self.root):
                self.db.execute("UPDATE jobs SET status='interrupted',updated_at=? WHERE status IN ('authorizing','scanning','downloading','paused')",(now(),))
                self.db.commit()
        except DestinationBusy:
            pass
