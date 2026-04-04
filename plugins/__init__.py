from aiohttp import web

routes = web.RouteTableDef()

@routes.get("/", allow_head=True)
async def root_route(request):
    return web.json_response({"status": "running"})

async def web_server():
    app = web.Application(client_max_size=30_000_000)
    app.add_routes(routes)
    return app
