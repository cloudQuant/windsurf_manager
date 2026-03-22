<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
      <h2 style="margin: 0; color: #303133;">Accounts</h2>
      <div style="display: flex; gap: 10px;">
        <el-button type="primary" @click="showForm = true">
          <el-icon><Plus /></el-icon>
          Add Account
        </el-button>
        <el-button type="warning" @click="handleRefreshAllStatus" :loading="refreshingAllStatus">
          <el-icon><Refresh /></el-icon>
          Refresh All Status
        </el-button>
      </div>
    </div>

    <el-table
      class="account-table"
      :data="accounts"
      :default-sort="{ prop: 'plan_expiry', order: 'ascending' }"
      stripe
      style="width: 100%"
      v-loading="loading"
    >
      <el-table-column label="Name" width="170">
        <template #default="{ row }">
          <div>
            <strong>{{ row.display_name || row.name }}</strong>
            <div v-if="row.plan_type" style="margin-top: 2px;">
              <el-tag size="small" :type="row.plan_type === 'Pro' ? 'warning' : 'info'">
                {{ row.plan_type }}
              </el-tag>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="email" label="Email" width="220" />
      <el-table-column label="Refresh Time" width="180">
        <template #default="{ row }">
          <span v-if="row.quota_updated_at" style="font-size: 12px;">{{ formatRefreshTime(row.quota_updated_at) }}</span>
          <span v-else style="color: #c0c4cc; font-size: 12px;">--</span>
        </template>
      </el-table-column>
      <el-table-column label="Status" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
            {{ row.is_active ? 'Active' : 'Inactive' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="Daily Quota" width="135">
        <template #default="{ row }">
          <QuotaBar v-if="row.daily_quota_pct != null" :pct="row.daily_quota_pct" label="Daily" />
          <span v-else style="color: #c0c4cc; font-size: 12px;">--</span>
        </template>
      </el-table-column>
      <el-table-column label="Weekly Quota" width="135">
        <template #default="{ row }">
          <QuotaBar v-if="row.weekly_quota_pct != null" :pct="row.weekly_quota_pct" label="Weekly" />
          <span v-else style="color: #c0c4cc; font-size: 12px;">--</span>
        </template>
      </el-table-column>
      <el-table-column prop="plan_expiry" label="Expiry" width="140" sortable :sort-method="sortByPlanExpiry">
        <template #default="{ row }">
          <span v-if="row.plan_expiry" style="font-size: 13px;">{{ row.plan_expiry }}</span>
          <span v-else style="color: #c0c4cc; font-size: 12px;">--</span>
        </template>
      </el-table-column>
      <el-table-column label="Balance" width="90">
        <template #default="{ row }">
          <span v-if="row.extra_balance" style="font-size: 13px;">{{ row.extra_balance }}</span>
          <span v-else style="color: #c0c4cc; font-size: 12px;">--</span>
        </template>
      </el-table-column>
      <el-table-column label="Actions" width="390">
        <template #default="{ row }">
          <div class="actions-cell">
            <el-button
              type="success"
              size="small"
              @click="handleActivate(row)"
              :loading="activatingId === row.id"
              :disabled="row.is_active"
            >
              <el-icon><Switch /></el-icon>
              Web Login
            </el-button>
            <el-button size="small" @click="handleEdit(row)">
              <el-icon><Edit /></el-icon>
              Edit
            </el-button>
            <el-button
              size="small"
              @click="handleQuota(row)"
              :loading="quotaLoadingId === row.id"
            >
              <el-icon><DataAnalysis /></el-icon>
              Refresh Status
            </el-button>
            <el-button
              type="danger"
              size="small"
              @click="handleDelete(row)"
            >
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <AccountForm
      v-model:visible="showForm"
      :editing="editingAccount"
      @saved="onSaved"
    />

    <el-dialog v-model="showActivateResult" title="Browser Login Result" width="500">
      <el-result
        :icon="activateResult?.success ? 'success' : 'warning'"
        :title="activateResult?.success ? 'Browser Login Started' : 'Browser Login Failed'"
      >
        <template #sub-title>
          <div style="text-align: left; line-height: 2;">
            <p><strong>IDE Step:</strong>
              <el-tag type="info" size="small">
                Skipped
              </el-tag>
            </p>
            <p><strong>Web Login:</strong>
              <el-tag :type="activateResult?.web_logged_in ? 'success' : 'danger'" size="small">
                {{ activateResult?.web_logged_in ? 'Started' : 'Failed' }}
              </el-tag>
            </p>
            <p style="color: #909399; font-size: 12px;">{{ activateResult?.message }}</p>
          </div>
        </template>
      </el-result>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteAccount, activateAccount, getQuota, refreshAllStatus
} from '../api/accounts.js'
import AccountForm from '../components/AccountForm.vue'
import QuotaBar from '../components/QuotaBar.vue'

const accounts = inject('accounts')
const fetchAccounts = inject('fetchAccounts')

const loading = ref(false)
const showForm = ref(false)
const editingAccount = ref(null)
const activatingId = ref(null)
const quotaLoadingId = ref(null)
const refreshingAllStatus = ref(false)
const showActivateResult = ref(false)
const activateResult = ref(null)

function formatRefreshTime(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '--'
  }
  const pad = num => String(num).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function parseExpiryValue(value) {
  if (!value) {
    return Number.POSITIVE_INFINITY
  }

  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) ? Number.POSITIVE_INFINITY : timestamp
}

