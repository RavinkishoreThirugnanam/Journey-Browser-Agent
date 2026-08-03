#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import sys


HEADER_LIMIT = 65536


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def handle_client(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter, target_host: str, target_port: int) -> None:
    server_reader = None
    server_writer = None
    try:
        server_reader, server_writer = await asyncio.open_connection(target_host, target_port)
        first = await client_reader.readuntil(b'\r\n\r\n')
        if len(first) > HEADER_LIMIT:
            raise RuntimeError('Request headers exceeded proxy limit')
        text = first.decode('iso-8859-1')
        lines = text.split('\r\n')
        rewritten = []
        host_done = False
        for line in lines:
            if line.lower().startswith('host:'):
                rewritten.append(f'Host: {target_host}:{target_port}')
                host_done = True
            else:
                rewritten.append(line)
        if not host_done and rewritten:
            rewritten.insert(1, f'Host: {target_host}:{target_port}')
        server_writer.write('\r\n'.join(rewritten).encode('iso-8859-1'))
        await server_writer.drain()
        await asyncio.gather(
            pipe(client_reader, server_writer),
            pipe(server_reader, client_writer),
        )
    except asyncio.IncompleteReadError as exc:
        if server_writer and exc.partial:
            server_writer.write(exc.partial)
            await server_writer.drain()
    except Exception as exc:
        try:
            body = f'CDP proxy error: {exc}\n'.encode('utf-8')
            client_writer.write(
                b'HTTP/1.1 502 Bad Gateway\r\n'
                + f'Content-Length: {len(body)}\r\nContent-Type: text/plain\r\n\r\n'.encode('ascii')
                + body
            )
            await client_writer.drain()
        except Exception:
            pass
    finally:
        for writer in (server_writer, client_writer):
            if writer:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass


async def main() -> None:
    listen_host = sys.argv[1]
    listen_port = int(sys.argv[2])
    target_host = sys.argv[3]
    target_port = int(sys.argv[4])
    server = await asyncio.start_server(
        lambda reader, writer: handle_client(reader, writer, target_host, target_port),
        listen_host,
        listen_port,
    )
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    asyncio.run(main())