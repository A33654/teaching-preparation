"""P02 验证：单次哈希耗时 < 300ms，且旧参数哈希仍可校验通过。

用法：
    python tests/perf/verify_hash.py
    echo $?      # 0 = 达标，1 = 超时或兼容性失败

本脚本只做哈希运算，不连数据库；POSTGRES_* 仅为让 Settings 能正常实例化。
失败即非零退出，可直接挂 CI 做性能回归门禁。
"""
import os
import statistics
import sys
import time

# 让 app 包可导入（脚本位于 backend/tests/perf/）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

os.environ.setdefault("SECRET_KEY", "qa-test-secret-key")
os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_PORT", "15432")
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASSWORD", "postgres123")
os.environ.setdefault("POSTGRES_DB", "qa_blank")

from pwdlib.hashers.argon2 import Argon2Hasher  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import get_password_hash, verify_password  # noqa: E402

PWD = "teacher-test-pwd-123"

print("ARGON2_TIME_COST =", settings.ARGON2_TIME_COST)
print("ARGON2_MEMORY_COST =", settings.ARGON2_MEMORY_COST, "KiB")
print()

# 1) 单次哈希耗时
ts = []
for _ in range(11):
    t0 = time.perf_counter()
    h = get_password_hash(PWD)
    ts.append((time.perf_counter() - t0) * 1000)
ts_sorted = sorted(ts)
p50 = statistics.median(ts)
p95 = ts_sorted[int(len(ts_sorted) * 0.95) - 1]
print(f"hash  P50 = {p50:.1f} ms   P95 = {p95:.1f} ms   max = {max(ts):.1f} ms")

# 2) 单次校验耗时
vs = []
for _ in range(11):
    t0 = time.perf_counter()
    ok, _new = verify_password(PWD, h)
    vs.append((time.perf_counter() - t0) * 1000)
vs_sorted = sorted(vs)
print(f"verify P50 = {statistics.median(vs):.1f} ms  "
      f"P95 = {vs_sorted[int(len(vs_sorted) * 0.95) - 1]:.1f} ms  max = {max(vs):.1f} ms")
print("verify 结果 =", ok)

# 3) 向后兼容：旧参数（t=3, m=64MiB）写出的哈希仍要能校验通过
old_hasher = Argon2Hasher(time_cost=3, memory_cost=65536)
old_hash = old_hasher.hash(PWD)
ok_old, _ = verify_password(PWD, old_hash)
print("旧参数哈希校验 =", ok_old, "(True 表示老用户密码不受影响)")

# 4) 断言
if p95 >= 300:
    print(f"【不达标】单次哈希 P95 {p95:.1f} ms ≥ 300ms 阈值")
    sys.exit(1)
if not (ok and ok_old):
    print("【不达标】哈希校验失败：新哈希或旧参数哈希未能通过 verify")
    sys.exit(1)
print()
print(f"结论：单次哈希 P95 {p95:.1f} ms < 300ms 阈值，达标；新旧哈希均可校验。")
