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
from typing import Optional, Any

load_dotenv()

host = os.getenv("HOST")
port = int(os.getenv("PORT"))


class MessageFactory:
    @staticmethod
    def create(type: str, data: Optional[dict[str, Any]] = None) -> dict:
        return Message(type=type, data=data).to_dict()


def recv_from_server(s):
    while True:
        try:
            data = s.recv(1024).decode()
            if not data:
                print("Server closed connection.")
                break
            print(f"[Server] {data}")
        except OSError as e:
            print(f"Unexpected error: {e}")
            break


class ServerHandler:
    def __init__(self):
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.check_hostname = False  # close for demo
        context.verify_mode = ssl.CERT_NONE  # close for demo
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ss = context.wrap_socket(s, server_hostname=host)
        ss.connect((host, port))

        self.socket = ss
        print("Connected to server!")

    def send(self, message_dict):
        try:
            data = json.dumps(message_dict).encode("utf-8")
            header = len(data).to_bytes(4, byteorder="big")
            self.socket.sendall(header + data)
        except Exception as e:
            print(f"send error {e}")
            self.active = False

    def recv(self) -> str | None:
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
            column=1, row=0, sticky=(tk.W, tk.E), pady=5
        )

        ttk.Label(self, text="Password:").grid(column=0, row=1, sticky=tk.W, pady=5)
        ttk.Entry(self, textvariable=self.password_var, width=30, show="*").grid(
            column=1, row=1, sticky=(tk.W, tk.E), pady=5
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
        msg = Message(**json_data)
        if not msg.type == "login":
            print(f"Receive error response: {msg.type}")
            return

        if msg.status == "ok":
            self.app.show_main_page(msg.data["username"], msg.data["chatroom"])
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
        msg = Message(**json_data)
        if not msg.type == "register":
            print(f"Receive error response: {msg.type}")
            return

        if msg.status == "ok":
            messagebox.showinfo("Register", msg.message)
        elif msg.status == "error":
            messagebox.showerror("Error", msg.message)


class MainPage(ttk.Frame):
    def __init__(self, parent, app, username, chatroom):
        super().__init__(parent, padding="20")
        self.app = app

        ttk.Label(self, text=f"Welcome, {username}! You are in room: {chatroom}").grid(
            column=0, row=0, pady=10
        )

        ttk.Button(self, text="Logout", command=self.on_logout).grid(column=0, row=1)

    def on_logout(self):
        self.app.show_login_page()


class App(tk.Tk):
    def __init__(self, server_handler: ServerHandler):
        super().__init__()
        self.server_handler = server_handler
        self.title("Chat Login")

        self.current_page = None
        self.show_login_page()

    def show_login_page(self):
        if self.current_page:
            self.current_page.destroy()
        self.current_page = LoginPage(self, self, server_handler)
        self.current_page.pack(fill="both", expand=True)

    def show_main_page(self, username, chatroom):
        if self.current_page:
            self.current_page.destroy()
        self.current_page = MainPage(self, self, username, chatroom)
        self.current_page.pack(fill="both", expand=True)


if __name__ == "__main__":
    server_handler = ServerHandler()
    # receive_thread = threading.Thread(target=recv_from_server, args=(ss,), daemon=True)
    # receive_thread.start()
    app = App(server_handler)
    app.mainloop()
