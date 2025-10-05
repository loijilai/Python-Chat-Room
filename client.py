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
        self.receiver_thread = threading.Thread(target=self._recv_loop)
        self.receiver_thread.start()
        print("Connected to server!")

    def send(self, message_dict):
        try:
            data = json.dumps(message_dict).encode("utf-8")
            header = len(data).to_bytes(4, byteorder="big")
            self.socket.sendall(header + data)
        except Exception as e:
            print(f"send error {e}")
            self.active = False

    def _recv(self) -> Dict[str, Any] | None:
        header = self._recv_exactly(4)
        if header is None:
            print("Server closed!")
            return None
        length = int.from_bytes(header, "big")
        payload = self._recv_exactly(length)
        if payload is None:
            print("Server closed!")
            return None
        return json.loads(payload.decode("utf-8"))

    def _recv_exactly(self, n):
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

    def _recv_loop(self):
        while True:
            json_data = self._recv()
            if json_data is None:
                self.q.put({"type": "ServerClosed"})
                break
            msg = Message.model_validate(json_data)
            self.q.put(msg)

    def get_message(self):
        try:
            return self.q.get_nowait()
        except queue.Empty:
            return None


class Dispatcher:
    def __init__(self):
        self.handlers = {}

    def register_callback(self, message_type, callback):
        self.handlers[message_type] = callback

    def handle(self, msg):
        message_type = msg.type
        if message_type in self.handlers:
            self.handlers[message_type](msg)


class LoginPage(ttk.Frame):
    def __init__(
        self, parent, app, dispatcher: Dispatcher, server_handler: ServerHandler
    ):
        super().__init__(parent, padding="20")
        self.app = app
        self.server_handler = server_handler
        self.dispatcher = dispatcher

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

        ttk.Button(self, text="Login", command=self.ui_login_request).grid(
            column=0, row=2, sticky=tk.E, pady=10, padx=5
        )
        ttk.Button(self, text="Register", command=self.ui_register_request).grid(
            column=1, row=2, sticky=tk.W, pady=10, padx=5
        )

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)
        self.dispatcher.register_callback("register", self.server_register_ack)
        self.dispatcher.register_callback("login", self.server_login_act)

    # === UI Event Handlers ===
    def ui_login_request(self):
        username = self.username_var.get()
        password = self.password_var.get()
        self.server_handler.send(
            MessageFactory.create("login", {"username": username, "password": password})
        )

    def ui_register_request(self):
        username = self.username_var.get()
        password = self.password_var.get()
        self.server_handler.send(
            MessageFactory.create(
                "register", {"username": username, "password": password}
            )
        )

    # === Server Ack Handlers ===
    def server_register_ack(self, msg: Message):
        if msg.status == "ok":
            messagebox.showinfo("Register", msg.message)
        elif msg.status == "error":
            messagebox.showerror("Error", msg.message)

    def server_login_act(self, msg: Message):
        if msg.status == "ok" and msg.data is not None:
            self.app.show_lobby_page(msg.data["username"], msg.data["chatroom"])
        elif msg.status == "error":
            messagebox.showerror("Error", msg.message)


