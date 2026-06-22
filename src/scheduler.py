import os
import sqlite3
from datetime import datetime
from pathlib import Path
import traceback
import tweepy
from apscheduler.schedulers.background import BackgroundScheduler
import config

DB_FILE_PATH = config.RAW_DATA_DIR / "scheduler.db"
UPLOAD_DIR = config.BASE_DIR / "static" / "uploads"

# Ensure the uploads directory exists
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

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
                tweet_id TEXT DEFAULT NULL,
                media_file TEXT DEFAULT NULL
            )
        """)
        conn.commit()
        
        # Safe migration: Add media_file column if it doesn't exist
        try:
            conn.execute("ALTER TABLE scheduled_tweets ADD COLUMN media_file TEXT DEFAULT NULL")
            conn.commit()
            print("[+] Added media_file column to scheduled_tweets table.")
        except sqlite3.OperationalError:
            # Column already exists
            pass
            
        print("[+] Scheduler database initialized successfully.")
    except Exception as e:
        print(f"[!] Failed to initialize scheduler database: {traceback.format_exc()}")
    finally:
        conn.close()

# --- Database CRUD Operations ---

def add_scheduled_tweet(text: str, scheduled_at: str, media_file: str = None):
    """
    Add a scheduled tweet.
    scheduled_at: ISO 8601 string, e.g. "2026-06-22 15:30:00"
    """
    conn = get_db_connection()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO scheduled_tweets (text, scheduled_at, status, created_at, media_file) VALUES (?, ?, ?, ?, ?)",
            (text, scheduled_at, "pending", now_str, media_file)
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

def update_scheduled_tweet(post_id: int, text: str = None, scheduled_at: str = None, status: str = None, tweet_id: str = None, error_message: str = None, media_file: str = None, clear_media: bool = False):
    """Update scheduled tweet fields."""
    old_tweet = get_scheduled_tweet(post_id)
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
        
        should_delete_old_media = False
        if clear_media:
            updates.append("media_file = NULL")
            should_delete_old_media = True
        elif media_file is not None:
            updates.append("media_file = ?")
            params.append(media_file)
            should_delete_old_media = True
            
        if not updates:
            return False
            
        params.append(post_id)
        cursor.execute(f"UPDATE scheduled_tweets SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        success = cursor.rowcount > 0
        
        # Clean up old media file if update succeeded and media has changed/cleared
        if success and should_delete_old_media and old_tweet and old_tweet.get("media_file"):
            if clear_media or (media_file is not None and old_tweet["media_file"] != media_file):
                media_path = config.BASE_DIR / old_tweet["media_file"]
                if media_path.exists() and media_path.is_file():
                    try:
                        media_path.unlink()
                        print(f"[+] Deleted replaced/removed media file: {media_path}")
                    except Exception as ex:
                        print(f"[!] Failed to delete local file {media_path}: {ex}")
                        
        return success
    except Exception as e:
        print(f"[!] Error updating scheduled tweet {post_id}: {e}")
        return False
    finally:
        conn.close()

def delete_scheduled_tweet(post_id: int):
    """Delete a scheduled tweet by ID."""
    tweet = get_scheduled_tweet(post_id)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM scheduled_tweets WHERE id = ?", (post_id,))
        conn.commit()
        success = cursor.rowcount > 0
        
        if success and tweet and tweet.get("media_file"):
            media_path = config.BASE_DIR / tweet["media_file"]
            if media_path.exists() and media_path.is_file():
                try:
                    media_path.unlink()
                    print(f"[+] Deleted local media file: {media_path}")
                except Exception as ex:
                    print(f"[!] Failed to delete local file {media_path}: {ex}")
        return success
    except Exception as e:
        print(f"[!] Error deleting scheduled tweet {post_id}: {e}")
        return False
    finally:
        conn.close()

# --- X (Twitter) API Integration ---

def post_to_x(text: str, media_file: str = None):
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

    # Resolve absolute path of media_file if present
    abs_media_path = None
    if media_file:
        path_obj = Path(media_file)
        if not path_obj.is_absolute():
            abs_media_path = config.BASE_DIR / media_file
        else:
            abs_media_path = path_obj
        if not abs_media_path.exists():
            print(f"[!] Media file {abs_media_path} not found. Proceeding without media.")
            abs_media_path = None

    if is_placeholder:
        print("[!] X API credentials not fully configured. Simulating successful post.")
        mock_id = f"simulated_{int(datetime.now().timestamp())}"
        sim_res = {"success": True, "tweet_id": mock_id, "simulated": True}
        if media_file:
            sim_res["media_file_uploaded"] = str(media_file)
            print(f"[*] Simulated upload of media file: {media_file}")
        return sim_res

    try:
        # X API v2 client
        client = tweepy.Client(
            consumer_key=ck,
            consumer_secret=cs,
            access_token=at,
            access_token_secret=ats
        )

        media_ids = None
        if abs_media_path:
            print(f"[*] Uploading media {abs_media_path} via API v1.1...")
            # X API v1.1 auth for media upload
            auth = tweepy.OAuth1UserHandler(
                consumer_key=ck,
                consumer_secret=cs,
                access_token=at,
                access_token_secret=ats
            )
            api = tweepy.API(auth)
            media = api.media_upload(filename=str(abs_media_path))
            media_ids = [media.media_id_string]
            print(f"[+] Media uploaded successfully. Media ID: {media.media_id_string}")

        # Create tweet (attach media if present)
        if media_ids:
            response = client.create_tweet(text=text, media_ids=media_ids)
        else:
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
            tmedia = tweet["media_file"]
            print(f"[*] Processing scheduled tweet #{tid} at {now_str}...")
            
            # Update status to 'posting' to avoid double execution in slow environments
            update_scheduled_tweet(tid, status="posting")
            
            # Post to X
            res = post_to_x(ttext, media_file=tmedia)
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