function sortByPlanExpiry(a, b) {
  return parseExpiryValue(a.plan_expiry) - parseExpiryValue(b.plan_expiry)
}

function handleEdit(row) {
  editingAccount.value = { ...row }
  showForm.value = true
}

async function onSaved() {
  showForm.value = false
  editingAccount.value = null
  await fetchAccounts()
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `Delete account "${row.name}"?`, 'Confirm',
      { type: 'warning' }
    )
    await deleteAccount(row.id)
    ElMessage.success('Deleted')
    await fetchAccounts()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('Delete failed')
  }
}

async function handleActivate(row) {
  try {
    await ElMessageBox.confirm(
      `Log into Windsurf web as "${row.name}" in your default browser?\n\nThis will open the Windsurf login page in your default browser, clear the current web login state, and submit the stored credentials for ${row.email}.`,
      'Confirm Browser Login',
      { type: 'warning' }
    )
  } catch { return }

  activatingId.value = row.id
  try {
    const res = await activateAccount(row.id)
    activateResult.value = res.data
    showActivateResult.value = true
    await fetchAccounts()
  } catch (e) {
    ElMessage.error('Browser login failed: ' + (e.response?.data?.detail || e.message))
  } finally {
    activatingId.value = null
  }
}

async function handleQuota(row) {
  quotaLoadingId.value = row.id
  try {
    await getQuota(row.id)
    await fetchAccounts()
    ElMessage.success('Status refreshed')
  } catch (e) {
    ElMessage.warning('Status refresh failed: ' + (e.response?.data?.detail || e.message))
  } finally {
    quotaLoadingId.value = null
  }
}

async function handleRefreshAllStatus() {
  refreshingAllStatus.value = true
  try {
    const res = await refreshAllStatus()
    await fetchAccounts()
    const data = res.data
    ElMessage.success(`Status refreshed: ${data.success_count}/${data.total_count} accounts updated`)
  } catch (e) {
    ElMessage.error('Refresh all status failed: ' + (e.response?.data?.detail || e.message))
  } finally {
    refreshingAllStatus.value = false
  }
}
</script>

<style scoped>
.account-table :deep(.el-table__cell) {
  padding: 12px 0;
}

.actions-cell {
  display: inline-flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 8px;
  white-space: nowrap;
}

.actions-cell :deep(.el-button) {
  margin-left: 0;
  white-space: nowrap;
}
</style>