class ChatRoomPage(ttk.Frame):
    def __init__(
        self,
        parent,
        app,
        username,
        room_name,
        dispatcher: Dispatcher,
        server_handler: ServerHandler,
    ):
        super().__init__(parent, padding="20")
        self.app = app
        self.username = username
        self.room_name = room_name
        self.dispatcher = dispatcher
        self.server_handler = server_handler

        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True)

        # === 左側：聊天區域 ===
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        ttk.Label(
            left_frame, text=f"Chat Room: {room_name}", font=("Arial", 14, "bold")
        ).pack(pady=10)

        ttk.Label(left_frame, text=f"You are {username}").pack(pady=5)

        self.chat_display = tk.Text(
            left_frame, height=15, width=50, state="disabled", wrap="word"
        )
        self.chat_display.pack(pady=10, fill="both", expand=True)

        input_frame = ttk.Frame(left_frame)
        input_frame.pack(fill="x", pady=5)

        self.msg_entry = ttk.Entry(input_frame)
        self.msg_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        ttk.Button(input_frame, text="Send", command=self.ui_msg_request).pack(
            side="right"
        )

        ttk.Button(left_frame, text="Back to Lobby", command=self.ui_exit_request).pack(
            pady=20
        )

        right_frame = ttk.Frame(main_frame, relief="groove", padding=10)
        right_frame.pack(side="right", fill="y")

        ttk.Label(right_frame, text="Online Users", font=("Arial", 12, "bold")).pack(
            pady=(0, 5)
        )

        self.user_listbox = tk.Listbox(right_frame, height=20)
        self.user_listbox.pack(fill="y", expand=True)
        ttk.Button(right_frame, text="Refresh", command=self.ui_list_request).pack(
            side="bottom"
        )

        self.dispatcher.register_callback("exit", self.server_exit_ack)
        self.dispatcher.register_callback("list_room", self.server_list_ack)
        self.dispatcher.register_callback("msg", self.server_msg_ack)
        self.ui_list_request()

    def _append_message(self, sender, message, is_private):
        self.chat_display.config(state="normal")
        line = (
            f"[Private] {sender}: {message}\n"
            if is_private
            else f"{sender}: {message}\n"
        )
        self.chat_display.insert(tk.END, line)
        self.chat_display.config(state="disabled")
        self.chat_display.see(tk.END)

    # === UI Event Handlers ===
    def ui_exit_request(self):
        self.server_handler.send(MessageFactory.create("exit"))

    def ui_msg_request(self):
        msg = self.msg_entry.get().strip()
        if not msg:
            return

        self.msg_entry.delete(0, tk.END)
        if msg.startswith(r"\private"):
            parts = msg.split(maxsplit=2)
            if len(parts) < 3:
                print("Invalid private message format")
                return

            _, receiver, message = parts  # 丟掉第一個 "\private"
            self.server_handler.send(
                MessageFactory.create(
                    "msg", {"from": self.username, "to": receiver, "text": message}
                )
            )
        else:
            self.server_handler.send(
                MessageFactory.create(
                    "msg", {"from": self.username, "to": "public", "text": msg}
                )
            )

    def ui_list_request(self):
        self.server_handler.send(MessageFactory.create("list"))

    # === Server Ack Handlers ===
    def server_exit_ack(self, msg: Message):
        if msg.status == "ok":
            self.app.show_lobby_page(
                self.app.current_username, self.app.current_chatroom
            )
        else:
            print("Server-side error", msg.message)

    def server_list_ack(self, msg: Message):
        if msg.data is None:
            return
        self.user_listbox.delete(0, tk.END)
        for user in msg.data.get(self.room_name, []):
            self.user_listbox.insert(
                tk.END, f"*{user}" if user == self.username else user
            )

    def server_msg_ack(self, msg: Message):
        if msg.status == "ok" and msg.data is not None:
            sender = msg.data["from"]
            receiver = msg.data["to"]
            sender = "You" if sender == self.username else sender
            is_private = receiver == self.username
            text = msg.data["text"]
            self._append_message(sender, text, is_private)
        else:
            messagebox.showerror("Error", msg.message)


