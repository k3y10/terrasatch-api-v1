# Generalized Edge receive provenance

The existing authenticated `GET /api/v1/edge/config` returns the device's organization-managed
`remote_config` without a new endpoint or database migration. Its `radio` object can now be
consumed by the companion generalized Edge RX implementation:

```json
{
  "radio": {
    "enabled": true,
    "mode": "continuous",
    "receivers": [{"name": "primary", "device_index": 0}],
    "targets": [{
      "id": "cottonwood-650",
      "name": "Cottonwood Repeater",
      "profile": "gmrs-repeater",
      "source_type": "repeater",
      "frequency_hz": 462650000,
      "modulation": "nfm",
      "enabled": true
    }],
    "processing": {
      "auto_calibrate": true,
      "calibration_seconds": 0.4,
      "min_transmission_seconds": 0.5,
      "max_transmission_seconds": 30,
      "end_gap_seconds": 0.9,
      "vad_enabled": true,
      "discard_no_speech": true
    }
  }
}
```

Use the existing authorized Edge-device update/control-plane mechanism to assign this object.
The receiver name/frequency are illustrative operator configuration, not verified RF data.
No new frontend or directory-backed administration workflow is introduced. Device/site scope
remains authenticated; frequency and directory metadata cannot change identity or TX policy.

Optional typed fields added to transmission `rf_metadata`: `modulation`, `target_id`,
`target_name`, `source_type`, and `repeater`. Repeater metadata accepts provider/ID/name,
output and input frequency, offset, location text and verification timestamp. Unknown
security-relevant fields inside the repeater object are rejected. Top-level flexible RF
metadata and all existing BCA fields remain compatible. These optional fields persist in
the existing JSON column; no migration is needed. Unavailable RF measurements remain null.

Repeater locations describe directory/site metadata, not a derived transmitter position.
Nooelec NESDR SMArt v5 is receive-only. Repeater discovery does not imply transmit authorization.
TerraSatch can monitor repeater outputs without transmitting. Existing TX capabilities,
approval gates, command negotiation, execution and result contracts are unchanged.

The Edge repository's `compatibility/test_generalized_rx.py` exercises actual authenticated
config retrieval, normalization, durable outbox payloads, transmission ingestion and duplicate
suppression with the real API routes/ORM and a local SQLite test database. The existing four
command/TX compatibility scenarios still run alongside the two new RX scenarios.
