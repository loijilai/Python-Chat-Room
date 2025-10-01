import socket
import os
import threading
from dotenv import load_dotenv
import ssl

from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    Integer,
    String,
)


load_dotenv()


class RoomError(Exception):
    pass


class ChatData:
    def __init__(self):
        self.online_users = {}  # username -> socket
        self.chatrooms = {"lobby": []}  # room_name -> [user1, user2, ...]
        self.lock = threading.RLock()

        DATABASE_URL = os.getenv("DATABASE_URL")
        self.engine = create_engine(DATABASE_URL, echo=True)
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
        stmt = self.users.insert().values(username=username, password=password)
        with self.engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()

    def check_password(self, username, password):
        stmt = self.users.select().where(self.users.c.username == username)
        with self.engine.connect() as conn:
            result = conn.execute(stmt).fetchone()
            return result.password == password if result else False

    def add_online_user(self, username, socket):
        with self.lock:
            self.online_users[username] = socket

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

    def get_room_users(self, room_name):
        with self.lock:
            return self.chatrooms.get(room_name, [])

    def get_socket(self, username):
        with self.lock:
            return self.online_users.get(username, None)

    def get_room_info(self, room_name=None):
        lines = []
        with self.lock:
            if not room_name:
                for room_name, users in self.chatrooms.items():
                    lines.append(f"Room: {room_name}")
                    for user in users:
                        lines.append(f"  - {user}")
                    lines.append("")
            else:
                lines.append(f"Your current room: {room_name}")
                for user in self.chatrooms[room_name]:
                    lines.append(f"  - {user}")
                lines.append("")
        return "\n" + "\n".join(lines)


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
        finally:
            print(f"{self.username} cleanup")

    def send(self, text, socket=None):
        try:
            target = self.conn if socket is None else socket
            target.sendall(text.encode("utf-8"))
        except Exception as e:
            print(f"send error {e}")
            self.active = False

    def recv(self) -> str | None:
        try:
            data = self.conn.recv(1024)
            if not data:
                self.active = False
                return None
            return data.decode("utf-8").strip()
        except Exception as e:
            print(f"recv error {e}")
            self.active = False

    def broadcast(self, text):
        room_users = self.chat_data.get_room_users(self.chatroom)
        for username in room_users:
            socket = self.chat_data.get_socket(username)
            self.send(f"{self.username}: {text}", socket)

    def auth(self):
        self.send("\nType 'login' or 'register' to use the chatroom")
        cmd = self.recv()
        if cmd is None:
            return "auth"
        cmd = cmd.lower()
        if cmd == "register":
            self.send("Enter your username:")
            username = self.recv()
            if username is None:
                return "auth"
            if self.chat_data.is_registered(username):
                self.send("Username already in use, try another one")
                return "auth"

            self.send("Enter your password:")
            password = self.recv()
            if password is None:
                return "auth"
            self.chat_data.add_user(username, password)
            self.send("Register successfully! You can now login")

        elif cmd == "login":
            self.send("Enter your username:")
            username = self.recv()
            if username is None:
                return "auth"
            if not self.chat_data.is_registered(username):
                self.send("Username not exists, try register first")
                return "auth"
            self.send("Enter your password:")
            password = self.recv()
            if password is None:
                return "auth"
            if not self.chat_data.check_password(username, password):
                self.send("Wrong password!")
                return "auth"
            self.send("Login successfully! Redirecting to the lobby")
            self.chat_data.add_online_user(username, self.conn)
            self.chat_data.enter_room(
                username, destination="lobby", source=self.chatroom
            )
            self.username = username
            self.chatroom = "lobby"
            return "lobby"
        else:
            self.send(f"Invalid command: {cmd}")

        return "auth"

    def lobby(self):
        self.send("\nCommand: 'list', 'enter <room_name>', 'create <room_name>'")
        cmd = self.recv()
        if cmd is None:
            return "lobby"
        cmd = cmd.lower()
        if cmd == "list":
            info = self.chat_data.get_room_info()
            self.send(info)
        elif cmd.startswith("enter"):
            _, room_name = cmd.split(" ")
            try:
                self.chat_data.enter_room(
                    self.username, destination=room_name, source=self.chatroom
                )
                self.chatroom = room_name
                self.send(f"Welcome to {room_name}")
                return "chat"
            except RoomError as e:
                self.send(str(e))
        elif cmd.startswith("create"):
            _, room_name = cmd.split(" ")
            try:
                self.chat_data.create_room(room_name)
                self.send(f"{room_name} created successfully")
            except RoomError as e:
                self.send(str(e))
        else:
            self.send(f"Invalid command: {cmd}")
        print(f"{self.username}: {cmd}")
        return "lobby"

    def chat(self):
        # self.send("Command: 'exit', 'list', 'msgall <text>', 'msg <username> <text>'")
        cmd = self.recv()
        if cmd is None:
            return "chat"
        if cmd.lower().startswith("exit"):
            try:
                self.chat_data.enter_room(
                    self.username, destination="lobby", source=self.chatroom
                )
                self.send(f"Exit {self.chatroom}, back to lobby")
                self.chatroom = "lobby"
                return "lobby"
            except RoomError as e:
                self.send(str(e))

            return "lobby"
        elif cmd.lower().startswith("list"):
            info = self.chat_data.get_room_info(self.chatroom)
            self.send(info)
        elif cmd.lower().startswith("msgall"):
            _, text = cmd.split(" ")  # TODO
            self.broadcast(text)
        elif cmd.lower().startswith("msg"):
            _, username, text = cmd.split(" ")  # TODO
            if username not in self.chat_data.get_room_users(self.chatroom):
                self.send(f"{username} not in {self.chatroom}")
                return "chat"
            socket = self.chat_data.get_socket(username)
            if socket:
                self.send(f"{self.username}: {text}", socket)
            else:
                self.send(f"{username} not exists")
        else:
            self.send(f"Invalid command: {cmd}")
        return "chat"


def handle_client(conn, addr, chat_data: ChatData):
    handler = ClientHandler(conn, addr, chat_data)
    handler.run()


def main():
    host = os.getenv("HOST")
    port = int(os.getenv("PORT"))
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
