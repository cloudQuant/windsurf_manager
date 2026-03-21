<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    :title="editing ? 'Edit Account' : 'Add Account'"
    width="480"
    @close="resetForm"
  >
    <el-form :model="form" label-width="100px" :rules="rules" ref="formRef">
      <el-form-item label="Name" prop="name">
        <el-input v-model="form.name" placeholder="Display name" />
      </el-form-item>
      <el-form-item label="Email" prop="email">
        <el-input v-model="form.email" placeholder="Windsurf login email" />
      </el-form-item>
      <el-form-item label="Password" prop="password">
        <el-input
          v-model="form.password"
          type="password"
          show-password
          :placeholder="editing ? 'Leave blank to keep current' : 'For web login (optional)'"
        />
      </el-form-item>
      <el-form-item label="API Key">
        <el-input v-model="form.api_key" placeholder="sk-ws-... (optional)" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">Cancel</el-button>
      <el-button type="primary" @click="handleSubmit" :loading="submitting">
        {{ editing ? 'Save' : 'Create' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { createAccount, updateAccount } from '../api/accounts.js'

const props = defineProps({
  visible: Boolean,
  editing: Object,
})
const emit = defineEmits(['update:visible', 'saved'])

const formRef = ref(null)
const submitting = ref(false)

const form = reactive({
  name: '',
  email: '',
  password: '',
  api_key: '',
})

const rules = {
  name: [{ required: true, message: 'Name is required', trigger: 'blur' }],
  email: [{ required: true, message: 'Email is required', trigger: 'blur' }],
}

watch(() => props.editing, (val) => {
  if (val) {
    form.name = val.name || ''
    form.email = val.email || ''
    form.password = ''
    form.api_key = val.api_key || ''
  }
}, { immediate: true })

function resetForm() {
  form.name = ''
  form.email = ''
  form.password = ''
  form.api_key = ''
}

async function handleSubmit() {
  try {
    await formRef.value.validate()
  } catch { return }

  submitting.value = true
  try {
    const payload = { ...form }
    if (!payload.password) delete payload.password
    if (!payload.api_key) delete payload.api_key

    if (props.editing) {
      await updateAccount(props.editing.id, payload)
      ElMessage.success('Account updated')
    } else {
      await createAccount(payload)
      ElMessage.success('Account created')
    }
    emit('saved')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || 'Save failed')
  } finally {
    submitting.value = false
  }
}
</script>
