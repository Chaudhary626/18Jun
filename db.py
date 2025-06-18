import sqlite3
from contextlib import closing
from config import DB_PATH
from datetime import datetime, timedelta

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            strikes INTEGER DEFAULT 0,
            banned INTEGER DEFAULT 0,
            paused INTEGER DEFAULT 0,
            joined TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            yt_link TEXT,
            thumb TEXT,
            duration INTEGER,
            uploaded TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active INTEGER DEFAULT 1
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_a INTEGER,
            user_b INTEGER,
            video_a_id INTEGER,
            video_b_id INTEGER,
            status TEXT DEFAULT 'pending',
            proof_a TEXT,
            proof_b TEXT,
            proof_a_time TIMESTAMP,
            proof_b_time TIMESTAMP,
            verify_a TEXT,
            verify_b TEXT,
            verify_a_time TIMESTAMP,
            verify_b_time TIMESTAMP,
            complaint_a TEXT,
            complaint_b TEXT,
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complainant INTEGER,
            accused INTEGER,
            task_id INTEGER,
            reason TEXT,
            proof_file TEXT,
            status TEXT DEFAULT 'open',
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.commit()

def add_user(user):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)", (user.id, user.username or ""))
        conn.commit()

def get_user(uid):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT id, username, strikes, banned, paused FROM users WHERE id=?", (uid,))
        r = c.fetchone()
        if not r: return None
        return {"id": r[0], "username": r[1], "strikes": r[2], "banned": r[3], "paused": r[4]}

def get_user_active_video_count(uid):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM videos WHERE user_id=? AND active=1", (uid,))
        return c.fetchone()[0]

def add_video(uid, title, yt_link, thumb, duration):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute('''INSERT INTO videos (user_id, title, yt_link, thumb, duration)
            VALUES (?, ?, ?, ?, ?)''', (uid, title, yt_link, thumb, duration))
        conn.commit()

def get_videos_by_user(uid):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT id, title, yt_link, thumb, duration FROM videos WHERE user_id=? AND active=1", (uid,))
        return [{"id": x[0], "title": x[1], "yt_link": x[2], "thumb": x[3], "duration": x[4]} for x in c.fetchall()]

def get_video_by_id(vid):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT id, user_id, title, yt_link, thumb, duration FROM videos WHERE id=?", (vid,))
        r = c.fetchone()
        if not r: return None
        return {"id": r[0], "user_id": r[1], "title": r[2], "yt_link": r[3], "thumb": r[4], "duration": r[5]}

def remove_video(vid):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("UPDATE videos SET active=0 WHERE id=?", (vid,))
        conn.commit()

def get_ready_users():
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE paused=0 AND banned=0")
        return [x[0] for x in c.fetchall()]

def get_waiting_users():
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE paused=0 AND banned=0")
        return [x[0] for x in c.fetchall()]

def create_task_pair(uid):
    # Pair with another ready user who has an active video and no pending task
    with closing(get_conn()) as conn:
        c = conn.cursor()
        # Find a partner
        c.execute("SELECT id FROM users WHERE id!=? AND paused=0 AND banned=0", (uid,))
        partners = [x[0] for x in c.fetchall()]
        for partner in partners:
            # Only pair if both have active videos and no pending tasks
            c.execute("SELECT COUNT(*) FROM videos WHERE user_id=? AND active=1", (uid,))
            if c.fetchone()[0] == 0: continue
            c.execute("SELECT COUNT(*) FROM videos WHERE user_id=? AND active=1", (partner,))
            if c.fetchone()[0] == 0: continue
            c.execute("SELECT COUNT(*) FROM tasks WHERE (user_a=? OR user_b=?) AND status='pending'", (uid, uid))
            if c.fetchone()[0] > 0: continue
            c.execute("SELECT COUNT(*) FROM tasks WHERE (user_a=? OR user_b=?) AND status='pending'", (partner, partner))
            if c.fetchone()[0] > 0: continue
            # Get latest active video for both
            c.execute("SELECT id FROM videos WHERE user_id=? AND active=1 ORDER BY uploaded DESC LIMIT 1", (uid,))
            video_a_id = c.fetchone()[0]
            c.execute("SELECT id FROM videos WHERE user_id=? AND active=1 ORDER BY uploaded DESC LIMIT 1", (partner,))
            video_b_id = c.fetchone()[0]
            # Create task
            c.execute('''INSERT INTO tasks (user_a, user_b, video_a_id, video_b_id)
                VALUES (?, ?, ?, ?)''', (uid, partner, video_a_id, video_b_id))
            conn.commit()
            return True, partner, c.lastrowid
        return False, None, None

