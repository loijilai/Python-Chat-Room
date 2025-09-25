import socket
import os
from dotenv import load_dotenv

load_dotenv()

host = os.getenv('HOST')
port = int(os.getenv('PORT'))

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((host, port))
    s.listen()
    conn, addr = s.accept()
    with conn:
        print(f"Connected by {addr}")
        while True:
            data = conn.recv(1024)
            if not data:
                break
            conn.sendall(data)