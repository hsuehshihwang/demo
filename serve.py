#!/usr/bin/env python3
"""
Local development server for the encrypted video site.
Serves static files on port 8899 with CORS headers.

Usage:
    python serve.py
    python serve.py --port 9000
"""

import http.server
import socketserver
import argparse
import os


class CORSHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        print(f"  {args[0]}")


def main():
    parser = argparse.ArgumentParser(description="Local dev server with CORS")
    parser.add_argument("-p", "--port", type=int, default=8899, help="Port (default: 8899)")
    parser.add_argument("-d", "--directory", default=".", help="Directory to serve")
    args = parser.parse_args()

    os.chdir(args.directory)

    socketserver.TCPServer.allow_reuse_address = True

    with socketserver.TCPServer(("", args.port), CORSHandler) as httpd:
        print(f"Serving on http://localhost:{args.port}")
        print(f"Directory: {os.getcwd()}")
        print("Press Ctrl+C to stop\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
