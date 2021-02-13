import argparse
import asyncio
import logging
import os
import platform

from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer

ROOT = os.path.dirname(__file__)


async def index(request):
    content = open(os.path.join(ROOT, "index.html"), "r").read()
    return Response(content, media_type="text/html")


async def javascript(request):
    content = open(os.path.join(ROOT, "client.js"), "r").read()
    return Response(content, media_type="application/javascript")


async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    app.state.peer_connections.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print("Connection state is %s" % pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            app.state.peer_connections.discard(pc)

    # open media source
    if app.state.play_from:
        player = MediaPlayer(app.state.play_from)
    else:
        options = {"framerate": "30", "video_size": "640x480"}
        if platform.system() == "Darwin":
            player = MediaPlayer("default:none", format="avfoundation", options=options)
        else:
            player = MediaPlayer("/dev/video0", format="v4l2", options=options)

    await pc.setRemoteDescription(offer)
    for t in pc.getTransceivers():
        if t.kind == "audio" and player.audio:
            pc.addTrack(player.audio)
        elif t.kind == "video" and player.video:
            pc.addTrack(player.video)

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return JSONResponse(
        {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
    )


async def on_shutdown():
    # close peer connections
    coros = [pc.close() for pc in app.state.peer_connections]
    await asyncio.gather(*coros)
    app.state.peer_connections.clear()


app = Starlette(
    on_shutdown=[on_shutdown],
    routes=[
        Route("/", index),
        Route("/client.js", javascript),
        Route("/offer", offer, methods=["POST"]),
    ],
)
app.state.peer_connections = set()
app.state.play_from = None


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="WebRTC webcam demo")
    parser.add_argument("--ssl-certfile", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--ssl-keyfile", help="SSL key file (for HTTPS)")
    parser.add_argument("--play-from", help="Read the media from a file and sent it."),
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port for HTTP server (default: 8080)"
    )
    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    if args.play_from:
        app.state.play_from = args.play_from

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        ssl_certfile=args.ssl_certfile,
        ssl_keyfile=args.ssl_keyfile,
    )
