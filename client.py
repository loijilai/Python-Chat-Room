import socket
import os
from dotenv import load_dotenv

load_dotenv()

host = os.getenv('HOST')
port = int(os.getenv('PORT'))

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((host, port))
    s.sendall(b'hello, world')
    data = s.recv(1024)

print(f'recv {data}!')