def get_task_for_user(uid):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute('''SELECT id, user_a, user_b, video_a_id, video_b_id, status, proof_a, proof_b, verify_a, verify_b, created
            FROM tasks WHERE (user_a=? OR user_b=?) AND status='pending' ORDER BY id DESC LIMIT 1''', (uid, uid))
        r = c.fetchone()
        if not r: return None
        return {
            "id": r[0], "user_a": r[1], "user_b": r[2], "video_a_id": r[3], "video_b_id": r[4],
            "status": r[5], "proof_a": r[6], "proof_b": r[7], "verify_a": r[8], "verify_b": r[9], "created": r[10]
        }

def submit_proof(task_id, uid, file_path):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT user_a, user_b FROM tasks WHERE id=?", (task_id,))
        user_a, user_b = c.fetchone()
        now = datetime.now().isoformat()
        if uid == user_a:
            c.execute("UPDATE tasks SET proof_a=?, proof_a_time=? WHERE id=?", (file_path, now, task_id))
        else:
            c.execute("UPDATE tasks SET proof_b=?, proof_b_time=? WHERE id=?", (file_path, now, task_id))
        conn.commit()

def verify_proof(task_id, uid, status):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT user_a, user_b FROM tasks WHERE id=?", (task_id,))
        user_a, user_b = c.fetchone()
        now = datetime.now().isoformat()
        if uid == user_a:
            c.execute("UPDATE tasks SET verify_a=?, verify_a_time=? WHERE id=?", (status, now, task_id))
        else:
            c.execute("UPDATE tasks SET verify_b=?, verify_b_time=? WHERE id=?", (status, now, task_id))
        conn.commit()

def get_task_by_id(task_id):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute('''SELECT id, user_a, user_b, video_a_id, video_b_id, status, proof_a, proof_b, verify_a, verify_b, created
            FROM tasks WHERE id=?''', (task_id,))
        r = c.fetchone()
        if not r: return None
        return {
            "id": r[0], "user_a": r[1], "user_b": r[2], "video_a_id": r[3], "video_b_id": r[4],
            "status": r[5], "proof_a": r[6], "proof_b": r[7], "verify_a": r[8], "verify_b": r[9], "created": r[10]
        }

def set_user_paused(uid):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET paused=1 WHERE id=?", (uid,))
        conn.commit()

def set_user_active(uid):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET paused=0 WHERE id=?", (uid,))
        conn.commit()

def add_complaint(complainant, accused, task_id, reason, proof_file):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute('''INSERT INTO complaints (complainant, accused, task_id, reason, proof_file)
            VALUES (?, ?, ?, ?, ?)''', (complainant, accused, task_id, reason, proof_file))
        conn.commit()

def get_complaints():
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute('''SELECT id, complainant, accused, task_id, reason, proof_file, status, created
            FROM complaints WHERE status='open' ''')
        return c.fetchall()

def set_task_status(task_id, status):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
        conn.commit()

def get_user_strikes(uid):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT strikes FROM users WHERE id=?", (uid,))
        return c.fetchone()[0]

def get_user_ban_status(uid):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT banned FROM users WHERE id=?", (uid,))
        return c.fetchone()[0]

def get_user_pause_status(uid):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT paused FROM users WHERE id=?", (uid,))
        return c.fetchone()[0]

def get_user_tasks(uid):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM tasks WHERE user_a=? OR user_b=?", (uid, uid))
        return [x[0] for x in c.fetchall()]

def admin_ban_user(uid):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET banned=1 WHERE id=?", (uid,))
        conn.commit()

def admin_strike_user(uid):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET strikes = strikes + 1 WHERE id=?", (uid,))
        conn.commit()
        c.execute("SELECT strikes FROM users WHERE id=?", (uid,))
        strikes = c.fetchone()[0]
        if strikes >= 3:
            c.execute("UPDATE users SET banned=1 WHERE id=?", (uid,))
        conn.commit()

def admin_unban_user(uid):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET banned=0 WHERE id=?", (uid,))
        conn.commit()

def admin_remove_strike(uid):
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET strikes = MAX(strikes-1, 0) WHERE id=?", (uid,))
        conn.commit()

def get_pending_tasks_timeout():
    # Returns tasks where proof submitted but verify delayed > 2hr
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute('''SELECT id, user_a, user_b, proof_a, proof_b, verify_a, verify_b, created
            FROM tasks WHERE status='pending' ''')
        return c.fetchall()

def get_all_users():
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT id, username, strikes, banned, paused FROM users")
        return c.fetchall()

def get_all_tasks():
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM tasks")
        return c.fetchall()

def get_admin_stats():
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'")
        active_tasks = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM complaints WHERE status='open'")
        complaints = c.fetchone()[0]
        c.execute("SELECT SUM(strikes) FROM users")
        strikes = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM users WHERE banned=1")
        banned = c.fetchone()[0]
        return {
            "users": users, "active_tasks": active_tasks,
            "complaints": complaints, "strikes": strikes, "banned": banned
        }