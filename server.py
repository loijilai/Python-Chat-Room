import socket
import os
import threading
from dotenv import load_dotenv
import ssl
import json

from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    Integer,
    String,
)
from utils import hash_password, Message
from typing import Optional, Any
import traceback


load_dotenv()


class RoomError(Exception):
    pass


class MessageFactory:
    @staticmethod
    def ok(
        type: str, data: Optional[dict[str, Any]] = None, message: Optional[str] = None
    ) -> dict:
        return Message(type=type, status="ok", message=message, data=data).to_dict()

    @staticmethod
    def error(type: str, message: str) -> dict:
        return Message(type=type, status="error", message=message).to_dict()

    @staticmethod
    def push():
        pass


class ChatData:
    def __init__(self):
        self.online_users = {}  # username -> socket
        self.chatrooms = {"lobby": []}  # room_name -> [user1, user2, ...]
        self.chatrooms["example"] = []  # for demo
        self.lock = threading.RLock()

        DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+pysqlite:///chatapp.db")
        self.engine = create_engine(DATABASE_URL)
        metadata_obj = MetaData()
        self.users = Table(
            "users",
            metadata_obj,
            Column("id", Integer, primary_key=True),
            Column("username", String, nullable=False),
            Column("password", String, nullable=False),
        )
        metadata_obj.create_all(self.engine)

    def is_registered(self, username: str):
        stmt = self.users.select().where(self.users.c.username == username)
        with self.engine.connect() as conn:
            result = conn.execute(stmt).fetchone()
            return result is not None

    def add_user(self, username, password):
        stmt = self.users.insert().values(
            username=username, password=hash_password(password)
        )
        with self.engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()

    def check_password(self, username, password):
        stmt = self.users.select().where(self.users.c.username == username)
        with self.engine.connect() as conn:
            result = conn.execute(stmt).fetchone()
            return result.password == hash_password(password) if result else False

    def add_online_user(self, username, socket):
        with self.lock:
            self.online_users[username] = socket

    def logout(self, username, chatroom):
        with self.lock:
            if username:
                self.online_users.pop(username, None)
            if chatroom and chatroom in self.chatrooms:
                if username in self.chatrooms[chatroom]:
                    self.chatrooms[chatroom].remove(username)

    def enter_room(self, username, destination, source=None):
        with self.lock:
            if source and source not in self.chatrooms:
                raise RoomError(f"Source room {source} not found")

            if destination not in self.chatrooms:
                raise RoomError(f"Destination room {destination} not found")

            if username in self.chatrooms[destination]:
                raise RoomError(f"You are already in {destination}")

            if source and username in self.chatrooms[source]:
                self.chatrooms[source].remove(username)
            self.chatrooms[destination].append(username)

    def create_room(self, room_name):
        with self.lock:
            if room_name in self.chatrooms:
                raise RoomError(f"{room_name} already exists")
            self.chatrooms[room_name] = []

    def get_room_users(self, room_name) -> list:
        with self.lock:
            return list(self.chatrooms.get(room_name, []))

    def get_socket(self, username):
        with self.lock:
            return self.online_users.get(username, None)

    def get_room_info(self, room_name=None):
        with self.lock:
            if not room_name:
                # return a copy insead of the object itself
                return {room: list(users) for room, users in self.chatrooms.items()}
            if room_name not in self.chatrooms:
                return {room_name: []}
            return {room_name: list(self.chatrooms[room_name])}


