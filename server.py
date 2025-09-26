import socket
import os
import threading
from dotenv import load_dotenv

load_dotenv()

host = os.getenv('HOST')
port = int(os.getenv('PORT'))

users = {}
online_users = {}

def handle_client(conn):
    try:
        while True:
            conn.sendall(b"Type 'login' or 'register' to enter the chatroom")
            data = conn.recv(1024).decode()
            if data.lower() == 'register':
                conn.sendall(b'Enter your username:')
                username = conn.recv(1024).decode()
                if username in users:
                    conn.sendall(b'Username already in use, try another one')
                    continue

                conn.sendall(b'Enter your password:')
                password = conn.recv(1024).decode()
                users[username] = {'password': password, 'room_id': 0}
                conn.sendall(b'Register successfully! You can now login\n')

            elif data.lower() == 'login':
                conn.sendall(b'Enter your username:')
                username = conn.recv(1024).decode()
                if username not in users:
                    conn.sendall(b'Username not exists, try login first')
                    continue
                conn.sendall(b'Enter your password:')
                password = conn.recv(1024).decode()
                if password != users[username]['password']:
                    conn.sendall(b'Wrong password!')
                    continue
                conn.sendall(b'Login successfully! You can now chat!')
                break

        while True:
            # start chatting
            conn.sendall(b"Type 'list', 'enter <room id>', 'create', 'exit' to start using the chatroom")
            data = conn.recv(1024).decode()
            print(f'client says: {data}')
    except OSError as e:
        print(f"Unexpected error: {e}")
    finally:
        # TODO: final cleanup
        conn.close()

def accept_new_connection():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen()
    print(f'Server start listening on ({host}, {port})')
    while True:
        conn, addr = s.accept()
        print(f'Connected by {addr}')
        thread = threading.Thread(target=handle_client, args=(conn,))
        thread.start()

accept_new_connection()