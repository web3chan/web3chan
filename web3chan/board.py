import asyncio
import orjson
import logging

from contextlib import suppress

import websockets

from aroma.api import MastodonAPI, MastodonError

from web3chan import rpc, config


class BoardBot:
    """BoardBot worker"""
    def __init__(self, client, board):
        self.client = client
        self.board = board
        self.log = logging.getLogger(str(self))
        self.background_tasks = []
        self.last_notif_id = None
        self.notif_queue = asyncio.Queue()
        self.dismiss_queue = asyncio.Queue()
        self._fetcher_cooldown = config.FETCHER_COOLDOWN
        self.api = MastodonAPI(self.client, self.board.instance.base_url, access_token=self.board.access_token)
        self.account, self.instance = {}, {}
        self.following, self.followers = [], []

        self._notification_handlers = {
            "mention": self._mentioned,
            "follow": self._followed
        }


    def __str__(self):
        return f"BoardBot:{self.board.name}"

    async def start(self):
        try:
            # TODO: use asyncio.gather lmao
            self.account = await self.api.account_verify_credentials()
            self.instance = await self.api.instance()
            await self._update_relationships()
        except MastodonError as e:
            self.log.error(f"can't start: {type(e)}: {e}")
            return rpc.INTERNAL_ERROR

        self.log.debug(f"instance version: {self.instance['version']}")

        tasks = [self._relationships_updater(), self._notification_dismisser(), self._notification_handler(),
                 self._notification_fetcher()]

        if self.board.streaming:
            await self._start_streaming()

        for t in tasks:
            self.background_tasks.append(asyncio.create_task(t))

        self.log.info("started")
        return rpc.OK

    async def stop(self):
        for t in self.background_tasks:
            t.cancel()
            with suppress(asyncio.CancelledError):
                await t

        self.log.info("stopped")

    async def _update_relationships(self):
        self.log.debug("updating relationships")
        # TODO: use asyncio.gather lmao
        following = await self.api.get_all(
            self.api.account_following(self.account["id"], params={"limit": 50})
        )
        followers = await self.api.get_all(
            self.api.account_followers(self.account["id"], params={"limit": 50})
        )
        self.following = [a["id"] for a in following]
        self.followers = [a["id"] for a in followers]
        self.log.debug(f"{len(self.following)} following")
        self.log.debug(f"{len(self.followers)} followers")

    async def _relationships_updater(self):
        """Task that keeps relationships info up to date"""
        while True:
            await asyncio.sleep(config.RELATIONSHIPS_SYNCER_COOLDOWN)
            try:
                await self._update_relationships()
            except MastodonError as e:
                self.log.error(f"relationships_syncer: {type(e)}: {e}")

    async def _start_streaming(self):
        streaming_api = None
        if "urls" in self.instance and "streaming_api" in self.instance["urls"]:
            streaming_api = self.instance["urls"]["streaming_api"]
        else:
            self.log.warning("can't find streaming_api url")

        if "compatible" in self.instance["version"]:
            self.log.warning("pleroma's notification streaming is broken")

        self.log.debug(f"streaming_api = {streaming_api}")

        try:
            async with self.api.stream(streaming_api) as ws:
                await ws.ping()
            self.background_tasks.append(asyncio.create_task(self._stream(streaming_api)))
            self._fetcher_cooldown = config.FETCHER_COOLDOWN_WITH_STREAMING
        except Exception as e:
            self.log.error(f"streaming: can't start: {type(e)}: {e}")


    async def _stream(self, streaming_api):
        """Websocket stream task"""
        self.log.debug("streaming: starting")
        async for ws in self.api.stream(streaming_api):
            self.log.debug("stream: connected")

            try:
                await ws.send(orjson.dumps({"type": "subscribe", "stream": "user:notification"}))

                async for data in ws:
                    if type(data) != str:
                        self.log.error(f"stream: received invalid data type: {type(data)}: {data}")
                        continue

                    try:
                        event = orjson.loads(data)
                    except Exception as e:
                        self.log.error(f"stream: can't parse event: {type(e): {e}}")
                        continue

                    if "event" in event and event["event"] == "notification" and "payload" in event:
                        try:
                            notification = orjson.loads(event["payload"])
                        except Exception as e:
                            self.log.error(f"stream: can't parse payload: {type(e): {e}}")
                        else:
                            await self.notif_queue.put(notification)
                    else:
                        self.log.error(f"stream: invalid event: {event}")

            except websockets.ConnectionClosed:
                self.log.debug("stream: connection closed")
                continue

    async def _notification_dismisser(self):
        """Dismiss notifications"""
        while True:
            n = await self.dismiss_queue.get()
            self.log.debug(f"dismissing notification: {n['id']}")
            try:
                await self.api.notification_dismiss(n["id"])
            except MastodonError as e:
                self.log.error(f"notification_dismisser: {type(e)}: {e}")

    async def _notification_fetcher(self):
        """Fetch notifications periodically so we don't miss anything"""
        while True:
            self.log.debug("fetching notifications")
            try:
                notifs = await self.api.get_all(self.api.notifications(params={
                    "limit": 50, "since_id": self.last_notif_id
                }))
            except MastodonError as e:
                self.log.error(f"can't fetch notifications: {type(e)}: {e}")
            else:
                self.log.debug(f"fetched {len(notifs)} notifications")
                if notifs:
                    self.last_notif_id = notifs[-1]["id"]
                    for n in notifs:
                        await self.notif_queue.put(n)

            await asyncio.sleep(self._fetcher_cooldown)

    async def _notification_handler(self):
        """Main board logic"""
        while True:
            n = await self.notif_queue.get()

            self.log.debug(f"handling notification: {n['id']}")
            if "type" in n and n["type"] in self._notification_handlers:
                await self._notification_handlers[n["type"]](n)
            else:
                self.log.warning(f"unhandled notification: {n}")

            await self.dismiss_queue.put(n)

    async def _followed(self, n):
        self.log.debug(f"followed by {n['account']['acct']}")
        self.followers.append(n['account']['id'])

        if self.board.autofollow and not n['account']['locked']:
            try:
                relationship = await self.api.account_follow(n['account']['id'])
                if relationship["following"]:
                    self.following.append(n['account']['id'])
                    self.log.info(f"followed {n['account']['acct']}")
            except MastodonError as e:
                self.log.error(f"can't follow {n['account']['acct']}: {type(e)}: {e}")

    async def _mentioned(self, n):
        self.log.debug(f"mentioned by {n['account']['acct']}")

        is_fren = n["account"]["id"] in self.followers and n["account"]["id"] in self.following

        if is_fren and n["status"]["visibility"] == "public":
            status_id = n["status"]["id"]
            if self.board.replies and "in_reply_to_id" in n["status"] and n["status"]["in_reply_to_id"]:
                status_id = n["status"]["in_reply_to_id"]

            try:
                await self.api.status_reblog(status_id)
                self.log.info(f"reblogged {n['account']['acct']}/{status_id}")
            except MastodonError as e:
                self.log.error(f"can't reblog {n['account']['acct']}/{status_id}: {type(e)}: {e}")
