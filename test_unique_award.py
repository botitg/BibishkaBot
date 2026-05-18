import database as db

if __name__ == '__main__':
    db.init_db([])
    user1 = 111111111
    user2 = 222222222
    chat_id = 99999
    title = 'Единственная корона'
    issuer = 8436225978
    print('Issuing first epic...')
    a1 = db.add_award(user1, chat_id, title, issuer, emoji='👑', description='Epic crown', rarity='epic')
    print('first_award_id ->', a1)
    print('Issuing second epic (should fail with -1)...')
    a2 = db.add_award(user2, chat_id, title, issuer, emoji='👑', description='Epic crown', rarity='epic')
    print('second_award_id ->', a2)
