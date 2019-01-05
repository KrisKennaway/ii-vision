import socketserver

ADDR = "192.168.1.15"
PORT = 20000


class ChunkHandler(socketserver.BaseRequestHandler):
    def handle(self):
        i = 0
        while True:
            i += 1
            print("sending %d" % i)
            self.request.sendall(bytes([i % (128 - 32) + 32] * 256))


def main():
    with socketserver.TCPServer(
            (ADDR, PORT), ChunkHandler, bind_and_activate=False) as server:
        server.allow_reuse_address = True
        server.server_bind()
        server.server_activate()
        server.serve_forever()


if __name__ == "__main__":
    main()
