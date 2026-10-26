import os
os.environ.setdefault("ENVIRONMENT", "local")
from unittest.mock import MagicMock
from sqlmodel import SQLModel, create_engine

import app.core.db as dbmod
# 文件型 SQLite（避免 :memory: 每连接独立库的问题）
DB_FILE = "./.probe_test.db"
if os.path.exists(DB_FILE):
    os.remove(DB_FILE)
eng = create_engine(f"sqlite:///{DB_FILE}", connect_args={"check_same_thread": False})
dbmod.engine = eng
SQLModel.metadata.create_all(eng)
print("tables created:", len(SQLModel.metadata.tables))

import app.core.neo4j as neo4jmod
neo4jmod.get_neo4j_driver = lambda: MagicMock()
import app.agent.llm as agent_llm
if hasattr(agent_llm, "get_chat_model"):
    agent_llm.get_chat_model = lambda *a, **k: MagicMock()

import app.main as mainmod
from fastapi.testclient import TestClient

with TestClient(mainmod.app) as c:
    r = c.get("/api/v1/utils/health-check/")
    print("health-check:", r.status_code, r.text[:60])
    r = c.post("/api/v1/login/access-token", data={"username":"teacher@example.com","password":"wrong"})
    print("login wrong pw:", r.status_code)
    r = c.post("/api/v1/login/access-token", data={"username":"teacher@example.com","password":"teacher123456"})
    print("login ok:", r.status_code, list(r.json().keys()) if r.status_code==200 else r.text[:80])
    if r.status_code == 200:
        tok = r.json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        print("me:", c.get("/api/v1/users/me", headers=h).status_code)
        print("admin stats as teacher:", c.get("/api/v1/admin/stats", headers=h).status_code)
        print("no token:", c.get("/api/v1/users/me").status_code)
        print("bad token:", c.get("/api/v1/users/me", headers={"Authorization":"Bearer bad"}).status_code)
os.remove(DB_FILE)
print("PROBE OK")
