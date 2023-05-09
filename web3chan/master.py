import asyncio
import orjson
import signal
import logging

import httpx
import orm.exceptions
from aroma.api import MastodonAPI, ResponseList

from web3chan import config, db, rpc
from web3chan.board import BoardBot


class BotMaster:
    __RPC_METHODS__ = ("help", "healthcheck",
                       "add_board", "remove_board", "list_boards", "toggle_board_option",
                       "start_board", "stop_board", "restart_board",
                       "mastoapi")

    def __init__(self):
        self.log = logging.getLogger("BotMaster")
        self.client = httpx.AsyncClient()
        self.stop_event = asyncio.Event()
        self.rpc_server = None
        self.slaves = {}

    async def start(self):
        """"Main function"""
        try:
            await db.database.connect()
        except Exception as e:
            self.log.error(f"can't connect to the database: {e}")
            return

        await self.start_slaves()
        await self.start_rpc()
        self.log.info("started")

        # catch sigint for graceful shutdown
        asyncio.get_running_loop().add_signal_handler(signal.SIGINT, self.stop_event.set)
        await self.stop_event.wait()

        await self.stop_rpc()
        await self.stop_slaves()
        await self.client.aclose()
        self.log.info("stopped")

    async def start_slaves(self):
        boards = await db.Board.objects.select_related("instance").filter(enabled=True).all()
        await asyncio.gather(*[self.start_board(b.name) for b in boards])

    async def stop_slaves(self):
        await asyncio.gather(*[self.stop_board(k) for k in self.slaves.keys()])

    async def start_rpc(self):
        self.rpc_server = asyncio.create_task(self.__rpc_server())

    async def stop_rpc(self):
        self.rpc_server.cancel()
        await self.rpc_server

    async def __rpc_server(self):
        """JSON-RPC server loop"""
        async def handle_rpc_client(reader, writer):
            request, response = None, {"jsonrpc": "2.0"}

            data = await reader.readline()
            try:
                request = orjson.loads(data)
            except Exception as e:
                self.log.error(f"RPC command parser exception: {(type(e))}: {e}")

            if request is None:
                response_data = rpc.PARSE_ERROR
            elif "jsonrpc" not in request or request["jsonrpc"] != "2.0" or "method" not in request or "id" not in request:
                response_data = rpc.INVALID_REQUEST
            else:
                response.update({"id": request["id"]})

                if request["method"] in self.__RPC_METHODS__:
                    args, kwargs = (), {}
                    if "params" in request:
                        if "args" in request["params"] and type(request["params"]["args"]) == list:
                            args = request["params"]["args"]
                        if "kwargs" in request["params"] and type(request["params"]["kwargs"]) == dict:
                            kwargs = request["params"]["kwargs"]

                    try:
                        self.log.debug(f"JSON-RPC method called: {request['method']} {args} {kwargs}")
                        response_data = await getattr(self, request["method"])(*args, **kwargs)
                    except Exception as e:
                        self.log.error(f"error while executing RPC method: {type(e)}: {e}")
                        response_data = rpc.INTERNAL_ERROR

                    if "result" in response_data:
                        if type(response_data["result"]) == ResponseList:
                            # TODO: json serialize ResponseList
                            response_data["result"] = response_data["result"].data

                else:
                    response_data = rpc.METHOD_NOT_FOUND

            response.update(response_data)
            writer.write(orjson.dumps(response))
            writer.close()
            await writer.wait_closed()

        host, port = config.RPC_ADDRESS.split(":")
        # TODO: handle bind exceptions
        server = await asyncio.start_server(handle_rpc_client, host, int(port))
        self.log.info(f"running JSON-RPC server on: {host}:{port}")

        try:
            async with server:
                await server.serve_forever()
        except asyncio.CancelledError:
            pass

    async def help(self):
        """help - returns this help message"""
        help_message = f"Available commands: {self.__RPC_METHODS__}"
        for command in self.__RPC_METHODS__:
            help_message = help_message + "\n\n" + str(getattr(self, command).__doc__)

        return {"result": help_message}

    async def healthcheck(self):
        """healthcheck - returns OK if daemon is running"""
        return rpc.OK

    async def add_board(self, name, base_url, email, password):
        """add_board

        arguments: name, base_url, email, password"""
        self.log.info(f"adding board: {name}, {base_url}")
        # check if a board with that name already exists
        board = await db.Board.objects.filter(name=name).first()
        if board:
            return rpc.INTERNAL_ERROR

        # get or create Instance object
        try:
            instance = await db.Instance.objects.get(base_url=base_url)
        except orm.exceptions.NoMatch:
            try:
                client_id, client_secret = await MastodonAPI.create_app(self.client, base_url)
            except Exception as e:
                self.log.error(f"add_board: can't create MastoAPI app: {type(e)}: {e}")
                return rpc.INTERNAL_ERROR
            else:
                instance = await db.Instance.objects.create(base_url=base_url, client_id=client_id,
                                                            client_secret=client_secret)

        # create Board object
        try:
            access_token = await MastodonAPI.log_in(
                self.client, instance.base_url,
                instance.client_id, instance.client_secret,
                username=email, password=password
            )
        except Exception as e:
            self.log.error(f"add_board: can't log in: {type(e)}: {e}")
            return rpc.INTERNAL_ERROR

        board = await db.Board.objects.create(name=name, instance=instance, access_token=access_token,
                                              enabled=True, streaming=config.STREAMING, 
                                              autofollow=config.AUTOFOLLOW, replies=config.REPLIES)
        return rpc.OK

    async def remove_board(self, name):
        """remove_board

        arguments: name"""
        try:
            board = await db.Board.objects.get(name=name)
            await board.delete()
        except orm.exceptions.NoMatch:
            return rpc.INTERNAL_ERROR
        else:
            return rpc.OK

    async def list_boards(self):
        """list_boards - returns a list of all boards hosted on this web3chan node"""
        boards = await db.Board.objects.all()
        return {"result": [(b.name, b.enabled, b.name in self.slaves, b.streaming, b.autofollow, b.replies) for b in boards]}

    async def toggle_board_option(self, name, field):
        """toggle_board_option - toggle boolean option in the database

        arguments: name, field"""
        try:
            board = await db.Board.objects.get(name=name)
        except orm.exceptions.NoMatch:
            return rpc.INTERNAL_ERROR
        try:
            value = getattr(board, field)
            assert type(value) == bool, "invalid option"
        except Exception as e:
            self.log.error(f"toggle_board_option: can't get value: {type(e)}: {e}")
            return rpc.INTERNAL_ERROR

        # update field with an opposite value
        updated_vals = {field: not value}
        await board.update(**updated_vals)
        return rpc.OK

    async def start_board(self, name):
        """start_board

        arguments: name"""
        self.log.debug(f"starting BoardBot: {name}")
        if name in self.slaves:
            return rpc.INTERNAL_ERROR
        try:
            board = await db.Board.objects.select_related("instance").get(name=name)
        except orm.exceptions.NoMatch:
            return rpc.INTERNAL_ERROR

        s = BoardBot(self.client, board)
        result = await s.start()
        if result == rpc.OK:
            self.slaves[board.name] = s

        return result

    async def stop_board(self, name):
        """stop_board

        arguments: name"""
        if name not in self.slaves:
            return rpc.INTERNAL_ERROR
        await self.slaves[name].stop()
        del self.slaves[name]
        return rpc.OK

    async def restart_board(self, name):
        """restart_board

        arguments: name"""
        await self.stop_board(name)
        return await self.start_board(name)

    async def mastoapi(self, name, method, *args, **kwargs):
        """mastoapi - execute MastoAPI method with a board account, returns API response

        arguments: name, method, *args, **kwargs"""
        try:
            board = await db.Board.objects.select_related("instance").get(name=name)
        except orm.exceptions.NoMatch:
            return rpc.INTERNAL_ERROR

        api = MastodonAPI(self.client, board.instance.base_url, access_token=board.access_token)

        if method not in dir(api):
            return rpc.INTERNAL_ERROR
        try:
            result = await getattr(api, method)(*args, **kwargs)
        except Exception as e:
            self.log.error(f"mastoapi: can't call method: {type(e)}: {e}")
            return rpc.INTERNAL_ERROR
        else:
            return {"result": result}
