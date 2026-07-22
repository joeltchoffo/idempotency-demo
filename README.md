# Idempotency Demo (FastAPI) 🔁

Dieses Repo ist eine kleine, reproduzierbare Demo für **Idempotency / Idempotenz** in APIs.

**Ziel:** `POST /orders` wird über einen `Idempotency-Key` **idempotent**, sodass ein Request mehrfach gesendet werden kann (Retries/Timeouts), ohne dass **doppelte Orders** entstehen.

---

## Was bedeutet Idempotency?

Eine Operation ist **idempotent**, wenn du sie mehrfach ausführen kannst und der **Systemzustand am Ende derselbe bleibt**, als hättest du sie nur einmal ausgeführt.

Intuition:  
Wenn du dieselbe Aktion nochmal machst, passiert **nichts Zusätzliches**.

### Alltagsbeispiel (Payment)
Du klickst auf **„Bezahlen“**, das Netz hängt kurz, dein Browser zeigt “Timeout”.  
Du klickst nochmal.

- **Ohne Idempotency:** im Worst Case **2–3 Abbuchungen / Orders**
- **Mit Idempotency:** der Server erkennt die Anfrage wieder → **kein Duplikat**, gleiche Antwort

Merksatz:

> **Wenn dein System Retries hat, braucht es Idempotency — sonst werden Fehler zu Duplikaten.**

---

## HTTP-Kontext (kurz)
- `GET` ist idempotent (lesen)
- `PUT` ist idempotent (ersetzen)
- `DELETE` ist idempotent (löschen)
- `POST` ist **meist nicht** idempotent (create erzeugt oft jedes Mal etwas Neues)

Darum wird Idempotency bei `POST` häufig über einen **Idempotency-Key** umgesetzt.

---

## Wie wird `POST` idempotent? (Idempotency-Key Pattern)

1. Client schickt `POST /orders` plus Header  
   `Idempotency-Key: <uuid>`
2. Server speichert beim ersten Request:  
   **key → response** (und einen **request_hash**)
3. Kommt derselbe Key nochmal:
   - gleicher Body → Response wird **replayed** (gleiche `order_id`)
   - anderer Body → **409 Conflict** (Key wurde schon für eine andere Anfrage benutzt)

---

## Was dieses Repo konkret demonstriert

### ✅ API
- `POST /orders`
  - **required**: `Idempotency-Key`
  - erstellt Order genau einmal pro Key
  - liefert Response inkl. `order_id`

### ✅ Transparenz über Response-Header
- `Idempotency-Replayed: false` → neu erstellt
- `Idempotency-Replayed: true` → wiederholte Response (kein Duplikat)
- `Idempotency-Request-Hash: ...` → Hash des Requests (zur Nachvollziehbarkeit)

### ✅ Konflikt-Handling
- gleicher Key + anderer Body → **409 Conflict**
- parallele Requests mit demselben Key → atomar genau eine gespeicherte Order

---

## Projektstruktur

```text
idempotency-demo/
  app/
    main.py        # FastAPI App + /orders Endpoint
    store.py       # Memory-Store (default) + optional SQLite-Store
  scripts/
    demo.sh        # Demo: gleicher Request 3x mit gleichem Key
  tests/
    test_idempotency.py  # Tests für Replay, Conflict, Missing-Key und parallele Retries
  requirements.txt
  README.md
```

## Projekt starten
Voraussetzungen

- Python 3.10+ (empfohlen)
- pip

## Setup
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell:
# .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

## Server starten
uvicorn app.main:app --reload

Danach:

API: http://127.0.0.1:8000

# Proof / Demo: gleicher Request 3x → gleiche order_id
Erwartetes Ergebnis

- Request 1: Idempotency-Replayed: false
- Request 2/3: Idempotency-Replayed: true
- order_id bleibt identisch → keine Duplikate trotz Retry

# Linux/macOS/WSL/Git Bash
chmod +x scripts/demo.sh
./scripts/demo.sh

# Windows PowerShell (ohne .sh)

Voraussetzung: Server läuft bereits.

