← [Back to README](../README.md)

# Execution Flow

A single sync run, from `main()` to a final exit code — settings
validation, MSAL authentication, format-agnostic chunked read + dedupe,
and the concurrent, circuit-breaker-guarded upsert loop.

```mermaid
sequenceDiagram
    participant Main as dataverse_sync_runner.main()
    participant Runner as BaseSyncRunner.run()
    participant Leaf as DataverseInventorySyncRunner<br/>(InventoryDomainMixin + BaseODataSyncRunner)
    participant Source as CsvInventorySource
    participant Settings as InventorySyncSettings
    participant Client as DataverseClient
    participant Entra as Microsoft Entra ID
    participant Reader as CsvRecordReader
    participant Dedupe as dedupe_last_seen[_chunks]()
    participant Breaker as ConsecutiveFailureCircuitBreaker
    participant Dataverse as Dataverse Web API (v9.2)

    Main->>Source: CsvInventorySource()
    Main->>Leaf: DataverseInventorySyncRunner(source=Source)
    Main->>Runner: .run()

    Runner->>Leaf: load_settings()
    Leaf->>Settings: InventorySyncSettings()
    alt required field missing/empty
        Settings-->>Runner: ValidationError
        Runner->>Runner: log + return 1
    end
    Settings-->>Runner: validated config

    Runner->>Leaf: build_client(settings)
    Leaf-->>Runner: DataverseClient.from_settings(settings,<br/>pool_maxsize=2 * max_workers)
    Runner->>Client: acquire_bearer_token()
    Client->>Entra: OAuth2 client-credentials grant (MSAL)
    alt credentials rejected
        Entra-->>Client: AADSTS error
        Client-->>Runner: DataverseAuthenticationError (is-a AuthenticationError)
        Runner->>Runner: log + return 1
    end
    Entra-->>Client: Bearer token (cached for reuse)

    Runner->>Leaf: load_records()
    alt source satisfies ChunkedRecordSource (CSV)
        loop each chunksize-row chunk, in file order
            Leaf->>Source: source.read_record_chunks(chunksize)
            Source->>Reader: load_chunks(csv_path, chunksize)
            Reader-->>Source: one chunk DataFrame
            Source-->>Leaf: chunk DataFrame
        end
        Leaf->>Dedupe: dedupe_last_seen_chunks(chunks, key="sku_id")
        Note over Dedupe: last-seen dict across chunks —<br/>memory ~ unique SKUs, not total rows
    else source reads in one shot (JSON)
        Leaf->>Source: source.read_records()
        Source->>Reader: load(json_path)
        Reader-->>Source: raw DataFrame
        Source-->>Leaf: raw DataFrame
        Leaf->>Dedupe: dedupe_last_seen(df, key="sku_id")
    end
    Dedupe-->>Leaf: one row per sku_id (last-seen wins)
    Leaf-->>Runner: deduplicated records

    Runner->>Leaf: sync_records(client, records)
    Leaf->>Breaker: new ConsecutiveFailureCircuitBreaker(failure_threshold)
    Note over Leaf,Dataverse: ThreadPoolExecutor(max_workers) dispatches<br/>every record's steps below concurrently, at most<br/>write_window_size futures held in memory at once
    loop each deduplicated record (up to max_workers in flight,<br/>up to write_window_size submitted-but-uncollected)
        Leaf->>Breaker: is_tripped?
        alt already tripped
            Breaker-->>Leaf: True
            Leaf-->>Leaf: "skipped" — no network call
        else not yet tripped
            Breaker-->>Leaf: False
            Leaf->>Leaf: build_payload(row)
            Leaf->>Client: upsert_record(entity_set="lagsol_inventoryitems",<br/>alternate_key_name="lagsol_skuid", key_value=sku_id, payload)
            Client->>Dataverse: HTTP PATCH /lagsol_inventoryitems(lagsol_skuid='...')
            alt record didn't exist
                Dataverse-->>Client: 201 Created
                Client-->>Leaf: response
                Leaf->>Breaker: record_success()
            else record existed
                Dataverse-->>Client: 204 No Content
                Client-->>Leaf: response
                Leaf->>Breaker: record_success()
            else request rejected (retried first, per BaseHttpClient)
                Dataverse-->>Client: 4xx/5xx
                Client-->>Leaf: requests.HTTPError (logged, counted)
                Leaf->>Breaker: record_failure()
                opt this failure just reached failure_threshold
                    Breaker-->>Leaf: True — log "circuit breaker tripped"
                end
            end
        end
    end
    Leaf-->>Runner: created/updated/failed/skipped counts

    Runner->>Runner: log tally, return 0 (or 1 if anything failed)
    Runner-->>Main: exit code
```

Re-running the sync is safe by construction: `upsert_record` issues an
`HTTP PATCH` against the `lagsol_skuid` alternate key, which is itself the
idempotency guarantee (OData v4 upsert semantics) — there is no
read-then-decide step that a second run could race against.

---

← [Back to README](../README.md)
