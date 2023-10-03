from quart import Quart, render_template, websocket

app = Quart(__name__)

@app.route("/api")
async def json():
    return {"hello": "world"}


@app.websocket("/ws")
async def ws():
    while True:
        await websocket.send("hello")
        await websocket.send_json({"hello": "world"})


if __name__ == "__main__":
    app.run()
