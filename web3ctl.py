#!/usr/bin/python3
import os
import sys
import asyncio
import argparse
import json

RPC_ADDRESS = os.getenv("WEB3CHAN_RPC_ADDRESS", "127.0.0.1:18166")


def fatal_error(message):
    print(f"ERROR: {message}")
    sys.exit(2)

def print_response(args, response_data):
    response = json.loads(response_data.decode())
    if args.json:
        print(response_data.decode())
        return

    if "error" in response:
        fatal_error(response['error']['message'])
    elif "result" in response:
        if type(response["result"]) == str and response["result"] == "ok":
            print("OK")
        elif args.command == "list_boards":
            print("name\t\t\t\tenabled?\trunning?\tstreaming\tautofollow\treplies")
            for b in response["result"]:
                print("\t\t".join([str(v) for v in b]))
        elif args.command == "mastoapi":
            print(json.dumps(response["result"], indent=1))
        else:
            print(response["result"])
    else:
        print(response)


async def main():
    host, port = RPC_ADDRESS.split(":")
    parser = argparse.ArgumentParser(description="Utility to control web3chan daemon", epilog="Use 'help' command to see all available commands")
    parser.add_argument("command")
    parser.add_argument("args", nargs="*")
    parser.add_argument("-k", "--kwargs", action="extend", nargs="*")
    parser.add_argument('-j', '--json', action='store_true')
    args = parser.parse_args()

    request = {"jsonrpc": "2.0", "id": 420,
               "method": args.command, "params": {}}
    if args.args:
        request["params"]["args"] = args.args
    if args.kwargs:
        request["params"]["kwargs"] = {}
        for token in args.kwargs:
            try:
                k, v = token.split("=", 1)
                request["params"]["kwargs"][k] = v
            except Exception as e:
                fatal_error(f"invalid kwargs: {type(e)}, {e}")

    try:
        reader, writer = await asyncio.open_connection(host, int(port))
    except ConnectionRefusedError as e:
        fatal_error(f"can't connect to web3chan daemon: {e}")

    writer.write(json.dumps(request).encode())
    writer.write("\n".encode())
    await writer.drain()

    response_data = await reader.read()
    writer.close()
    await writer.wait_closed()

    print_response(args, response_data)

if __name__ == "__main__":
    asyncio.run(main())
