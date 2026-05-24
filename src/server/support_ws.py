import json
from typing import Dict, List
from fastapi import WebSocket

class SupportConnectionManager:
    def __init__(self):
        # Maps user_id to list of active websockets
        self.active_users: Dict[int, List[WebSocket]] = {}
        # List of active admin websockets
        self.active_admins: List[WebSocket] = []

    async def connect_user(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        if user_id not in self.active_users:
            self.active_users[user_id] = []
        self.active_users[user_id].append(websocket)
        # Notify admins that a user came online
        await self.broadcast_to_admins({"type": "user_status", "user_id": user_id, "status": "online"})

    def disconnect_user(self, websocket: WebSocket, user_id: int):
        if user_id in self.active_users:
            if websocket in self.active_users[user_id]:
                self.active_users[user_id].remove(websocket)
            if not self.active_users[user_id]:
                del self.active_users[user_id]
                # Notify admins that user went offline
                import asyncio
                asyncio.create_task(self.broadcast_to_admins({"type": "user_status", "user_id": user_id, "status": "offline"}))

    async def connect_admin(self, websocket: WebSocket):
        await websocket.accept()
        self.active_admins.append(websocket)
        # Notify all users that admin is online
        await self.broadcast_to_users({"type": "admin_status", "status": "online"})

    def disconnect_admin(self, websocket: WebSocket):
        if websocket in self.active_admins:
            self.active_admins.remove(websocket)
        if not self.active_admins:
            # Notify all users that admin went offline
            import asyncio
            asyncio.create_task(self.broadcast_to_users({"type": "admin_status", "status": "offline"}))

    async def send_to_user(self, user_id: int, message: dict):
        if user_id in self.active_users:
            for connection in self.active_users[user_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

    async def broadcast_to_admins(self, message: dict):
        for connection in self.active_admins:
            try:
                await connection.send_json(message)
            except Exception:
                pass

    async def broadcast_to_users(self, message: dict):
        for user_websockets in self.active_users.values():
            for connection in user_websockets:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

    def is_admin_online(self) -> bool:
        return len(self.active_admins) > 0

manager = SupportConnectionManager()
