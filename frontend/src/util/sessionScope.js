export const SESSION_SCOPES = [
  { key: 'all', label: 'All Enabled' },
  { key: 'ny', label: 'NY only' },
  { key: 'london', label: 'London only' },
  { key: 'asian', label: 'Asian only' },
]

export function applySessionScope(params, scope) {
  if (!scope || scope === 'all') return params
  return {
    ...params,
    use_ny: scope === 'ny',
    use_london: scope === 'london',
    use_asian: scope === 'asian',
  }
}
