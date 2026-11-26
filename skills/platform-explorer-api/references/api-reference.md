# Platform Explorer API Reference

Verified against the live host on March 11, 2026 unless noted otherwise.

## Base URLs

- Docs UI: `https://platform-explorer.com/api`
- Primary live REST bases (DashHQ):
  - Mainnet: `https://api.pe.dashhq.org`
  - Testnet: `https://api.testnet.pe.dashhq.org`
- Public fallback REST base (mainnet): `https://platform-explorer.pshenmic.dev`

Use the docs UI for discovery. Prefer `api.pe.dashhq.org` / `api.testnet.pe.dashhq.org` first, and fall back to `platform-explorer.pshenmic.dev` if the primary host errors.

## Verified Live Routes

These routes were exercised directly against the live host.

### Status

`GET /status`

Purpose: network health, epoch, total counters, version info, latest block, indexer sync.

Example:

```bash
curl -sS https://platform-explorer.pshenmic.dev/status
```

Observed shape:

```json
{
  "epoch": { "number": 61 },
  "transactionsCount": 59588,
  "network": "evo1",
  "api": {
    "version": "2.2.0",
    "block": { "height": 334445 }
  },
  "indexer": { "status": "synced", "syncProgress": 100 }
}
```

### Search

`GET /search?query=<text>`

Purpose: quick discovery when the user only has an alias, keyword, or partial name.

Example:

```bash
curl -sS 'https://platform-explorer.pshenmic.dev/search?query=DashMoney2.dash'
```

Observed shape:

```json
{
  "identities": [
    {
      "identifier": "4nfdswz8VvrmV9uaX9HFht81rDN1MMkagThW2CyT412t",
      "alias": "DashMoney2.dash"
    }
  ]
}
```

### Validators

`GET /validators?page=<n>&limit=<n>`

`GET /validator/<proTxHash>`

Purpose: browse validator set data or fetch one validator by `proTxHash`.

Examples:

```bash
curl -sS 'https://platform-explorer.pshenmic.dev/validators?page=2&limit=2'
curl -sS 'https://platform-explorer.pshenmic.dev/validator/06A9EE248111BF6D6D5B123CC40B3A9C9C9C3C84A58E5A2ED9DF97AD7C4E7289'
```

Observed list shape:

```json
{
  "pagination": { "page": 2, "limit": 2, "total": 547 },
  "resultSet": [
    {
      "proTxHash": "092828EDC081D3BA1A54F043259B941368F2C718881B06A9D347883B21BFE313",
      "isActive": false
    }
  ]
}
```

### Identities

`GET /identities?page=<n>&limit=<n>`

`GET /identity/<identifier>`

Purpose: list identities or inspect a single identity in depth.

Examples:

```bash
curl -sS 'https://platform-explorer.pshenmic.dev/identities?page=1&limit=1'
curl -sS 'https://platform-explorer.pshenmic.dev/identity/T1jY1c6ojfhYe5w8TV7eNwWXvGRhkcqHJPHfdC54RVz'
```

Notes:

- Detail responses include aggregate counters such as `totalTxs`, `totalTransfers`, `totalDocuments`, and withdrawal stats.
- Large balances and totals are emitted as strings.

### Transactions

`GET /transactions`

`GET /transaction/<hash>`

Purpose: inspect recent transactions or retrieve a specific transaction payload.

Example:

```bash
curl -sS 'https://platform-explorer.pshenmic.dev/transaction/D813CA05BD34FE814E238A65EC51D8D89975A8CDDBA0E39EB99154624521AFB9'
```

Observed fields include `hash`, `blockHash`, `blockHeight`, `type`, and raw `data`.

### Blocks

`GET /blocks`

`GET /block/<blockHash>`

Purpose: browse blocks or inspect one block with quorum details.

Example:

```bash
curl -sS 'https://platform-explorer.pshenmic.dev/block/20FE00F10D59B9C5487EE18C1A298A04D9DE58F414E04D61779E582F462BAD7F'
```

Observed detail shape contains:

- `header`
- `txs`
- `quorum`

### Data Contracts

`GET /dataContracts`

`GET /dataContract/<dataContractId>`

Purpose: enumerate contracts or fetch the contract schema and owner info.

Examples:

