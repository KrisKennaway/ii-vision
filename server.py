import socketserver

ADDR = "192.168.1.15"
PORT = 20000

FILE = "out.bin"


class ChunkHandler(socketserver.BaseRequestHandler):
    def handle(self):
        with open(FILE, "rb") as f:
            data = f.read()
            print("Sending %d bytes" % len(data))
            self.request.sendall(data)


def main():
    with socketserver.TCPServer(
            (ADDR, PORT), ChunkHandler, bind_and_activate=False) as server:
        server.allow_reuse_address = True
        server.server_bind()
        server.server_activate()
        server.serve_forever()


if __name__ == "__main__":
    main()
