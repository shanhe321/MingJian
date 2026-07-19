export function buildTrainingExportPayload(form, isAdmin) {
  const version = String(form.version || '').trim()
  return {
    version: version || null,
    description: form.description || '',
    set_default: isAdmin ? Boolean(form.set_default) : false,
    upload_minio: Boolean(form.upload_minio),
  }
}
