import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import socket
import os
import threading
from dotenv import load_dotenv
import ssl
import json
from utils import Message
from typing import Optional, Any, Dict
import queue

load_dotenv()

host = os.getenv("HOST")
port = int(os.getenv("PORT", "65432"))


class MessageFactory:
    @staticmethod
    def create(type: str, data: Optional[dict[str, Any]] = None) -> dict:
        return Message(type=type, data=data).to_dict()


class ServerHandler:
    def __init__(self):
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.check_hostname = False  # close for demo
        context.verify_mode = ssl.CERT_NONE  # close for demo
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ss = context.wrap_socket(s, server_hostname=host)
        ss.connect((host, port))

        self.socket = ss
        self.q = queue.Queue()
        print("Connected to server!")

    def send(self, message_dict):
        try:
            data = json.dumps(message_dict).encode("utf-8")
            header = len(data).to_bytes(4, byteorder="big")
            self.socket.sendall(header + data)
        except Exception as e:
            print(f"send error {e}")
            self.active = False

    def recv(self) -> Dict[str, Any] | None:
        header = self.recv_exactly(4)
        if header is None:
            print("Server closed!")
            return None
        length = int.from_bytes(header, "big")
        payload = self.recv_exactly(length)
        if payload is None:
            print("Server closed!")
            return None
        return json.loads(payload.decode("utf-8"))

    def recv_exactly(self, n):
        buffer = b""
        try:
            while len(buffer) < n:
                data = self.socket.recv(n - len(buffer))
                if not data:
                    self.active = False
                    return None
                buffer += data
            return buffer
        except Exception as e:
            print(f"recv error {e}")
            self.active = False


class LoginPage(ttk.Frame):
    def __init__(self, parent, app, server_handler: ServerHandler):
        super().__init__(parent, padding="20")
        self.app = app
        self.server_handler = server_handler

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()

        ttk.Label(self, text="Username:").grid(column=0, row=0, sticky=tk.W, pady=5)
        ttk.Entry(self, textvariable=self.username_var, width=30).grid(
            column=1, row=0, sticky=tk.W + tk.E, pady=5
        )

        ttk.Label(self, text="Password:").grid(column=0, row=1, sticky=tk.W, pady=5)
        ttk.Entry(self, textvariable=self.password_var, width=30, show="*").grid(
            column=1, row=1, sticky=tk.W + tk.E, pady=5
        )

        ttk.Button(self, text="Login", command=self.on_login).grid(
            column=0, row=2, sticky=tk.E, pady=10, padx=5
        )
        ttk.Button(self, text="Register", command=self.on_register).grid(
            column=1, row=2, sticky=tk.W, pady=10, padx=5
        )

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)

    def on_login(self):
        username = self.username_var.get()
        password = self.password_var.get()
        self.server_handler.send(
            MessageFactory.create("login", {"username": username, "password": password})
        )
        json_data = self.server_handler.recv()
        if json_data is None:
            self.app.on_server_disconnect()
            return
        msg = Message.model_validate(json_data)
        if not msg.type == "login":
            print(f"Receive error response: {msg.type}")
            return

        if msg.status == "ok" and msg.data is not None:
            self.app.show_lobby_page(msg.data["username"], msg.data["chatroom"])
        elif msg.status == "error":
            messagebox.showerror("Error", msg.message)

    def on_register(self):
        username = self.username_var.get()
        password = self.password_var.get()
        self.server_handler.send(
            MessageFactory.create(
                "register", {"username": username, "password": password}
            )
        )
        json_data = self.server_handler.recv()
        if json_data is None:
            self.app.on_server_disconnect()
            return

        msg = Message.model_validate(json_data)
        if not msg.type == "register":
            print(f"Receive error response: {msg.type}")
            return

        if msg.status == "ok":
            messagebox.showinfo("Register", msg.message)
        elif msg.status == "error":
            messagebox.showerror("Error", msg.message)


class ChatRoomPage(ttk.Frame):
    def __init__(self, parent, app, username, room_name):
        super().__init__(parent, padding="20")
        self.app = app
        ttk.Label(
            self, text=f"Chat Room: {room_name}", font=("Arial", 14, "bold")
        ).pack(pady=10)
        ttk.Label(self, text=f"You are {username}").pack(pady=5)
        ttk.Button(self, text="Back to Lobby", command=self.on_back).pack(pady=20)

    def on_back(self):
        self.app.show_lobby_page(self.app.current_username, self.app.current_chatroom)


