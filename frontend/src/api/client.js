import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

export async function uploadCsv(files, sourceTz = 'UTC') {
  const form = new FormData()
  files.forEach((f) => form.append('files', f))
  form.append('source_tz', sourceTz)
  const res = await api.post('/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export async function fetchTwelveData(payload) {
  const res = await api.post('/data/twelvedata', payload)
  return res.data
}

export async function runBacktest(payload) {
  const res = await api.post('/backtest/run', payload)
  return res.data
}

export async function runWalkForward(payload) {
  const res = await api.post('/backtest/walkforward', payload)
  return res.data
}

export async function listSessions() {
  const res = await api.get('/data/sessions')
  return res.data
}

export default api
