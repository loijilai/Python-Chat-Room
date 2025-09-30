import socket
import os
import threading
from dotenv import load_dotenv
from utils import format_room

load_dotenv()

users = {}  # username -> password
online_users = {}  # username -> socket
chatrooms = {"lobby": []}  # room_name -> [user1, user2, ...]


class ClientHandler:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr
        self.username = None
        self.chatroom = None
        self.state = "auth"
        self.active = True

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
            if socket is None:
                self.conn.sendall(text.encode("utf-8"))
            else:
                socket.sendall(text.encode("utf-8"))
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
        for username in chatrooms[self.chatroom]:
            socket = online_users[username]
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
            if username in users:
                self.send("Username already in use, try another one")
                return "auth"

            self.send("Enter your password:")
            password = self.recv()
            if password is None:
                return "auth"
            users[username] = password
            self.send("Register successfully! You can now login")

        elif cmd == "login":
            self.send("Enter your username:")
            username = self.recv()
            if username is None:
                return "auth"
            if username not in users:
                self.send("Username not exists, try login first")
                return "auth"
            self.send("Enter your password:")
            password = self.recv()
            if password is None:
                return "auth"
            if password != users[username]:
                self.send("Wrong password!")
                return "auth"
            self.send("Login successfully! You can now chat!")
            self.username = username
            online_users[username] = self.conn
            chatrooms["lobby"].append(username)
            return "lobby"

        return "auth"

    def lobby(self):
        info = format_room(chatrooms)
        self.send(info)
        self.send("Command: 'list', 'enter <room_name>', 'create <room_name>'")
        cmd = self.recv()
        if cmd is None:
            return "lobby"
        cmd = cmd.lower()
        if cmd == "list":
            info = format_room(chatrooms)
            self.send(info)
        elif cmd.startswith("enter"):
            _, room_name = cmd.split(" ")
            if room_name not in chatrooms:
                self.send(f"{room_name} not found")
            elif room_name == "lobby":
                self.send("you are already in lobby")
            else:
                self.chatroom = room_name
                self.send(f"Welcome to {self.chatroom}")
                chatrooms[room_name].append(self.username)
                chatrooms["lobby"].remove(self.username)
                return "chat"
        elif cmd.startswith("create"):
            _, room_name = cmd.split(" ")
            if room_name in chatrooms:
                self.send(f"{room_name} already exists")
            else:
                self.send(f"{room_name} created successfully")
                chatrooms[room_name] = []
        else:
            print(f"Unknown command {cmd}")
        print(f"{self.username}: {cmd}")
        return "lobby"

    def chat(self):
        # self.send("Command: 'exit', 'list', 'msgall <text>', 'msg <username> <text>'")
        cmd = self.recv()
        if cmd is None:
            return "chat"
        if cmd.lower().startswith("exit"):
            self.send(f"Exit {self.chatroom}, back to lobby")
            chatrooms[self.chatroom].remove(self.username)
            chatrooms["lobby"].append(self.username)
            self.chatroom = "lobby"
            return "lobby"
        elif cmd.lower().startswith("list"):
            info = format_room(chatrooms, self.chatroom)
            self.send(info)
        elif cmd.lower().startswith("msgall"):
            _, text = cmd.split(" ")
            self.broadcast(text)
        elif cmd.lower().startswith("msg"):
            _, username, text = cmd.split(" ")
            socket = online_users.get(username, None)
            if socket:
                self.send(f"{self.username}: {text}", socket)
            else:
                self.send(f"{username} not exists")
        return "chat"


def handle_client(conn, addr):
    handler = ClientHandler(conn, addr)
    handler.run()


def main():
    host = os.getenv("HOST")
    port = int(os.getenv("PORT"))
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen()
    print(f"Server start listening on ({host}, {port})...")

    # TODO: for debug
    users["abc"] = "123"
    users["bcd"] = "123"

    while True:
        try:
            conn, addr = server.accept()
            print(f"Connected by {addr}")
            thread = threading.Thread(target=handle_client, args=(conn, addr))
            thread.start()
        except KeyboardInterrupt:
            print("Server ctrl+c exit")
            server.close()
            break
        except Exception as e:
            print(f"Server unexpected error: {e}")


if __name__ == "__main__":
    main()
