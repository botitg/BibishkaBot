import database as db

if __name__ == '__main__':
    db.init_db([])
    db.set_setting('ai_enabled', '0')
    print('Set ai_enabled ->', db.get_bool_setting('ai_enabled', False))
