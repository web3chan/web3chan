import asyncio

import databases
import orm

from web3chan import config


database = databases.Database(config.DATABASE)
models = orm.ModelRegistry(database=database)


class Instance(orm.Model):
    tablename = "instances"
    registry = models
    fields = {
        "id": orm.Integer(primary_key=True),
        "base_url": orm.String(max_length=200, unique=True),
        "client_id": orm.String(max_length=43),
        "client_secret": orm.String(max_length=43),
    }


class Board(orm.Model):
    tablename = "boards"
    registry = models
    fields = {
        "id": orm.Integer(primary_key=True),
        "name": orm.String(max_length=200, unique=True),
        "instance": orm.ForeignKey(Instance),
        "access_token": orm.String(max_length=43),
        "enabled": orm.Boolean(),
        "streaming": orm.Boolean(),
        "autofollow": orm.Boolean(),
        "replies": orm.Boolean()
    }
