import socket
import os
import threading
from dotenv import load_dotenv

load_dotenv()

host = os.getenv('HOST')
port = int(os.getenv('PORT'))

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
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    print('Connected to server!')

    receive_thread = threading.Thread(target=recv_from_server, args=(s,), daemon=True)
    receive_thread.start()

    while True:
        try:
            text = input('')
            s.sendall(text.encode())
            if text == 'logout':
                break

        except OSError as e:
            print(f"Unexpected error: {e}")
            break

    s.close()

connect_to_server()