```bash
curl -sS 'https://platform-explorer.pshenmic.dev/dataContracts'
curl -sS 'https://platform-explorer.pshenmic.dev/dataContract/HY1keaRK5bcDmujNCQq5pxNyvAiHHpoHQgLN5ppiu4kh'
```

Notes:

- List responses use `resultSet`.
- Detail responses include `schema` as a JSON string, not a nested object.
- System-owned contracts use owner `11111111111111111111111111111111`.

### DPNS Alias Lookup

`GET /dpns/identity?dpns=<alias>`

Purpose: resolve a DPNS alias to an identity record.

Example:

```bash
curl -sS 'https://platform-explorer.pshenmic.dev/dpns/identity?dpns=DashMoney2.dash'
```

Observed shape:

```json
[
  {
    "identifier": "4nfdswz8VvrmV9uaX9HFht81rDN1MMkagThW2CyT412t",
    "alias": "DashMoney2.dash",
    "status": { "status": "ok" }
  }
]
```

### Token Rating

`GET /tokens/rating`

Purpose: view ranked token activity.

Example:

```bash
curl -sS 'https://platform-explorer.pshenmic.dev/tokens/rating'
```

Observed shape:

```json
{
  "resultSet": [
    {
      "tokenIdentifier": "AxAYWyXV6mrm8Sq7vc7wEM18wtL8a8rgj64SM3SDmzsB",
      "transitionCount": 1
    }
  ],
  "pagination": { "page": 1, "limit": 10, "total": 5 }
}
```

## Documented Public Route Inventory

An older public route list posted by the maintainer in GitHub issue `#508` includes:

- `/status`
- `/search?query=:query`
- `/validators`
- `/validator/:proTxHash`
- `/epochs`
- `/epoch/:epochNumber`
- `/blocks`
- `/block/:blockHash`
- `/transactions`
- `/transaction/:transactionHash`
- `/identities`
- `/identity/:identityId`
- `/dpns/identity?dpns=:dpns`
- `/dpns/identity/:identityId`
- `/dataContracts`
- `/dataContract/:dataContractId`
- `/documents`
- `/document/:documentId`
- `/withdrawals`
- `/withdrawal/:withdrawalHash`
- `/contests`
- `/contested-resources`
- `/votes`
- `/tokens`
- `/tokens/rating`

Treat this as a discovery list, not a guarantee of current live behavior.

## Routes With Drift or Caveats

Observed on March 11, 2026:

- `GET /epochs` returned `404`.
- `GET /documents?page=1&limit=2` returned `404`.
- `GET /tokens?page=1&limit=2` returned `{"error":"memory access out of bounds"}`.
- `GET /tokens/rating?page=1&limit=2` returned `{"error":"memory access out of bounds"}` even though `GET /tokens/rating` worked.
- `GET /dpns/identity/<identityId>` returned `404`, while the query-parameter version worked.

When a route behaves like this:

1. Say that the route is documented but currently failing on the live host.
2. Offer the closest working route.
3. Include the exact date of validation.

## Recommended Query Patterns

### Health Check

Use when the user wants to know whether the explorer is current or synced.

```bash
curl -sS https://platform-explorer.pshenmic.dev/status
```

### Resolve Alias Then Fetch Identity

```bash
alias='DashMoney2.dash'
id=$(curl -sS "https://platform-explorer.pshenmic.dev/dpns/identity?dpns=${alias}" | jq -r '.[0].identifier')
curl -sS "https://platform-explorer.pshenmic.dev/identity/${id}"
```

### Discover Then Drill In

```bash
curl -sS 'https://platform-explorer.pshenmic.dev/search?query=dash'
curl -sS 'https://platform-explorer.pshenmic.dev/validator/06A9EE248111BF6D6D5B123CC40B3A9C9C9C3C84A58E5A2ED9DF97AD7C4E7289'
```

### JavaScript Fetch Template

```js
const baseUrl = 'https://platform-explorer.pshenmic.dev';

async function getStatus() {
  const response = await fetch(`${baseUrl}/status`);
  if (!response.ok) {
    throw new Error(`status request failed: ${response.status}`);
  }
  return response.json();
}
```

## Practical Guidance

- Prefer the live host in examples unless the user specifically asks for the docs page.
- For list endpoints, look for `resultSet` and `pagination`.
- For detail endpoints, treat IDs and hashes as opaque strings.
- Do not assume every list route supports every pagination parameter.
- When building production code, handle `404` and malformed error payloads defensively.
