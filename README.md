# Mutual YouTube Engagement Telegram Bot

A production-ready Telegram bot for fair, mutual YouTube engagement with anti-cheat, stylish UI, and full admin controls.  
**Works on Termux, Render, Heroku, any Python 3+ host.**

---

## Features

- Pairwise video exchange with mutual proof verification  
- Anti-cheat: warnings/strikes on inactivity, fake proof, cheating  
- Stylish button-based UI (no typing needed)  
- Full admin panel: strikes, ban/unban, complaints, logs  
- Pause/resume, user status, task logs  
- Deployment-ready, cross-platform (Termux/Heroku/Render...)  
- Data storage: SQLite, local proofs/thumbnails

---

## Setup

1. **Clone repo & install requirements:**
    ```sh
    pip install -r requirements.txt
    ```

2. **Configure .env:**
    ```
    BOT_TOKEN=YOUR_TOKEN_HERE
    ADMIN_IDS=YourTelegramID,AnotherID
    DB_PATH=bot.db
    PROOF_PATH=proofs/
    THUMB_PATH=thumbs/
    ```

3. **Run bot:**
    ```sh
    python main.py
    ```

---

## Deployment Tips

- **Termux:**  
  - Run with `python main.py`
- **Heroku/Render:**  
  - Use `requirements.txt` and set env variables
  - No OS-specific code, works everywhere

---

## Workflow

1. User uploads YouTube video (title, thumb, link, duration)
2. User presses "Ready", gets paired 
3. Each user receives partner's video details
4. Watch video (screen record), upload proof
5. Partner reviews/approves/reports proof
6. Anti-cheat (timeout, cheating = strikes/ban)
7. Admin panel for full manual control

---

## Admin Commands

- `/adminpanel` – Opens full admin menu
- Manual actions: ban, strike, unban, complaint review

---

## License

MIT
