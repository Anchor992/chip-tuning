"""Serve this built preview on localhost only, without installing anything."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Timer
import webbrowser

ROOT = Path(__file__).resolve().parents[2]

def main():
    handler = partial(SimpleHTTPRequestHandler, directory=str(ROOT))
    try:
        server = ThreadingHTTPServer(('127.0.0.1', 8765), handler)
    except OSError:
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    url = f'http://127.0.0.1:{server.server_port}/cinematic-preview/black-signal/'
    print('CHECK92 local preview — no public deployment')
    print(url)
    print('Keep this window open. Press Ctrl+C to stop.')
    Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