class LobbyPage(ttk.Frame):
    def __init__(
        self,
        parent,
        app,
        username,
        chatroom,
        dispatcher: Dispatcher,
        server_handler: ServerHandler,
    ):
        super().__init__(parent, padding="20")
        self.app = app
        self.username = username
        self.chatroom = chatroom
        self.dispatcher = dispatcher
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
        ttk.Button(self, text="Create", command=self.ui_create_room_request).grid(
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

        ttk.Button(self, text="Refresh", command=self.ui_list_request).grid(
            column=2, row=5, sticky=tk.E, pady=10
        )

        # ---- Logout ----
        ttk.Button(self, text="Logout", command=self.ui_logout_request).grid(
            column=0, row=5, pady=15, sticky=tk.W
        )

        self.columnconfigure(1, weight=1)
        self.rowconfigure(4, weight=1)
        self.dispatcher.register_callback("list", self.server_list_ack)
        self.dispatcher.register_callback("logout", self.server_logout_ack)
        self.dispatcher.register_callback("enter", self.server_enter_room_ack)
        self.dispatcher.register_callback("create", self.server_create_room_ack)
        self.ui_list_request()

    # === UI Event Handlers ===
    def ui_create_room_request(self):
        room_name = self.create_room_var.get()
        if not room_name:
            messagebox.showwarning("Warning", "Please enter a room name.")
            return
        self.server_handler.send(MessageFactory.create("create", {"room": room_name}))

    def on_enter_room(self):
        room_name = self.enter_room_var.get()
        if not room_name:
            messagebox.showwarning("Warning", "Please enter a room name.")
            return
        self.server_handler.send(MessageFactory.create("enter", {"room": room_name}))

    def ui_list_request(self):
        server_handler.send(MessageFactory.create("list"))

    def ui_logout_request(self):
        self.server_handler.send(MessageFactory.create("logout"))

    # === Server Ack Handlers ===

    def server_create_room_ack(self, msg: Message):
        if msg.status == "ok":
            messagebox.showinfo("Create Room", msg.message)
        else:
            messagebox.showwarning("Create Room", msg.message)

    def server_enter_room_ack(self, msg: Message):
        if msg.status == "ok" and msg.data is not None:
            messagebox.showinfo("Enter Room", msg.message)
            self.app.show_chatroom_page(msg.data["username"], msg.data["room"])
        else:
            messagebox.showwarning("Enter Room", msg.message)

    def server_logout_ack(self, msg: Message):
        messagebox.showinfo("Logout", msg.message)
        if msg.status == "error":
            print("Server-side not logout successfully")
        self.app.show_login_page()

    def server_list_ack(self, msg: Message):
        if msg.data is None:
            return

        for item in self.user_tree.get_children():
            self.user_tree.delete(item)

        for room, users in msg.data.items():
            room_id = self.user_tree.insert("", "end", text=f"Room: {room}")
            for user in users:
                self.user_tree.insert(room_id, "end", text=f"- {user}")


class App(tk.Tk):
    def __init__(self, dispatcher: Dispatcher, server_handler: ServerHandler):
        super().__init__()
        self.title("Chat Client")

        self.server_handler = server_handler
        self.dispatcher = dispatcher
        self.current_page = None
        self.current_username = None
        self.current_chatroom = None
        self.poll_messages()
        self.show_login_page()

    def on_server_disconnect(self):
        messagebox.showerror("Disconnected", "Server connection lost. Closing app...")
        self.after(100, self.destroy)

    def poll_messages(self):
        # handle the events (response/push) from server
        msg = self.server_handler.get_message()
        while msg:
            print(f"Get new message from server: {msg}")
            if isinstance(msg, dict) and msg.get("type") == "ServerClosed":
                self.on_server_disconnect()
                break

            self.dispatcher.handle(msg)
            msg = self.server_handler.get_message()
        else:
            self.after(100, self.poll_messages)

    def show_login_page(self):
        if self.current_page:
            self.current_page.destroy()
        self.current_page = LoginPage(self, self, self.dispatcher, self.server_handler)
        self.current_page.pack(fill="both", expand=True)

    def show_lobby_page(self, username, chatroom):
        if self.current_page:
            self.current_page.destroy()
        self.current_username = username
        self.current_chatroom = chatroom
        self.current_page = LobbyPage(
            self, self, username, chatroom, self.dispatcher, self.server_handler
        )
        self.current_page.pack(fill="both", expand=True)

    def show_chatroom_page(self, username, chatroom):
        if self.current_page:
            self.current_page.destroy()
        self.current_page = ChatRoomPage(
            self, self, username, chatroom, self.dispatcher, self.server_handler
        )
        self.current_page.pack(fill="both", expand=True)


if __name__ == "__main__":
    server_handler = ServerHandler()
    dispatcher = Dispatcher()
    app = App(dispatcher, server_handler)
    app.mainloop()
