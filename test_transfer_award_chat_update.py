import database as db

if __name__ == '__main__':
    db.init_db([])
    user1 = 111111111
    user2 = 222222222
    chat_id = 99999
    title = 'TransferChatTest'
    issuer = 8436225978
    print('Creating award with chat_id=', chat_id)
    a1 = db.add_award(user1, chat_id, title, issuer, emoji='🏅', description='Chat update test', rarity='rare')
    print('award_id ->', a1)
    print('Transferring award and updating chat_id to 55555')
    ok = db.transfer_award(a1, user2, new_chat_id=55555)
    print('transfer ok ->', ok)
    award = db.get_award(a1)
    print('award owner ->', award.get('user_id'))
    print('award chat_id ->', award.get('chat_id'))