class ClientHandler:
    def __init__(self, conn, addr, chat_data: ChatData):
        self.conn = conn
        self.addr = addr
        self.username = None
        self.chatroom = None
        self.state = "auth"
        self.active = True
        self.chat_data = chat_data

    def run(self):
        try:
            while self.active:
                if self.state == "auth":
                    self.state = self.auth()
                elif self.state == "lobby":
                    self.state = self.lobby()
                elif self.state == "chat":
                    self.state = self.chat()
                else:
                    print("Unknown state")
                    break
        except Exception as e:
            print(f"run error {e}")
            traceback.print_exc()
        finally:
            last_username = self.username
            last_room = self.chatroom
            self.chat_data.logout(last_username, last_room)
            if last_username:
                self.notify_lobby_state()
                if last_room and last_room != "lobby":
                    self.notify_room_state(last_room)
            self.conn.close()
            self.active = False
            print(f"{last_username} cleanup")

    def send(self, message_dict, socket=None):
        try:
            data = json.dumps(message_dict).encode("utf-8")
            header = len(data).to_bytes(4, byteorder="big")
            target = self.conn if socket is None else socket
            target.sendall(header + data)
        except Exception as e:
            print(f"send error {e}")
            self.active = False

    def recv(self) -> str | None:
        header = self.recv_exactly(4)
        if header is None:
            return None
        length = int.from_bytes(header, "big")
        payload = self.recv_exactly(length)
        if payload is None:
            return None
        return json.loads(payload.decode("utf-8"))

    def recv_exactly(self, n):
        buffer = b""
        try:
            while len(buffer) < n:
                data = self.conn.recv(n - len(buffer))
                if not data:
                    self.active = False
                    return None
                buffer += data
            return buffer
        except Exception as e:
            print(f"recv error {e}")
            self.active = False

    def notify_lobby_state(self):
        info = self.chat_data.get_room_info()
        for username in self.chat_data.get_room_users("lobby"):
            socket = self.chat_data.get_socket(username)
            if socket:
                self.send(MessageFactory.ok("list", info), socket)

    def notify_room_state(self, room_name):
        if not room_name:
            return
        info = self.chat_data.get_room_info(room_name)
        for username in self.chat_data.get_room_users(room_name):
            socket = self.chat_data.get_socket(username)
            if socket:
                self.send(MessageFactory.ok("list_room", info), socket)

    def send_message(self, sender, receiver, text):
        if receiver == "public":
            room_users = self.chat_data.get_room_users(self.chatroom)
            for username in room_users:
                socket = self.chat_data.get_socket(username)
                self.send(
                    MessageFactory.ok(
                        "msg", {"to": "public", "from": sender, "text": text}
                    ),
                    socket,
                )
        else:
            if receiver not in self.chat_data.get_room_users(self.chatroom):
                self.send(
                    MessageFactory.error(
                        "msg", message=f"{receiver} not in {self.chatroom}"
                    )
                )
                return "chat"
            socket = self.chat_data.get_socket(receiver)
            if socket:
                self.send(
                    MessageFactory.ok(
                        "msg", {"to": receiver, "from": self.username, "text": text}
                    ),
                    socket,
                )
                # send one copy to sender
                self.send(
                    MessageFactory.ok(
                        "msg",
                        {"to": self.username, "from": self.username, "text": text},
                    )
                )
            else:
                self.send(MessageFactory.error("msg", message=f"{receiver} not exists"))
            pass

    def auth(self):
        request = self.recv()
        if request is None:
            return "auth"
        msg = Message.model_validate(request)
        print(msg)
        if msg.data is None:
            return "auth"
        username = msg.data["username"]
        password = msg.data["password"]
        if msg.type == "register":
            if self.chat_data.is_registered(username):
                self.send(
                    MessageFactory.error(
                        "register", "Username already in use, try another one"
                    )
                )
            else:
                self.chat_data.add_user(username, password)
                self.send(
                    MessageFactory.ok(
                        "register", message="Register successfully! You can now login"
                    )
                )

        elif msg.type == "login":
            if not self.chat_data.is_registered(username):
                self.send(
                    MessageFactory.error(
                        "login", "Username not exists, try register first"
                    )
                )
                return "auth"
            if not self.chat_data.check_password(username, password):
                self.send(MessageFactory.error("login", "Invalid password"))
                return "auth"
            self.send(
                MessageFactory.ok(
                    "login",
                    {"username": f"{username}", "chatroom": "lobby"},
                    "Login successful",
                )
            )
            self.chat_data.add_online_user(username, self.conn)
            self.chat_data.enter_room(
                username, destination="lobby", source=self.chatroom
            )
            self.username = username
            self.chatroom = "lobby"
            return "lobby"
        else:
            print(f"Invalid command: {msg.to_dict()}")

        return "auth"

    def lobby(self):
        self.notify_lobby_state()
        request = self.recv()
        if request is None:
            return "lobby"
        msg = Message.model_validate(request)
        print(msg)
        if msg.type == "list":
            info = self.chat_data.get_room_info()
            self.send(MessageFactory.ok("list", info))
        elif msg.type == "enter" and msg.data is not None:
            room_name = msg.data["room"]
            try:
                self.chat_data.enter_room(
                    self.username, destination=room_name, source=self.chatroom
                )
                self.chatroom = room_name
                self.send(
                    MessageFactory.ok(
                        "enter",
                        data={"username": self.username, "room": self.chatroom},
                        message=f"Welcome to {self.chatroom}",
                    )
                )
                self.notify_lobby_state()
                return "chat"
            except RoomError as e:
                self.send(MessageFactory.error("enter", message=str(e)))
        elif msg.type == "create" and msg.data is not None:
            room_name = msg.data["room"]
            try:
                self.chat_data.create_room(room_name)
                self.send(
                    MessageFactory.ok(
                        "create", message=f"{room_name} created successfully"
                    )
                )
                self.notify_lobby_state()
            except RoomError as e:
                self.send(MessageFactory.error("create", message=str(e)))
        elif msg.type == "logout":
            self.chat_data.logout(self.username, self.chatroom)
            self.send(
                MessageFactory.ok(
                    "logout", message=f"{self.username} logout successfully"
                )
            )
            self.notify_lobby_state()
            self.username = None
            self.chatroom = None
            return "auth"
        else:
            print(f"Invalid command: {msg.to_dict()}")
        return "lobby"

    def chat(self):
        self.notify_room_state(self.chatroom)
        request = self.recv()
        if request is None:
            return "chat"
        msg = Message.model_validate(request)
        print(msg)
        if msg.type == "exit":
            try:
                self.chat_data.enter_room(
                    self.username, destination="lobby", source=self.chatroom
                )
                self.send(
                    MessageFactory.ok(
                        "exit", message=f"Exit {self.chatroom}, back to lobby"
                    )
                )
                self.notify_room_state(self.chatroom)
                self.chatroom = "lobby"
                return "lobby"
            except RoomError as e:
                self.send(MessageFactory.error("exit", str(e)))

            return "lobby"
        elif msg.type == "list":
            info = self.chat_data.get_room_info(self.chatroom)
            self.send(MessageFactory.ok("list_room", info))
        elif msg.type == "msg":
            if msg.data is None:
                return
            text = msg.data["text"]
            sender = msg.data["from"]
            receiver = msg.data["to"]

            self.send_message(sender, receiver, text)
        else:
            print(f"Invalid command: {msg.to_dict()}")
        return "chat"


def handle_client(conn, addr, chat_data: ChatData):
    handler = ClientHandler(conn, addr, chat_data)
    handler.run()


def main():
    host = os.getenv("HOST")
    port = int(os.getenv("PORT", "65432"))
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen()
    print(f"Server start listening on ({host}, {port})...")

    chat_data = ChatData()

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile="server.crt", keyfile="server.key")

    while True:
        try:
            conn, addr = server.accept()
            sconn = context.wrap_socket(conn, server_side=True)
            print(f"Connected by {addr}")
            thread = threading.Thread(
                target=handle_client, args=(sconn, addr, chat_data)
            )
            thread.start()
        except KeyboardInterrupt:
            print("Server ctrl+c exit")
            server.close()
            break
        except Exception as e:
            print(f"Server unexpected error: {e}")


if __name__ == "__main__":
    main()
