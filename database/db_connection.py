import pymysql
from sqlalchemy import create_engine
from config.config import DB_CONFIG

def get_mysql_connection():
    return pymysql.connect(**DB_CONFIG)

def get_sqlalchemy_engine():
    url = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset={DB_CONFIG['charset']}"
    return create_engine(url)

if __name__ == "__main__":
    engine = get_sqlalchemy_engine()
    with engine.connect():
        print("✅数据库连接成功")
