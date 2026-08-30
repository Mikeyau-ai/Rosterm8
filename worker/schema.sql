-- One row per synced database. The server never sees plaintext: `ciphertext`
-- and `iv` are produced on the device and are meaningless without the user's
-- secret, which is never transmitted.
CREATE TABLE IF NOT EXISTS blobs (
  id         TEXT PRIMARY KEY,   -- hex SHA-256 derived from the user's secret
  ciphertext TEXT NOT NULL,      -- base64 AES-GCM ciphertext
  iv         TEXT NOT NULL,      -- base64 12-byte nonce, fresh for every write
  updated_at TEXT NOT NULL       -- ISO timestamp, set by the device
);
