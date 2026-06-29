# Thread — Architecture

## System Topology

```mermaid
graph LR
    subgraph Workstation
        V[VSCode / Cline]
        B[thread_bridge<br/>MCP stdio bridge]
    end
    subgraph "Raspberry Pi 3B"
        W[Waitress WSGI<br/>12 threads]
        F[Flask App<br/>5 blueprints]
        subgraph "Data Layer"
            P[(ConnectionPool<br/>thread-local<br/>12 connections)]
            S[(SQLite + FTS5<br/>WAL mode)]
        end
        G[Git Manager<br/>subprocess per session]
    end
    V -->|MCP JSON-RPC| B
    B -->|HTTP REST| W
    W --> F
    F --> P
    P --> S
    F --> G
```

## Data Flow

```mermaid
flowchart LR
    R[HTTP Request] --> H{Request Hook}
    H -->|attach db| C[g.db from Pool]
    H -->|generate| ID[requestId]
    C --> RT[Route Handler]
    RT -->|lookup| CA{Cache Hit?}
    CA -->|yes session| L1[Session LRU]
    CA -->|yes search| L2[SearchCache<br/>5s TTL]
    CA -->|yes tags| L3[TagCache<br/>30s TTL]
    CA -->|miss| M[Models Layer]
    M --> S[(SQLite + FTS5)]
    M -->|populate| CA
    RT -->|mutation| GI[Git Commit<br/>best-effort async]
    RT -->|response| AFT{After Request Hook}
    AFT -->|log duration| LOG[JSON to stderr]
    AFT -->|set headers| RES[HTTP Response]
```

## Component Diagram

```mermaid
graph TB
    subgraph Config
        CFG[config.py<br/>env vars + defaults]
    end
    subgraph "Server Entry"
        SRV[server.py<br/>Waitress / Werkzeug]
        APP[app.py<br/>create_app factory]
    end
    subgraph "Database"
        DB[database.py<br/>ConnectionPool]
        SCH[schema.sql<br/>DDL + FTS5 + triggers]
        MOD[models.py<br/>CRUD + search]
    end
    subgraph "Caching"
        CAC[cache.py<br/>3 tiers: LRU, Search, Tags]
    end
    subgraph "API Routes"
        HLT[health.py<br/>GET /health]
        SES[sessions.py<br/>CRUD]
        ENT[entries.py<br/>CRUD + batch + bulk + upload]
        SCHR[search.py<br/>FTS5 + tags]
        STA[stats.py<br/>GET /stats]
        ERR[errors.py<br/>handlers]
    end
    subgraph "Infrastructure"
        LOG[logging_config.py<br/>NDJSON]
        GIT[git_manager.py<br/>subprocess wrapper]
        CHK[chunker.py<br/>doc ingestion]
    end
    CFG --> APP
    APP --> DB
    APP --> CAC
    APP --> HLT & SES & ENT & SCHR & STA & ERR
    APP --> LOG
    DB --> SCH
    MOD --> DB
    HLT & SES & ENT & SCHR & STA --> MOD
    HLT & SES & ENT & SCHR & STA --> CAC
    SES & ENT --> GIT
    ENT --> CHK
    SRV --> APP
```

## Request Lifecycle

```mermaid
sequenceDiagram
    participant C as Client
    participant W as Waitress Thread
    participant BH as before_request
    participant RT as Route Handler
    participant CA as Cache Layer
    participant MO as Models
    participant DB as SQLite
    participant GI as Git Manager
    participant AH as after_request

    C->>W: HTTP GET/POST/PUT/DELETE
    W->>BH: hook
    BH->>BH: generate requestId
    BH->>BH: g.db = pool.get()
    BH->>RT: dispatch
    RT->>CA: check cache
    alt cache hit
        CA-->>RT: cached result
    else cache miss
        RT->>MO: query
        MO->>DB: SQL
        DB-->>MO: rows
        MO-->>RT: result
        RT->>CA: populate cache
    end
    opt mutation (POST/PUT/DELETE)
        RT->>GI: commit (best-effort)
    end
    RT-->>AH: response
    AH->>AH: log duration + status
    AH-->>C: HTTP Response + X-Request-Id
```

