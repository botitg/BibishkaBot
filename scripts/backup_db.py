from pathlib import Path
from shutil import copy2
from datetime import datetime

src = Path("data/bot.db")
if not src.exists():
    print("DB file not found:", src)
else:
    dst = src.parent / f"bot.db.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    copy2(src, dst)
    print("Backed up:", dst)
