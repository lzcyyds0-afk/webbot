from __future__ import annotations
from app.engine.models import WsMessage


class WsBroadcaster:
    async def emit(self, message: WsMessage) -> None:
        raise NotImplementedError


class SocketIoBroadcaster(WsBroadcaster):
    def __init__(self, sio: "socketio.AsyncServer") -> None:
        self._sio = sio

    async def emit(self, message: WsMessage) -> None:
        room = f"run_{message.run_id}"
        await self._sio.emit(
            "run_event",
            message.to_dict(),
            room=room,
        )


class NullBroadcaster(WsBroadcaster):
    async def emit(self, message: WsMessage) -> None:
        pass
