import os
import sqlite3
from datetime import datetime
import traceback
import tweepy
from apscheduler.schedulers.background import BackgroundScheduler
import config

DB_FILE_PATH = config.RAW_DATA_DIR / "scheduler.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the SQLite database and create tables if they do not exist."""
    conn = get_db_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_tweets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                error_message TEXT DEFAULT NULL,
                tweet_id TEXT DEFAULT NULL
            )
        """)
        conn.commit()
        print("[+] Scheduler database initialized successfully.")
    except Exception as e:
        print(f"[!] Failed to initialize scheduler database: {traceback.format_exc()}")
    finally:
        conn.close()

# --- Database CRUD Operations ---

def add_scheduled_tweet(text: str, scheduled_at: str):
    """
    Add a scheduled tweet.
    scheduled_at: ISO 8601 string, e.g. "2026-06-22 15:30:00"
    """
    conn = get_db_connection()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO scheduled_tweets (text, scheduled_at, status, created_at) VALUES (?, ?, ?, ?)",
            (text, scheduled_at, "pending", now_str)
        )
        conn.commit()
        new_id = cursor.lastrowid
        return new_id
    except Exception as e:
        print(f"[!] Error adding scheduled tweet: {e}")
        return None
    finally:
        conn.close()

def get_scheduled_tweets(start_date: str = None, end_date: str = None):
    """Get list of scheduled tweets, optionally filtered by date range."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if start_date and end_date:
            cursor.execute(
                "SELECT * FROM scheduled_tweets WHERE scheduled_at BETWEEN ? AND ? ORDER BY scheduled_at ASC",
                (start_date, end_date)
            )
        else:
            cursor.execute("SELECT * FROM scheduled_tweets ORDER BY scheduled_at ASC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[!] Error fetching scheduled tweets: {e}")
        return []
    finally:
        conn.close()

def get_scheduled_tweet(post_id: int):
    """Get a single scheduled tweet by ID."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM scheduled_tweets WHERE id = ?", (post_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"[!] Error fetching scheduled tweet {post_id}: {e}")
        return None
    finally:
        conn.close()

def update_scheduled_tweet(post_id: int, text: str = None, scheduled_at: str = None, status: str = None, tweet_id: str = None, error_message: str = None):
    """Update scheduled tweet fields."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        updates = []
        params = []
        if text is not None:
            updates.append("text = ?")
            params.append(text)
        if scheduled_at is not None:
            updates.append("scheduled_at = ?")
            params.append(scheduled_at)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if tweet_id is not None:
            updates.append("tweet_id = ?")
            params.append(tweet_id)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
            
        if not updates:
            return False
            
        params.append(post_id)
        cursor.execute(f"UPDATE scheduled_tweets SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"[!] Error updating scheduled tweet {post_id}: {e}")
        return False
    finally:
        conn.close()

def delete_scheduled_tweet(post_id: int):
    """Delete a scheduled tweet by ID."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM scheduled_tweets WHERE id = ?", (post_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"[!] Error deleting scheduled tweet {post_id}: {e}")
        return False
    finally:
        conn.close()

# --- X (Twitter) API Integration ---

def post_to_x(text: str):
    """
    Publish a tweet to X using X API v2.
    If credentials are placeholder or missing, it simulates a successful post for testing purposes.
    """
    ck = config.X_CONSUMER_KEY
    cs = config.X_CONSUMER_SECRET
    at = config.X_ACCESS_TOKEN
    ats = config.X_ACCESS_TOKEN_SECRET

    # Check for placeholder values or empty keys
    is_placeholder = (
        not ck or not cs or not at or not ats or
        "YOUR_CONSUMER_KEY" in ck or "YOUR_ACCESS_TOKEN" in at or
        ck.strip() == ""
    )

    if is_placeholder:
        print("[!] X API credentials not fully configured. Simulating successful post.")
        mock_id = f"simulated_{int(datetime.now().timestamp())}"
        return {"success": True, "tweet_id": mock_id, "simulated": True}

    try:
        client = tweepy.Client(
            consumer_key=ck,
            consumer_secret=cs,
            access_token=at,
            access_token_secret=ats
        )
        response = client.create_tweet(text=text)
        # Check if response has data and id
        if response and response.data and 'id' in response.data:
            tweet_id = str(response.data['id'])
            return {"success": True, "tweet_id": tweet_id, "simulated": False}
        else:
            return {"success": False, "error": "No tweet ID returned from X API"}
    except Exception as e:
        error_msg = str(e)
        print(f"[!] X API posting failed: {error_msg}")
        return {"success": False, "error": error_msg}

# --- APScheduler Background Worker ---

def worker_tick():
    """Tick function executed every 60 seconds to process pending tweets."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Find pending tweets that should have been posted by now
        cursor.execute(
            "SELECT * FROM scheduled_tweets WHERE status = 'pending' AND scheduled_at <= ?",
            (now_str,)
        )
        tweets_to_post = [dict(r) for r in cursor.fetchall()]
        conn.close() # Close it so we don't lock the DB during network requests

        for tweet in tweets_to_post:
            tid = tweet["id"]
            ttext = tweet["text"]
            print(f"[*] Processing scheduled tweet #{tid} at {now_str}...")
            
            # Update status to 'posting' to avoid double execution in slow environments
            update_scheduled_tweet(tid, status="posting")
            
            # Post to X
            res = post_to_x(ttext)
            if res["success"]:
                # Success
                update_scheduled_tweet(
                    tid,
                    status="posted",
                    tweet_id=res["tweet_id"],
                    error_message=None
                )
                print(f"[+] Successfully posted scheduled tweet #{tid} (Tweet ID: {res['tweet_id']})")
            else:
                # Failure
                update_scheduled_tweet(
                    tid,
                    status="failed",
                    error_message=res.get("error", "Unknown error")
                )
                print(f"[!] Failed to post scheduled tweet #{tid}: {res.get('error')}")

    except Exception as e:
        print(f"[!] Error in background scheduler tick: {e}")

_scheduler_started = False

def start_scheduler():
    """Start the background scheduler."""
    global _scheduler_started
    if _scheduler_started:
        return
        
    init_db()
    
    scheduler = BackgroundScheduler()
    # Execute worker_tick every 60 seconds
    scheduler.add_job(worker_tick, 'interval', seconds=60)
    scheduler.start()
    _scheduler_started = True
    print("[+] Background scheduler started. Processing queue every 60 seconds.")
