import argparse
import socketserver


parser = argparse.ArgumentParser(
    description='Serve a video to ][Vision clients.')
parser.add_argument(
    'input', help='Path to input video file.')
parser.add_argument(
    '--port', type=int,
    # 6502 is used by ADTPro so use another nice number
    default=1977,
    help='Port number to serve on.')


def main(args):
    serve_file = args.input

    def handler():
        class ChunkHandler(socketserver.BaseRequestHandler):
            def handle(self):
                with open(serve_file, "rb") as f:
                    data = f.read()
                    print("Sending %d bytes" % len(data))
                    self.request.sendall(data)

        return ChunkHandler

    with socketserver.TCPServer(
            ("0.0.0.0", args.port), handler(),
            bind_and_activate=False) as server:
        server.allow_reuse_address = True
        server.server_bind()
        server.server_activate()
        server.serve_forever()


if __name__ == "__main__":
    main(parser.parse_args())
