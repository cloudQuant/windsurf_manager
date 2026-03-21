import axios from 'axios'

const api = axios.create({
  baseURL: '/api/accounts',
  timeout: 60000,
})

export function listAccounts() {
  return api.get('')
}

export function createAccount(data) {
  return api.post('', data)
}

export function updateAccount(id, data) {
  return api.put(`/${id}`, data)
}

export function deleteAccount(id) {
  return api.delete(`/${id}`)
}

export function activateAccount(id) {
  return api.post(`/${id}/activate`)
}

export function getQuota(id) {
  return api.get(`/${id}/quota`)
}

export function refreshAllQuotas() {
  return api.post('/refresh-all-quotas', null, { timeout: 600000 })
}

export function refreshAllStatus() {
  return api.post('/refresh-all-status', null, { timeout: 600000 })
}
