import asyncio
import json
import os
import aiohttp

API_BASE = "https://www.donationalerts.com/api/v1"

# from centrifuge import Client
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv("DA_USER_ID")
access_token = os.getenv("DA_ACCESS_TOKEN", "")

WS_URL = "wss://centrifugo.donationalerts.com/connection/websocket"


async def get_socket_token():
    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE}/user/oauth", headers=headers) as resp:
            resp.raise_for_status()
            return (await resp.json())["data"]["socket_connection_token"]


async def new_subscription(client_uid):
    headers = {"Authorization": f"Bearer {access_token}"}
    data = {"channels": [f"$alerts:donation_{client_id}"], "client": client_uid}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://www.donationalerts.com/api/v1/centrifuge/subscribe",
            json=data,
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            for channel in data['channels']:
                return channel['token']


"""
async def get_user_info():
    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE}/user/oauth", headers=headers) as resp:
            resp.raise_for_status()
            print(await resp.json())
"""


class BotClient:
    def __init__(
        self,
        connect_url=WS_URL,
    ):
        self.session_id: str | None = None
        self._socket = None
        self._reconnect_url: str | None = None
        self.connect_url = connect_url

    async def run_ws(self):
        connection_token = await get_socket_token()

        async with aiohttp.ClientSession() as session:
            print('ws open')
            self._socket = await session.ws_connect(
                self.connect_url,
                # reconnect_url already includes query params
            )

            data = {"params": {"token": connection_token}, "id": 1}
            await self._socket.send_json(data=data)

            welcome_message: aiohttp.WSMessage = await self._socket.receive_json()
            client_uid = welcome_message["result"]["client"]
            print('got client_uid')

            # подписались на меня
            
            print('subs on')
            new_fucking_token = await new_subscription(client_uid)

            # connect evetn

            connect_data = {
                "params": {
                    "channel": f"$alerts:donation_{client_id}",
                    "token": new_fucking_token,
                },
                "method": 1,
                "id": 2,
            }
            await self._socket.send_json(data=connect_data)
            print(await self._socket.receive_json())

            # client_uuid = welcome_message.data[0]['client']
            # print(client_uuid)
            async for mssg in self._socket:
                print("got new message: %s", mssg.data)

            return
            """
            event = typing.cast(
                "Mapping[str, typing.Any]",
                EventSchema().load(json.loads(welcome_message.data)),
            )
            await self.prokkcess_event(event)
            if not self.session_id:
                logger.warning("no session_id after welcome, reconnecting")
                connect_url = WS_URL
                is_reconnect = False
                continue

            backoff = 1.0


            async for mssg in self._socket:
                logger.info("got new message: %s", mssg.data)
                try:
                    event = typing.cast(
                        "Mapping[str, str]",
                        EventSchema().load(json.loads(mssg.data)),
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("cant load event %s", mssg.data, exc_info=e)
                    continue
                await self.process_event(event)
            """


async def main():
    # client = Client(address=address, token=access_token)
    channel = f"$alerts:donation_{client_id}"
    # "token": "<connection_token>"
    # await client.connect()
    # await asyncio.sleep(3)
    # print(client.state)
    # return
    # client.new_subscription(channel=channel)
    # await client.ready()
    bot = BotClient()
    await bot.run_ws()


if __name__ == "__main__":
    asyncio.run(main())
