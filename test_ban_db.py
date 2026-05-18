import database as db
from datetime import datetime, timedelta

if __name__ == '__main__':
    db.init_db([])
    user = 555555
    chat = 99999
    until = (datetime.utcnow() + timedelta(minutes=10)).isoformat(timespec='seconds')
    db.add_ban_record(user, chat, until, issuer_id=8436225978, reason='test ban')
    rec = db.get_active_ban(user, chat)
    print('active ban ->', rec)
    # simulate expiry
    db.add_ban_record(user, chat, (datetime.utcnow() - timedelta(minutes=1)).isoformat(timespec='seconds'), issuer_id=8436225978)
    rec2 = db.get_active_ban(user, chat)
    print('after expiry ->', rec2)