class LobbyPage(ttk.Frame):
    def __init__(self, parent, app, username, chatroom, server_handler: ServerHandler):
        super().__init__(parent, padding="20")
        self.app = app
        self.username = username
        self.chatroom = chatroom
        self.server_handler = server_handler

        ttk.Label(
            self,
            text=f"Welcome, {username}! You are in room: {chatroom}",
            font=("Arial", 14, "bold"),
        ).grid(column=0, row=0, columnspan=2, pady=10)

        # ---- Create room ----
        self.create_room_var = tk.StringVar()
        ttk.Label(self, text="Create Room:").grid(column=0, row=1, sticky=tk.W, pady=5)
        ttk.Entry(self, textvariable=self.create_room_var, width=25).grid(
            column=1, row=1, pady=5, sticky=tk.W + tk.E
        )
        ttk.Button(self, text="Create", command=self.on_create_room).grid(
            column=2, row=1, padx=5
        )

        # ---- Enter room ----
        self.enter_room_var = tk.StringVar()
        ttk.Label(self, text="Enter Room:").grid(column=0, row=2, sticky=tk.W, pady=5)
        ttk.Entry(self, textvariable=self.enter_room_var, width=25).grid(
            column=1, row=2, pady=5, sticky=tk.W + tk.E
        )
        ttk.Button(self, text="Enter", command=self.on_enter_room).grid(
            column=2, row=2, padx=5
        )

        # ---- User list ----
        self.user_tree = ttk.Treeview(self)
        self.user_tree.heading("#0", text="Rooms / Users", anchor="w")
        self.user_tree.grid(column=0, row=3, columnspan=3, sticky="nsew")

        ttk.Button(self, text="Refresh", command=self.refresh_user_list).grid(
            column=2, row=5, sticky=tk.E, pady=10
        )

        # ---- Logout ----
        ttk.Button(self, text="Logout", command=self.on_logout).grid(
            column=0, row=5, pady=15, sticky=tk.W
        )

        self.columnconfigure(1, weight=1)
        self.rowconfigure(4, weight=1)
        self.refresh_user_list()

    # === UI Event Handlers ===
    def on_create_room(self):
        room_name = self.create_room_var.get()
        if not room_name:
            messagebox.showwarning("Warning", "Please enter a room name.")
            return
        self.server_handler.send(MessageFactory.create("create", {"room": room_name}))
        json_data = self.server_handler.recv()
        if json_data is None:
            self.app.on_server_disconnect()
            return
        msg = Message.model_validate(json_data)
        if msg.status == "ok":
            messagebox.showinfo("Create Room", msg.message)
        else:
            messagebox.showwarning("Create Room", msg.message)

    def on_enter_room(self):
        room_name = self.enter_room_var.get()
        if not room_name:
            messagebox.showwarning("Warning", "Please enter a room name.")
            return
        self.server_handler.send(MessageFactory.create("enter", {"room": room_name}))
        json_data = self.server_handler.recv()
        if json_data is None:
            self.app.on_server_disconnect()
            return
        msg = Message.model_validate(json_data)

        if msg.status == "ok":
            messagebox.showinfo("Enter Room", msg.message)
            self.app.show_chatroom_page(self.username, room_name)
        else:
            messagebox.showwarning("Enter Room", msg.message)

    def on_logout(self):
        self.server_handler.send(MessageFactory.create("logout"))
        json_data = self.server_handler.recv()
        msg = Message.model_validate(json_data)
        messagebox.showinfo("Logout", msg.message)
        self.app.show_login_page()

    def refresh_user_list(self):
        for item in self.user_tree.get_children():
            self.user_tree.delete(item)

        server_handler.send(MessageFactory.create("list"))
        json_data = server_handler.recv()
        if json_data is None:
            self.app.on_server_disconnect()
            return
        print(json_data)

        for room, users in json_data.items():
            room_id = self.user_tree.insert("", "end", text=f"Room: {room}")
            for user in users:
                self.user_tree.insert(room_id, "end", text=f"- {user}")


class App(tk.Tk):
    def __init__(self, server_handler: ServerHandler):
        super().__init__()
        self.server_handler = server_handler
        self.title("Chat Client")

        self.current_page = None
        self.current_username = None
        self.current_chatroom = None
        self.show_login_page()

    def on_server_disconnect(self):
        messagebox.showerror("Disconnected", "Server connection lost. Closing app...")
        self.after(100, self.destroy)

    def show_login_page(self):
        if self.current_page:
            self.current_page.destroy()
        self.current_page = LoginPage(self, self, server_handler)
        self.current_page.pack(fill="both", expand=True)

    def show_lobby_page(self, username, chatroom):
        if self.current_page:
            self.current_page.destroy()
        self.current_username = username
        self.current_chatroom = chatroom
        self.current_page = LobbyPage(self, self, username, chatroom, server_handler)
        self.current_page.pack(fill="both", expand=True)

    def show_chatroom_page(self, username, room_name):
        if self.current_page:
            self.current_page.destroy()
        self.current_page = ChatRoomPage(self, self, username, room_name)
        self.current_page.pack(fill="both", expand=True)


if __name__ == "__main__":
    server_handler = ServerHandler()
    app = App(server_handler)
    app.mainloop()
