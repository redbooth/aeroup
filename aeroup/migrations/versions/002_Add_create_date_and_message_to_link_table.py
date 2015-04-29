from sqlalchemy import *
from migrate import *


from migrate.changeset import schema
pre_meta = MetaData()
post_meta = MetaData()
link = Table('link', post_meta,
    Column('id', Integer, primary_key=True, nullable=False),
    Column('uuid', String(length=32), nullable=False),
    Column('receiver_id', Integer, nullable=False),
    Column('giver_email', Unicode(length=256)),
    Column('token', Unicode(length=256), nullable=False),
    Column('create_date', DateTime),
    Column('expiry_date', DateTime),
    Column('uploads_allowed', Integer),
    Column('uploads_performed', Integer),
    Column('message', Unicode(length=4096)),
)


def upgrade(migrate_engine):
    # Upgrade operations go here. Don't create your own engine; bind
    # migrate_engine to your metadata
    pre_meta.bind = migrate_engine
    post_meta.bind = migrate_engine
    post_meta.tables['link'].columns['create_date'].create()
    post_meta.tables['link'].columns['message'].create()


def downgrade(migrate_engine):
    # Operations to reverse the above upgrade go here.
    pre_meta.bind = migrate_engine
    post_meta.bind = migrate_engine
    post_meta.tables['link'].columns['create_date'].drop()
    post_meta.tables['link'].columns['message'].drop()
