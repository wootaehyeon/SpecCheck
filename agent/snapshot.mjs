const sourceStatuses = new Set(['collected', 'unavailable', 'permission_required', 'not_in_scope']);

export function validateSnapshot(snapshot) {
  const failures = [];
  if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) failures.push('snapshot must be an object');
  if (!snapshot?.machine || typeof snapshot.machine !== 'object') failures.push('machine is required');
  if (!Array.isArray(snapshot?.resources)) failures.push('resources must be an array');
  if (!Array.isArray(snapshot?.findings)) failures.push('findings must be an array');
  if (!Array.isArray(snapshot?.inventory)) failures.push('inventory must be an array');
  if (!Array.isArray(snapshot?.sources)) failures.push('sources must be an array');

  for (const source of snapshot?.sources ?? []) {
    if (!source?.name || !sourceStatuses.has(source.status)) failures.push('each source requires a valid name and status');
  }

  if (failures.length) throw new TypeError(`Invalid snapshot: ${failures.join(', ')}`);
  return snapshot;
}
