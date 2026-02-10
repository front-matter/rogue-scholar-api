# Database Architecture Migration Plan

## Problem Statement

Current architecture has instability issues since switching from Supabase Python library:
- Dual connection pooling (QuartDB + manual pool)
- Inconsistent retry logic
- Complex fallback mechanisms
- buildpg abstraction layer adds complexity
- No proper health monitoring

## Proposed Solution

Simplify to **single connection pool** with proper Supabase Pro configuration.

### Changes Required

#### 1. Replace db_client.py

**Current Issues:**
- Dual pools compete for connections
- Retry logic only on manual pool
- g.connection fallback adds complexity
- buildpg dependency unnecessary

**Solution:** See `api/db_client_simplified.py`
- Single `AsyncConnectionPool` 
- Consistent retry on all operations
- Health checks and monitoring
- Direct psycopg (no buildpg)
- Transaction support (autocommit=False)
- Supabase Pro optimized settings

#### 2. Update api/__init__.py

**Remove QuartDB:**
```python
# REMOVE:
from quart_db import QuartDB
db = QuartDB(app, url=...)

# REPLACE WITH:
from api.db_client_simplified import get_pool, close_pool

@app.before_serving
async def startup():
    """Initialize database pool on startup."""
    await get_pool()
    logger.info("Database pool initialized")

@app.after_serving
async def shutdown():
    """Close database pool gracefully."""
    await close_pool()
    logger.info("Database pool closed")
```

**Remove request hooks:**
```python
# DELETE these - no longer needed:
@app.before_request
async def before_request():
    g.connection = await db.acquire()

@app.teardown_request  
async def teardown_request(exception):
    if hasattr(g, 'connection'):
        await db.release(g.connection)
```

#### 3. Update All Query Files

No changes needed! The `Database` class API remains the same:
- `Database.fetch_one(query, params)` ✅
- `Database.fetch_all(query, params)` ✅  
- `Database.execute(query, params)` ✅
- `Database.execute_many(query, params_list)` ✅

#### 4. Remove Dependencies

**pyproject.toml:**
```toml
# REMOVE:
quart-db[psycopg]~=0.11.0
buildpg>=0.4

# KEEP:
psycopg[binary]>=3.2,<4
psycopg-pool>=3.2,<4
```

#### 5. Update Environment Variables (Optional)

Add connection tuning:
```bash
# Supabase Pro allows 50 connections default
# Reserve some for other services/tools
DB_MAX_CONNECTIONS=20  # Per app instance
DB_MIN_CONNECTIONS=5   # Keep warm connections
```

### Migration Steps

#### Phase 1: Preparation (No Downtime)
1. ✅ Create `db_client_simplified.py` 
2. ✅ Create this migration plan
3. Run tests with current setup to establish baseline
4. Review all Database.* usages (already done - 48 found)

#### Phase 2: Code Migration (Staged)
1. Backup current `db_client.py` → `db_client_legacy.py`
2. Rename `db_client_simplified.py` → `db_client.py`
3. Update `api/__init__.py`:
   - Remove QuartDB import and initialization
   - Add startup/shutdown hooks for pool
   - Remove request hooks (before_request/teardown_request)
4. Update `pyproject.toml` dependencies
5. Test locally with `pytest`

#### Phase 3: Deployment
1. Deploy to staging
2. Monitor pool stats: `/health` endpoint (add this)
3. Load test with realistic traffic
4. Check Supabase dashboard for connection usage
5. Deploy to production with monitoring

#### Phase 4: Cleanup (After 1 week stable)
1. Remove `quart_db` dependency
2. Remove `buildpg` dependency  
3. Delete `db_client_legacy.py`
4. Update documentation

### Monitoring & Health Checks

Add health endpoint in `api/__init__.py`:
```python
@app.route("/health")
async def health():
    """Health check with database pool stats."""
    pool = await get_pool()
    stats = pool.get_pool_stats()
    
    return jsonify({
        "status": "healthy" if stats["status"] == "active" else "degraded",
        "database": stats,
        "timestamp": datetime.utcnow().isoformat()
    })
```

### Rollback Plan

If issues occur:
1. Revert `db_client.py` from `db_client_legacy.py`
2. Revert `api/__init__.py` to use QuartDB
3. Revert `pyproject.toml` dependencies
4. Redeploy previous version

### Expected Benefits

1. **Stability**: Single pool = no connection competition
2. **Resilience**: Retry on all operations, not just scripts
3. **Observability**: Pool stats, health checks
4. **Performance**: Min connections stay warm
5. **Simplicity**: Less code, easier debugging
6. **Transactions**: Can now use proper transactions when needed

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Connection limit exceeded | Start with conservative max_connections=20 |
| Query syntax changes | Database.* API unchanged, no query changes needed |
| Retry loops on bad queries | Only retry connection errors, not SQL errors |
| Pool exhaustion | Health checks detect early, alerts can trigger |

### Testing Checklist

- [ ] Unit tests pass
- [ ] Integration tests pass  
- [ ] Load test: 100 concurrent requests
- [ ] Long-running queries don't block pool
- [ ] Connection failures trigger retries
- [ ] Pool stats endpoint works
- [ ] Supabase dashboard shows healthy connection count
- [ ] No connection leaks over 1 hour test
- [ ] Graceful shutdown releases all connections

### Success Metrics

After 1 week in production:
- [ ] Zero "server closed connection" errors
- [ ] <50ms p99 query latency
- [ ] Pool availability >95%
- [ ] Successful retry rate >90% (when failures occur)
- [ ] No connection leaks (stable pool size)

---

## Quick Start (Immediate Test)

Want to test the new architecture immediately?

1. **Copy files:**
   ```bash
   cp api/db_client.py api/db_client_legacy.py
   cp api/db_client_simplified.py api/db_client.py
   ```

2. **Update api/__init__.py** - Remove QuartDB, add pool hooks

3. **Test locally:**
   ```bash
   pytest tests/
   hypercorn api:app --bind 0.0.0.0:5200
   ```

4. **Monitor:** Watch for errors, check `/health` endpoint

5. **Rollback if needed:**
   ```bash
   cp api/db_client_legacy.py api/db_client.py
   ```