```powershell
$key = [guid]::NewGuid().ToString()
$body = @{
  customer_id="cust_123"
  currency="EUR"
  amount_cents=1999
  items=@(@{ sku="sku_abc"; qty=1; unit_price_cents=1999 })
} | ConvertTo-Json -Compress

1..3 | ForEach-Object {
  "`n---- Request $_ ----"
  $resp = Invoke-WebRequest -Method Post -Uri "http://127.0.0.1:8000/orders" `
    -UseBasicParsing `
    -Headers @{ "Idempotency-Key" = $key } `
    -ContentType "application/json" `
    -Body $body

  "Status: $($resp.StatusCode)"
  "Idempotency-Replayed: $($resp.Headers['Idempotency-Replayed'])"
  "OrderId: $((($resp.Content | ConvertFrom-Json).order_id))"
}
```

# Edge Case (wichtig): gleicher Key + anderer Body ⇒ 409 Conflict

```powershell
$key = [guid]::NewGuid().ToString()

$body1 = @{ customer_id="cust_123"; currency="EUR"; amount_cents=100 } | ConvertTo-Json -Compress
$body2 = @{ customer_id="cust_123"; currency="EUR"; amount_cents=200 } | ConvertTo-Json -Compress

Invoke-WebRequest -UseBasicParsing -Method Post -Uri "http://127.0.0.1:8000/orders" `
  -Headers @{ "Idempotency-Key" = $key } -ContentType "application/json" -Body $body1 | Out-Null

try {
  Invoke-WebRequest -UseBasicParsing -Method Post -Uri "http://127.0.0.1:8000/orders" `
    -Headers @{ "Idempotency-Key" = $key } -ContentType "application/json" -Body $body2
} catch {
  "Expected: HTTP $($_.Exception.Response.StatusCode.value__) (Conflict)"
}
```
# Tests
```powershell
pytest -q
```

# Storage-Optionen
Default: In-Memory

Schnell & simpel für Demos.

Achtung:

Store ist nach Neustart weg

nicht shared zwischen mehreren Prozessen/Instanzen

Optional: Persistenter Store (SQLite)

Für Persistenz über Neustarts:

# macOS/Linux
```powershell
export IDEMPOTENCY_STORE=sqlite
export IDEMPOTENCY_DB=./idempotency.sqlite3
uvicorn app.main:app --reload
```

# Windows PowerShell
```powershell
$env:IDEMPOTENCY_STORE="sqlite"
$env:IDEMPOTENCY_DB=".\\idempotency.sqlite3"
uvicorn app.main:app --reload
```

# Wie die Implementierung funktioniert (konkret)

1. Request kommt rein mit Idempotency-Key.
2. Server berechnet einen stabilen Request-Hash (sortiertes JSON).
3. Atomarer Insert-if-absent im Store:

    - Key nicht vorhanden → Response genau einmal speichern
    - Key vorhanden + gleicher Hash → gespeicherte Response zurückgeben (Replay)
    - Key vorhanden + anderer Hash → 409 Conflict
    - parallele Requests werden durch Locking beziehungsweise den SQLite-Primärschlüssel serialisiert

# Production Notes / Grenzen

Das hier ist eine Demo. In echten Systemen sind zusätzlich wichtig:
    - Shared Store (DB/Redis) bei mehreren Instanzen
    - TTL/Expiry für Keys (z. B. 24h)
    - verteilte Atomicity über mehrere Instanzen, z. B. mit Redis `SET NX` oder einer Datenbank-Transaktion
    - Side-Effects ebenfalls idempotent machen (Emails, Events, …)

## Docker

Image bauen und API starten:

```bash
docker build -t idempotency-demo .
docker run --rm -p 8000:8000 idempotency-demo
```

Danach sind die API unter <http://127.0.0.1:8000> und die interaktive Dokumentation unter <http://127.0.0.1:8000/docs> erreichbar. Das Image läuft als nicht privilegierter Benutzer und prüft den Endpunkt `/health` über einen Container-Healthcheck.