## Threading Model

```mermaid
graph TB
    subgraph "Waitress (12 threads)"
        T1[Thread 1]
        T2[Thread 2]
        T3[Thread ...]
        T12[Thread 12]
    end
    subgraph "ConnectionPool"
        C1[(Conn 1)]
        C2[(Conn 2)]
        C3[(Conn ...)]
        C12[(Conn 12)]
    end
    subgraph "SQLite (WAL mode)"
        WAL[Write-Ahead Log]
        DBF[(thread.db)]
    end
    T1 -.->|threading.local| C1
    T2 -.->|threading.local| C2
    T3 -.->|threading.local| C3
    T12 -.->|threading.local| C12
    T1 & T2 & T3 & T12 -->|read concurrent| WAL
    T1 -->|write via Lock| WAL
    WAL --> DBF
```

**Key**: Each thread has a dedicated SQLite connection (`threading.local()`). Reads are fully concurrent (WAL mode). Writes serialize through a single `threading.Lock` held only for the duration of the INSERT/UPDATE/DELETE (~1-5ms). Readers never block on writers.

## Caching Architecture

```mermaid
flowchart TB
    R[Request] --> T{Request Type}
    T -->|session lookup| SESSION{Session LRU<br/>maxsize=512}
    SESSION -->|hit <1ms| DONE[Done]
    SESSION -->|miss| DB_SES[(SQLite)]
    DB_SES -->|populate| SESSION

    T -->|search| SEARCH{SearchCache<br/>128 entries<br/>5s TTL}
    SEARCH -->|hit <2ms| DONE2[Done]
    SEARCH -->|miss| FTS5[(FTS5)]
    FTS5 -->|populate| SEARCH

    T -->|tags| TAGS{TagCache<br/>30s TTL}
    TAGS -->|hit <1ms| DONE3[Done]
    TAGS -->|miss| DB_TAGS[(SQLite)]
    DB_TAGS -->|populate| TAGS

    T -->|mutation| INV[Invalidate<br/>session caches]
    INV --> SESSION
    INV --> SEARCH
    INV --> TAGS
```

All caches are in-process, pure Python, no external dependency. Cache invalidation is write-through: after any mutation (create/update/delete entry/session), all caches for that session are cleared.

## Deployment Topology

```mermaid
graph TB
    subgraph "Raspberry Pi 3B (ARMv7, 1GB RAM)"
        systemd[systemd<br/>thread.service]
        PROC[Python Process<br/>Waitress + Flask]
        DB[(SQLite<br/>thread.db)]
        GITREPO[Git Repos<br/>data/git/&lt;session&gt;/]
        JRNL[journald]
    end
    subgraph "Network"
        LAN[LAN:5000]
    end
    subgraph "Workstation"
        VSC[VSCode + Cline]
        MCP[thread_bridge<br/>stdio JSON-RPC]
    end
    systemd -->|MemoryMax=800M| PROC
    PROC --> DB
    PROC --> GITREPO
    PROC -->|stderr| JRNL
    PROC -->|listen :5000| LAN
    LAN -->|HTTP REST| MCP
    MCP -->|JSON-RPC| VSC
```

## Startup Sequence

```mermaid
sequenceDiagram
    participant SYS as systemd
    participant SRV as server.py
    participant APP as create_app()
    participant CFG as config.py
    participant POOL as ConnectionPool
    participant CACHE as caches
    participant GIT as git_manager

    SYS->>SRV: ExecStart
    SRV->>APP: create_app()
    APP->>CFG: validate()
    CFG-->>APP: Config object
    APP->>APP: setup_logging()
    APP->>POOL: start() — pre-warm 12 connections
    POOL->>POOL: open + apply pragmas + init schema
    POOL-->>APP: ready
    APP->>CACHE: init_caches()
    APP->>GIT: init_git_manager()
    APP->>APP: register blueprints + error handlers
    APP-->>SRV: Flask app
    SRV->>SYS: Waitress listening on :5000
```
