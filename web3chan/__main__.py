#!/usr/bin/env python3
import asyncio
import argparse

from web3chan.master import BotMaster
from web3chan import db

async def daemon(args):
    web3app = BotMaster()
    await web3app.start()

async def database(args):
    if args.database == 'create':
        await db.models.create_all()
    elif args.database == 'drop':
        await db.models.drop_all()
    
def main():
    parser = argparse.ArgumentParser(
        prog='web3chan', description='like 4chan, but in web3',
        epilog='BOTTOM TEXT')
    parser.add_argument('-d', '--daemon', action='store_true')
    parser.add_argument('--database', choices=['create', 'drop'])

    args = parser.parse_args()

    if args.database:
        asyncio.run(database(args))
    elif args.daemon:
        asyncio.run(daemon(args))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
