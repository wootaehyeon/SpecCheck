import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { DatabaseSync } from 'node:sqlite';

export class ScanStore {
  constructor(path) {
    mkdirSync(dirname(path), { recursive: true });
    this.database = new DatabaseSync(path);
    this.database.exec(`
      PRAGMA journal_mode = WAL;
      PRAGMA foreign_keys = ON;
      CREATE TABLE IF NOT EXISTS scans (
        scan_id TEXT PRIMARY KEY,
        generated_at TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('complete', 'partial', 'failed')),
        diagnosis_json TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_scans_generated_at
        ON scans(generated_at DESC);
      PRAGMA optimize;
    `);
    this.insert = this.database.prepare(`
      INSERT INTO scans (scan_id, generated_at, status, diagnosis_json)
      VALUES (?, ?, ?, ?)
      ON CONFLICT(scan_id) DO UPDATE SET
        generated_at = excluded.generated_at,
        status = excluded.status,
        diagnosis_json = excluded.diagnosis_json
    `);
    this.latest = this.database.prepare(`
      SELECT diagnosis_json FROM scans ORDER BY generated_at DESC LIMIT 1
    `);
  }

  save(diagnosis) {
    this.insert.run(diagnosis.scanId, diagnosis.generatedAt, diagnosis.status, JSON.stringify(diagnosis));
  }

  getLatest() {
    const row = this.latest.get();
    return row ? JSON.parse(row.diagnosis_json) : null;
  }

  close() {
    this.database.exec('PRAGMA optimize;');
    this.database.close();
  }
}
