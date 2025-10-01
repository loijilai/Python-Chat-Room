import socket
import os
import threading
from dotenv import load_dotenv
import ssl

load_dotenv()

host = os.getenv("HOST")
port = int(os.getenv("PORT"))


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


def connect_to_server():
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.check_hostname = False  # close for demo
    context.verify_mode = ssl.CERT_NONE  # close for demo
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ss = context.wrap_socket(s, server_hostname=host)
    ss.connect((host, port))
    print("Connected to server!")

    receive_thread = threading.Thread(target=recv_from_server, args=(ss,), daemon=True)
    receive_thread.start()

    while True:
        try:
            text = input("")
            ss.sendall(text.encode())
            if text == "logout":
                break

        except OSError as e:
            print(f"Unexpected error: {e}")
            break

    ss.shutdown(
        socket.SHUT_RDWR
    )  # signal to the receive_thread that no more data will be sent or received
    ss.close()


connect_to_server()
