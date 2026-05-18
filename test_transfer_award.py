import database as db
from datetime import datetime

if __name__ == '__main__':
    db.init_db([])
    user1 = 111111111
    user2 = 222222222
    chat_id = 99999
    title = f'TransferTest {datetime.utcnow().strftime("%Y%m%d%H%M%S%f")}'
    issuer = 8436225978
    print('Creating unique epic award...')
    a1 = db.add_award(user1, chat_id, title, issuer, emoji='🏅', description='Transfer test', rarity='epic')
    print('award_id ->', a1)
    if a1 == -1:
        print('Failed to create unique award; maybe duplicate title exists. Exiting.')
    else:
        print('Transferring award to user2...')
        ok = db.transfer_award(a1, user2)
        print('transfer ok ->', ok)
        award = db.get_award(a1)
        print('award owner ->', award.get('user_id'))
