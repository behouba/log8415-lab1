from fastapi import FastAPI
import uvicorn
import logging
import os
from urllib.request import Request, urlopen

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = FastAPI()

def get_instance_id() -> str:
    try:
        req_token = Request(
            "http://169.254.169.254/latest/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
        )
        token = urlopen(req_token, timeout=2).read().decode()
        req_id = Request(
            "http://169.254.169.254/latest/meta-data/instance-id",
            headers={"X-aws-ec2-metadata-token": token},
        )
        return urlopen(req_id, timeout=2).read().decode()
    except Exception:
        return "unknown"

INSTANCE_ID = get_instance_id()
CLUSTER_NAME = os.getenv("CLUSTER_NAME")

@app.get("/")
async def root():
    message = "Instance has received the request"
    logger.info(message)
    return {"message": message, "instance_id": INSTANCE_ID}

def register_cluster_routes(app: FastAPI, cluster: str | None):
    def factory(name: str):
        async def handler():
            logger.info("Serving %s on instance %s", name, INSTANCE_ID)
            return {"cluster": name, "instance_id": INSTANCE_ID}
        return handler
    if cluster in {"cluster1", "cluster2"}:
        app.get(f"/{cluster}")(factory(cluster))
    else:
        app.get("/cluster1")(factory("cluster1"))
        app.get("/cluster2")(factory("cluster2"))

register_cluster_routes(app, CLUSTER_NAME)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)