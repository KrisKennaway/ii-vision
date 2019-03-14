import socketserver
import sys

ADDR = "192.168.1.15"
PORT = 20000


def main(argv):
    serve_file = argv[1]

    def handler(serve_file):
        nonlocal serve_file

        class ChunkHandler(socketserver.BaseRequestHandler):
            def handle(self):
                with open(serve_file, "rb") as f:
                    data = f.read()
                    print("Sending %d bytes" % len(data))
                    self.request.sendall(data)

        return ChunkHandler

    with socketserver.TCPServer(
            (ADDR, PORT), handler(serve_file),
            bind_and_activate=False) as server:
        server.allow_reuse_address = True
        server.server_bind()
        server.server_activate()
        server.serve_forever()


if __name__ == "__main__":
    main(sys.argv)
