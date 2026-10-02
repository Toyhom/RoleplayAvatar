"""Health probes for native services and OpenAI-compatible local engines."""

import json
import urllib.error
import urllib.request


def probe(port, route="/healthz", *, opener=None):
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
    routes = [route, "/health"] if route == "/healthz" else [route]
    for endpoint in routes:
        try:
            with opener.open(f"http://127.0.0.1:{int(port)}{endpoint}", timeout=3) as response:
                raw = response.read()
                if endpoint == "/health" and response.status == 200:
                    return {"status": "ready"}
                return json.loads(raw)
        except urllib.error.HTTPError as error:
            if error.code != 404:
                return {"status": "unavailable"}
        except (OSError, ValueError):
            return {"status": "unavailable"}
    return {"status": "unavailable"}
