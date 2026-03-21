<template>
  <el-container style="min-height: 100vh;">
    <el-header style="background: #1a1a2e; color: #fff; display: flex; align-items: center; justify-content: space-between;">
      <div style="display: flex; align-items: center; gap: 12px;">
        <el-icon :size="24"><Monitor /></el-icon>
        <span style="font-size: 18px; font-weight: 600;">Windsurf Manager</span>
      </div>
      <div v-if="activeAccount" style="font-size: 14px; color: #a0a0b0;">
        <el-tag type="success" effect="dark">
          <el-icon><User /></el-icon>
          {{ activeAccount.name }}
        </el-tag>
      </div>
    </el-header>

    <el-main style="background: #f5f5f5; padding: 24px;">
      <AccountList />
    </el-main>
  </el-container>
</template>

<script setup>
import { ref, provide, onMounted, onUnmounted } from 'vue'
import { listAccounts } from './api/accounts.js'
import AccountList from './views/AccountList.vue'

const accounts = ref([])
const activeAccount = ref(null)
let refreshTimer = null

async function fetchAccounts() {
  try {
    const res = await listAccounts()
    accounts.value = res.data
    activeAccount.value = res.data.find(a => a.is_active) || null
  } catch (e) {
    console.error('Failed to fetch accounts', e)
  }
}

provide('accounts', accounts)
provide('activeAccount', activeAccount)
provide('fetchAccounts', fetchAccounts)

onMounted(() => {
  fetchAccounts()
  refreshTimer = setInterval(fetchAccounts, 10000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style>
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
</style>
