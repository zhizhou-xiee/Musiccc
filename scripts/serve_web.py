#!/usr/bin/env python3
"""Serve the local web preview with single-range media responses."""

from __future__ import annotations

import argparse
import os
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")


class RangeRequestHandler(SimpleHTTPRequestHandler):
    """Simple static handler with the byte ranges needed by video seeking."""

    range_to_send: tuple[int, int] | None = None

    def send_head(self):  # noqa: ANN201 - signature follows stdlib handler
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()

        try:
            source = open(path, "rb")  # noqa: SIM115 - returned to the server
        except OSError:
            self.send_error(404, "File not found")
            return None

        stat = os.fstat(source.fileno())
        file_size = stat.st_size
        start, end = 0, file_size - 1
        requested_range = self.headers.get("Range")

        if requested_range:
            match = RANGE_PATTERN.fullmatch(requested_range.strip())
            if not match:
                source.close()
                self.send_error(400, "Only a single byte range is supported")
                return None

            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), file_size - 1) if last else file_size - 1
            elif last:
                suffix_length = min(int(last), file_size)
                start = file_size - suffix_length

            if start > end or start >= file_size:
                source.close()
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return None

            self.range_to_send = (start, end)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            content_length = end - start + 1
        else:
            self.range_to_send = None
            self.send_response(200)
            content_length = file_size

        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Length", str(content_length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
        self.end_headers()
        source.seek(start)
        return source

    def copyfile(self, source, outputfile) -> None:  # noqa: ANN001
        try:
            if self.range_to_send is None:
                super().copyfile(source, outputfile)
                return

            start, end = self.range_to_send
            remaining = end - start + 1
            while remaining > 0:
                chunk = source.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                outputfile.write(chunk)
                remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            # Browsers routinely cancel superseded media ranges while seeking.
            return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=4174)
    args = parser.parse_args()

    web_root = Path(__file__).resolve().parents[1] / "web"
    handler = lambda *handler_args, **kwargs: RangeRequestHandler(  # noqa: E731
        *handler_args, directory=str(web_root), **kwargs
    )
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Serving {web_root} at http://127.0.0.1:{args.port}/music/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
